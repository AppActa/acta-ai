from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo.database import Database
from qdrant_client import QdrantClient, models

from agents.helpers.embeddings import gerar_embedding
from agents.helpers.errors import AuthorizationError, NotFoundError
from agents.helpers.serialization import serialize
from clients.mcp_acta_client import MCPRequestContext as RequestContext
from config import MONGODB_MESSAGES_COLLECTION, MONGODB_SESSIONS_COLLECTION

logger = logging.getLogger(__name__)
SESSION_TITLE_MAX_LENGTH = 80
MAX_CONTEXT_MESSAGES = 30
PII_PATTERNS = (
    ("CPF", r"\d{3}[.]?\d{3}[.]?\d{3}-?\d{2}"),
    ("CNPJ", r"\d{2}[.]?\d{3}[.]?\d{3}/?\d{4}-?\d{2}"),
    ("TELEFONE", r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}"),
    ("EMAIL", r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
)


def sanitize_text(text: str) -> str:
    sanitized = text.strip()
    for label, pattern in PII_PATTERNS:
        sanitized = re.sub(pattern, f"[{label} OMITIDO]", sanitized)
    return sanitized


def _session_title(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip()[:SESSION_TITLE_MAX_LENGTH].rstrip()


class MemoryRepository:
    """Persistência de conversas em duas collections Mongo e vetores no Qdrant."""

    def __init__(
        self,
        database: Database,
        qdrant: QdrantClient | None,
        *,
        messages_collection_name: str,
        vector_size: int,
    ) -> None:
        self.sessions = database[MONGODB_SESSIONS_COLLECTION]
        self.messages = database[MONGODB_MESSAGES_COLLECTION]
        self.qdrant = qdrant
        self.messages_collection_name = messages_collection_name
        self.vector_size = vector_size

    @staticmethod
    def _owner(context: RequestContext) -> dict[str, int]:
        return {"usuario_id": context.usuario_id, "empresa_id": context.empresa_id}

    def ensure_indexes(self) -> None:
        for collection in (self.sessions, self.messages):
            for index_name, details in collection.index_information().items():
                if "expireAfterSeconds" in details:
                    collection.drop_index(index_name)
        self.sessions.create_index("session_id", unique=True)
        self.sessions.create_index([("empresa_id", 1), ("usuario_id", 1), ("atualizada_em", -1)])
        self.messages.create_index([("session_id", 1), ("criada_em", -1)])
        if self.qdrant is not None:
            self._ensure_vector_collection()

    def _ensure_vector_collection(self) -> None:
        if self.qdrant is None:
            return
        name = self.messages_collection_name
        if not self.qdrant.collection_exists(name):
            self.qdrant.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=self.vector_size, distance=models.Distance.COSINE
                ),
            )
        else:
            vectors = self.qdrant.get_collection(name).config.params.vectors
            if (
                not isinstance(vectors, models.VectorParams)
                or vectors.size != self.vector_size
                or vectors.distance != models.Distance.COSINE
            ):
                raise ValueError(
                    f"A collection Qdrant '{name}' não é compatível com "
                    f"vetores cosine de dimensão {self.vector_size}."
                )
        for field_name, schema in (
            ("usuario_id", models.PayloadSchemaType.INTEGER),
            ("empresa_id", models.PayloadSchemaType.INTEGER),
            ("session_id", models.PayloadSchemaType.KEYWORD),
            ("role", models.PayloadSchemaType.KEYWORD),
        ):
            self.qdrant.create_payload_index(
                collection_name=name,
                field_name=field_name,
                field_schema=schema,
                wait=True,
            )
        for message in self.messages.find({"indice_status": "pendente"}).limit(100):
            self._index_message(message)

    def _index_message(self, message: dict[str, Any]) -> None:
        if self.qdrant is None:
            return
        try:
            self.qdrant.upsert(
                collection_name=self.messages_collection_name,
                wait=True,
                points=[models.PointStruct(
                    id=message["_id"],
                    vector=gerar_embedding(message["content"]),
                    payload={
                        "usuario_id": message["usuario_id"],
                        "empresa_id": message["empresa_id"],
                        "session_id": message["session_id"],
                        "role": message["role"],
                    },
                )],
            )
        except Exception:  # noqa: BLE001 - MongoDB é a fonte canônica
            logger.exception("Não foi possível indexar mensagem no Qdrant.")
        else:
            self.messages.update_one(
                {"_id": message["_id"]}, {"$set": {"indice_status": "sincronizado"}}
            )

    def ensure_session(
        self, context: RequestContext, session_id: str, metadata: dict[str, Any] | None = None
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
                "$set": {"status": "aberta", "atualizada_em": now},
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
        document = {
            "_id": str(uuid4()),
            "session_id": session_id,
            **self._owner(context),
            "role": role,
            "content": sanitize_text(content)[:8000],
            "agent": agent,
            "metadata": metadata,
            "indice_status": "pendente" if self.qdrant is not None else "nao_configurado",
            "criada_em": datetime.now(UTC),
        }
        self.messages.insert_one(document)
        self.sessions.update_one(
            {"session_id": session_id, **self._owner(context)},
            {"$inc": {"total_mensagens": 1}, "$set": {"atualizada_em": document["criada_em"]}},
        )
        if role == "usuario":
            title = _session_title(document["content"])
            if title:
                self.sessions.update_one(
                    {"session_id": session_id, **self._owner(context), "titulo": {"$in": [None, ""]}},
                    {"$set": {"titulo": title}},
                )
        if self.qdrant is not None:
            self._index_message(document)
            document["indice_status"] = self.messages.find_one(
                {"_id": document["_id"]}, {"indice_status": 1}
            )["indice_status"]
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
            .limit(min(max(limit, 1), MAX_CONTEXT_MESSAGES))
        )
        messages.reverse()
        return session, serialize(messages)

    def list_messages(self, context: RequestContext, session_id: str, limit: int) -> list[dict[str, Any]]:
        if self._existing_session(context, session_id) is None:
            raise NotFoundError("Sessão não encontrada.")
        messages = list(
            self.messages.find({"session_id": session_id, **self._owner(context)})
            .sort([("criada_em", -1), ("_id", -1)])
            .limit(min(max(limit, 1), 100))
        )
        messages.reverse()
        return serialize(messages)

    def summary_material(
        self, context: RequestContext, session_id: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        session = self._existing_session(context, session_id)
        if session is None:
            return {"session_id": session_id, "resumo": ""}, []
        query: dict[str, Any] = {"session_id": session_id, **self._owner(context)}
        if session.get("resumido_ate"):
            query["criada_em"] = {"$gt": session["resumido_ate"]}
        return session, serialize(list(self.messages.find(query).sort("criada_em", 1)))

    def _existing_session(self, context: RequestContext, session_id: str) -> dict[str, Any] | None:
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
        chats = serialize(list(
            self.sessions.find({**self._owner(context), "total_mensagens": {"$gt": 0}})
            .sort("atualizada_em", -1).limit(limit)
        ))
        for chat in chats:
            if chat.get("titulo"):
                continue
            first_message = next(iter(self.messages.find({
                "session_id": chat["session_id"], **self._owner(context), "role": "usuario"
            }).sort([("criada_em", 1), ("_id", 1)]).limit(1)), None)
            if first_message:
                title = _session_title(first_message.get("content", ""))
                if title:
                    self.sessions.update_one(
                        {"session_id": chat["session_id"], **self._owner(context)},
                        {"$set": {"titulo": title}},
                    )
                    chat["titulo"] = title
        return chats

    def update_summary(
        self, context: RequestContext, session_id: str, summary: str, summarized_until: datetime
    ) -> None:
        result = self.sessions.update_one(
            {"session_id": session_id, **self._owner(context)},
            {"$set": {"resumo": sanitize_text(summary)[:12000], "resumido_ate": summarized_until,
                      "atualizada_em": datetime.now(UTC)}},
        )
        if result.matched_count == 0:
            raise NotFoundError("Sessão não encontrada.")

