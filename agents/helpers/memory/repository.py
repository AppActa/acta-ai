from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pymongo.database import Database
from qdrant_client import QdrantClient, models

from agents.helpers.embeddings import gerar_embedding
from agents.helpers.errors import AuthorizationError, NotFoundError
from agents.helpers.serialization import serialize
from clients.mcp_acta_client import MCPRequestContext as RequestContext

logger = logging.getLogger(__name__)

PII_PATTERNS = (
    ("CPF", r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"),
    ("CNPJ", r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}"),
    ("TELEFONE", r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}"),
    ("EMAIL", r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
)


def sanitize_text(text: str) -> str:
    sanitized = text.strip()
    for label, pattern in PII_PATTERNS:
        sanitized = re.sub(pattern, f"[{label} OMITIDO]", sanitized)
    return sanitized


class MemoryRepository:
    def __init__(
        self,
        database: Database,
        qdrant: QdrantClient,
        *,
        messages_collection_name: str,
        memories_collection_name: str,
        vector_size: int,
        message_retention_days: int,
        inferred_retention_days: int,
    ) -> None:
        self.sessions = database["memoria_sessoes"]
        self.messages = database["memoria_mensagens"]
        self.memories = database["memoria_usuario"]
        self.consents = database["memoria_consentimentos"]
        self.qdrant = qdrant
        self.messages_collection_name = messages_collection_name
        self.memories_collection_name = memories_collection_name
        self.vector_size = vector_size
        self.message_retention_days = message_retention_days
        self.inferred_retention_days = inferred_retention_days

    @staticmethod
    def _owner(context: RequestContext) -> dict[str, int]:
        return {"usuario_id": context.usuario_id, "empresa_id": context.empresa_id}

    def ensure_indexes(self) -> None:
        self.sessions.create_index("session_id", unique=True)
        self.sessions.create_index("expira_em", expireAfterSeconds=0)
        self.sessions.create_index([("empresa_id", 1), ("usuario_id", 1), ("atualizada_em", -1)])
        self.messages.create_index([("session_id", 1), ("criada_em", -1)])
        self.messages.create_index("expira_em", expireAfterSeconds=0)
        self.memories.create_index([("empresa_id", 1), ("usuario_id", 1), ("status", 1)])
        expiration_index = self.memories.index_information().get("expira_em_1")
        if expiration_index and "expireAfterSeconds" in expiration_index:
            self.memories.drop_index("expira_em_1")
        self.memories.create_index("expira_em")
        self.consents.create_index([("empresa_id", 1), ("usuario_id", 1)], unique=True)
        if self.qdrant is not None:
            for collection_name in (self.messages_collection_name, self.memories_collection_name):
                self._ensure_vector_collection(collection_name)
        self.cleanup_expired()
        if self.qdrant is not None:
            self._retry_pending_indexes()

    def _ensure_vector_collection(self, collection_name: str) -> None:
        if self.qdrant is None:
            return
        if not self.qdrant.collection_exists(collection_name):
            self.qdrant.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
        else:
            vectors = self.qdrant.get_collection(collection_name).config.params.vectors
            if (
                not isinstance(vectors, models.VectorParams)
                or vectors.size != self.vector_size
                or vectors.distance != models.Distance.COSINE
            ):
                raise ValueError(
                    f"A collection Qdrant '{collection_name}' não é compatível "
                    f"com vetores cosine de dimensão {self.vector_size}."
                )

        for field_name, schema in (
            ("usuario_id", models.PayloadSchemaType.INTEGER),
            ("empresa_id", models.PayloadSchemaType.INTEGER),
            ("status", models.PayloadSchemaType.KEYWORD),
            ("session_id", models.PayloadSchemaType.KEYWORD),
            ("tipo", models.PayloadSchemaType.KEYWORD),
        ):
            self.qdrant.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=schema,
                wait=True,
            )

    def _retry_pending_indexes(self) -> None:
        for message in list(self.messages.find({"indice_status": "pendente"}))[:100]:
            try:
                self.qdrant.upsert(
                    collection_name=self.messages_collection_name,
                    wait=True,
                    points=[
                        models.PointStruct(
                            id=message["_id"],
                            vector=gerar_embedding(message["content"]),
                            payload={
                                "usuario_id": message["usuario_id"],
                                "empresa_id": message["empresa_id"],
                                "session_id": message["session_id"],
                                "role": message["role"],
                                "status": "ativa",
                            },
                        )
                    ],
                )
            except Exception:  # noqa: BLE001 - tenta novamente na próxima inicialização
                logger.exception("Não foi possível reindexar mensagem pendente no Qdrant.")
            else:
                self.messages.update_one(
                    {"_id": message["_id"]}, {"$set": {"indice_status": "sincronizado"}}
                )

        for memory in list(self.memories.find({"indice_status": "pendente", "status": "ativa"}))[:100]:
            context = RequestContext(
                usuario_id=memory["usuario_id"],
                empresa_id=memory["empresa_id"],
                trace_id="memory-reindex",
            )
            try:
                self._upsert_vector(context, memory)
            except Exception:  # noqa: BLE001 - tenta novamente na próxima inicialização
                logger.exception("Não foi possível reindexar memória pendente no Qdrant.")
            else:
                self.memories.update_one(
                    {"_id": memory["_id"]}, {"$set": {"indice_status": "sincronizado"}}
                )

    def cleanup_expired(self, context: RequestContext | None = None) -> int:
        now = datetime.now(UTC)
        query: dict[str, Any] = {
            "$or": [
                {"status": "excluida_indice_pendente"},
                {
                    "status": {"$in": ["ativa", "expirada_indice_pendente"]},
                    "expira_em": {"$ne": None, "$lte": now},
                },
            ]
        }
        if context is not None:
            query.update(self._owner(context))
        expired_memory_ids: list[str] = []
        deleted_memory_ids: list[str] = []
        for item in self.memories.find(query, {"_id": 1, "status": 1}):
            if item.get("status") == "excluida_indice_pendente":
                deleted_memory_ids.append(item["_id"])
            else:
                expired_memory_ids.append(item["_id"])
        memory_ids = expired_memory_ids + deleted_memory_ids
        message_query: dict[str, Any] = {"expira_em": {"$lte": now}}
        if context is not None:
            message_query.update(self._owner(context))
        message_ids = [item["_id"] for item in self.messages.find(message_query, {"_id": 1})]
        if not memory_ids and not message_ids:
            return 0
        status = "expirada"
        if memory_ids:
            if self.qdrant is not None:
                try:
                    self.qdrant.delete(
                        collection_name=self.memories_collection_name,
                        points_selector=models.PointIdsList(points=memory_ids),
                        wait=True,
                    )
                except Exception:  # noqa: BLE001 - mantém bloqueado no Mongo e tenta depois
                    status = "expirada_indice_pendente"
                    logger.exception("Não foi possível remover vetores de memória expirados do Qdrant.")
            if expired_memory_ids:
                self.memories.update_many(
                    {"_id": {"$in": expired_memory_ids}},
                    {"$set": {"status": status, "expirada_em": now}},
                )
            if deleted_memory_ids and status != "expirada_indice_pendente":
                self.memories.update_many(
                    {"_id": {"$in": deleted_memory_ids}},
                    {"$set": {"status": "excluida"}},
                )
        if message_ids:
            if self.qdrant is None:
                self.messages.delete_many({"_id": {"$in": message_ids}})
            else:
                try:
                    self.qdrant.delete(
                        collection_name=self.messages_collection_name,
                        points_selector=models.PointIdsList(points=message_ids),
                        wait=True,
                    )
                except Exception:  # noqa: BLE001 - deixa a mensagem para uma nova tentativa
                    logger.exception("Não foi possível remover vetores de mensagens expiradas do Qdrant.")
                else:
                    self.messages.delete_many({"_id": {"$in": message_ids}})
        return len(memory_ids) + len(message_ids)

    def ensure_session(
        self,
        context: RequestContext,
        session_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        existing = self.sessions.find_one({"session_id": session_id})
        if existing and any(
            existing.get(key) != value for key, value in self._owner(context).items()
        ):
            raise AuthorizationError("A sessão não pertence ao usuário autenticado nesta empresa.")
        self.sessions.update_one(
            {"session_id": session_id, **self._owner(context)},
            {
                "$setOnInsert": {
                    "_id": str(uuid4()),
                    "session_id": session_id,
                    **self._owner(context),
                    "iniciada_em": now,
                    "resumo": "",
                    "resumido_ate": None,
                    "total_mensagens": 0,
                    "metadata": metadata or {},
                },
                "$set": {
                    "status": "aberta",
                    "atualizada_em": now,
                    "expira_em": now + timedelta(days=self.message_retention_days),
                },
            },
            upsert=True,
        )
        return serialize(self.sessions.find_one({"session_id": session_id, **self._owner(context)}))

    def add_message(
        self,
        context: RequestContext,
        *,
        session_id: str,
        role: str,
        content: str,
        agent: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        self.ensure_session(context, session_id)
        now = datetime.now(UTC)
        document = {
            "_id": str(uuid4()),
            "session_id": session_id,
            **self._owner(context),
            "role": role,
            "content": sanitize_text(content)[:8000],
            "agent": agent,
            "metadata": metadata,
            "indice_status": "pendente",
            "criada_em": now,
            "expira_em": now + timedelta(days=self.message_retention_days),
        }
        self.messages.insert_one(document)
        self.sessions.update_one(
            {"session_id": session_id, **self._owner(context)},
            {
                "$inc": {"total_mensagens": 1},
                "$set": {
                    "atualizada_em": now,
                    "expira_em": now + timedelta(days=self.message_retention_days),
                },
            },
        )
        if self.qdrant is not None:
            try:
                self.qdrant.upsert(
                collection_name=self.messages_collection_name,
                wait=True,
                points=[
                    models.PointStruct(
                        id=document["_id"],
                        vector=gerar_embedding(document["content"]),
                        payload={
                            "usuario_id": context.usuario_id,
                            "empresa_id": context.empresa_id,
                            "session_id": session_id,
                            "role": role,
                            "status": "ativa",
                        },
                    )
                ],
                )
            except Exception:  # noqa: BLE001 - Mongo é a fonte de verdade
                logger.exception("Não foi possível indexar mensagem no Qdrant.")
            else:
                document["indice_status"] = "sincronizado"
                self.messages.update_one(
                    {"_id": document["_id"]}, {"$set": {"indice_status": "sincronizado"}}
                )
        return serialize(document)

    def session_context(
        self, context: RequestContext, session_id: str, limit: int
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        session = self._existing_session(context, session_id)
        if session is None:
            return {"session_id": session_id, "resumo": ""}, []
        messages = list(
            self.messages.find({"session_id": session_id, **self._owner(context)})
            .sort("criada_em", -1)
            .limit(limit)
        )
        messages.reverse()
        return session, serialize(messages)

    def summary_material(
        self, context: RequestContext, session_id: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        session = self._existing_session(context, session_id)
        if session is None:
            return {"session_id": session_id, "resumo": ""}, []
        query: dict[str, Any] = {"session_id": session_id, **self._owner(context)}
        if session.get("resumido_ate"):
            query["criada_em"] = {"$gt": session["resumido_ate"]}
        messages = list(self.messages.find(query).sort("criada_em", 1))
        return session, serialize(messages)

    def _existing_session(
        self, context: RequestContext, session_id: str
    ) -> dict[str, Any] | None:
        session = self.sessions.find_one({"session_id": session_id})
        if session is None:
            return None
        if any(session.get(key) != value for key, value in self._owner(context).items()):
            raise AuthorizationError("A sessão não pertence ao usuário autenticado nesta empresa.")
        return serialize(session)

    def close_session_if_has_messages(self, context: RequestContext, session_id: str) -> bool:
        now = datetime.now(UTC)
        result = self.sessions.update_one(
            {"session_id": session_id, **self._owner(context), "total_mensagens": {"$gt": 0}},
            {"$set": {"status": "encerrada", "encerrada_em": now, "atualizada_em": now}},
        )
        return result.matched_count == 1

    def list_chats(self, context: RequestContext, limit: int) -> list[dict[str, Any]]:
        chats = self.sessions.find(
            {**self._owner(context), "total_mensagens": {"$gt": 0}}
        ).sort("atualizada_em", -1).limit(limit)
        return serialize(list(chats))

    def update_summary(
        self,
        context: RequestContext,
        session_id: str,
        summary: str,
        summarized_until: datetime,
    ) -> None:
        result = self.sessions.update_one(
            {"session_id": session_id, **self._owner(context)},
            {
                "$set": {
                    "resumo": sanitize_text(summary)[:12000],
                    "resumido_ate": summarized_until,
                    "atualizada_em": datetime.now(UTC),
                }
            },
        )
        if result.matched_count == 0:
            raise NotFoundError("Sessão não encontrada.")

    def get_consent(self, context: RequestContext) -> dict[str, Any]:
        consent = self.consents.find_one(self._owner(context))
        if consent:
            return serialize(consent)
        return {**self._owner(context), "modo": "somente_explicitas", "retencao_dias": None}

    def set_consent(
        self, context: RequestContext, modo: str, retencao_dias: int | None
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        self.consents.update_one(
            self._owner(context),
            {
                "$set": {
                    **self._owner(context),
                    "modo": modo,
                    "retencao_dias": retencao_dias,
                    "atualizada_em": now,
                }
            },
            upsert=True,
        )
        if modo == "desativado":
            memory_ids = [
                item["_id"]
                for item in self.memories.find(
                    {**self._owner(context), "status": "ativa"}, {"_id": 1}
                )
            ]
            message_ids = [
                item["_id"]
                for item in self.messages.find(self._owner(context), {"_id": 1})
            ]
            self.memories.update_many(
                {**self._owner(context), "status": "ativa"},
                {"$set": {"status": "excluida", "excluida_em": now}},
            )
            self.messages.delete_many(self._owner(context))
            self.sessions.delete_many(self._owner(context))
            if memory_ids and self.qdrant is not None:
                self.qdrant.delete(
                    self.memories_collection_name,
                    points_selector=models.PointIdsList(points=memory_ids),
                    wait=True,
                )
            if message_ids and self.qdrant is not None:
                self.qdrant.delete(
                    self.messages_collection_name,
                    points_selector=models.PointIdsList(points=message_ids),
                    wait=True,
                )
        return self.get_consent(context)

    def store_memory(self, context: RequestContext, data: dict[str, Any]) -> dict[str, Any] | None:
        self.cleanup_expired(context)
        consent = self.get_consent(context)
        if consent["modo"] == "desativado":
            return None
        if data["origem"] == "inferida" and consent["modo"] != "automatica":
            return None
        now = datetime.now(UTC)
        retention = consent.get("retencao_dias")
        if retention is None and data["origem"] == "inferida":
            retention = self.inferred_retention_days
        memory_id = str(uuid4())
        document = {
            "_id": memory_id,
            **self._owner(context),
            **data,
            "conteudo": sanitize_text(data["conteudo"]),
            "status": "ativa",
            "indice_status": "pendente",
            "criada_em": now,
            "atualizada_em": now,
            "expira_em": now + timedelta(days=retention) if retention else None,
        }
        duplicate = self.memories.find_one(
            {
                **self._owner(context),
                "status": "ativa",
                "tipo": document["tipo"],
                "conteudo": document["conteudo"],
            }
        )
        if duplicate:
            if self.qdrant is not None:
                try:
                    self._upsert_vector(context, duplicate)
                except Exception:  # noqa: BLE001 - Mongo é a fonte de verdade
                    logger.exception("Não foi possível indexar memória existente no Qdrant.")
            return serialize(duplicate)
        self.memories.insert_one(document)
        if self.qdrant is not None:
            try:
                self._upsert_vector(context, document)
            except Exception:  # noqa: BLE001 - Mongo é a fonte de verdade
                logger.exception("Não foi possível indexar memória no Qdrant.")
            else:
                document["indice_status"] = "sincronizado"
                self.memories.update_one(
                    {"_id": document["_id"]}, {"$set": {"indice_status": "sincronizado"}}
                )
        return serialize(document)

    def _upsert_vector(self, context: RequestContext, document: dict[str, Any]) -> None:
        if self.qdrant is None:
            raise RuntimeError("Índice semântico de memória não configurado.")
        self.qdrant.upsert(
            collection_name=self.memories_collection_name,
            wait=True,
            points=[
                models.PointStruct(
                    id=document["_id"],
                    vector=gerar_embedding(document["conteudo"]),
                    payload={
                        "usuario_id": context.usuario_id,
                        "empresa_id": context.empresa_id,
                        "tipo": document["tipo"],
                        "status": "ativa",
                    },
                )
            ],
        )

    def list_memories(
        self, context: RequestContext, *, tipo: str | None, limit: int
    ) -> list[dict[str, Any]]:
        self.cleanup_expired(context)
        query: dict[str, Any] = {**self._owner(context), "status": "ativa"}
        if tipo:
            query["tipo"] = tipo
        return serialize(list(self.memories.find(query).sort("atualizada_em", -1).limit(limit)))

    def semantic_search(
        self, context: RequestContext, query: str, limit: int
    ) -> list[dict[str, Any]]:
        if self.qdrant is None:
            raise RuntimeError("Índice semântico de memória não configurado.")
        self.cleanup_expired(context)
        response = self.qdrant.query_points(
            collection_name=self.memories_collection_name,
            query=gerar_embedding(query),
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="usuario_id", match=models.MatchValue(value=context.usuario_id)
                    ),
                    models.FieldCondition(
                        key="empresa_id", match=models.MatchValue(value=context.empresa_id)
                    ),
                    models.FieldCondition(key="status", match=models.MatchValue(value="ativa")),
                ]
            ),
            with_payload=False,
            limit=limit,
        )
        scores = {str(point.id): float(point.score) for point in response.points}
        documents = {
            item["_id"]: item
            for item in self.memories.find(
                {"_id": {"$in": list(scores)}, **self._owner(context), "status": "ativa"}
            )
        }
        return [
            {**serialize(documents[memory_id]), "score": round(scores[memory_id], 6)}
            for memory_id in scores
            if memory_id in documents
        ]

    def delete_memory(self, context: RequestContext, memory_id: str) -> bool:
        now = datetime.now(UTC)
        deleted_status = "excluida" if self.qdrant is None else "excluida_indice_pendente"
        result = self.memories.update_one(
            {"_id": memory_id, **self._owner(context), "status": "ativa"},
            {"$set": {"status": deleted_status, "excluida_em": now}},
        )
        if result.matched_count:
            if self.qdrant is not None:
                try:
                    self.qdrant.delete(
                        collection_name=self.memories_collection_name,
                        points_selector=models.PointIdsList(points=[memory_id]),
                        wait=True,
                    )
                except Exception:  # noqa: BLE001 - cleanup_expired retries vector removal
                    logger.exception("Failed to remove deleted memory vector from Qdrant.")
                else:
                    self.memories.update_one(
                        {
                            "_id": memory_id,
                            **self._owner(context),
                            "status": "excluida_indice_pendente",
                        },
                        {"$set": {"status": "excluida"}},
                    )
            return True
        return False
