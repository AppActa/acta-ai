from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.database import Database

from clients.mcp_acta_client import MCPRequestContext as RequestContext
from agents.helpers.serialization import serialize
from agents.helpers.skills.schemas import SkillDefinition


class SkillsRepository:
    def __init__(self, database: Database) -> None:
        self.collection = database["skills_usuario"]

    @staticmethod
    def _owner(context: RequestContext) -> dict[str, int]:
        return {"usuario_id": context.usuario_id, "empresa_id": context.empresa_id}

    def ensure_indexes(self) -> None:
        self.collection.create_index(
            [("empresa_id", 1), ("usuario_id", 1), ("slug", 1)],
            unique=True,
            name="skill_owner_slug_unique",
        )
        self.collection.create_index(
            [("empresa_id", 1), ("usuario_id", 1), ("status", 1), ("atualizada_em", -1)],
            name="skill_owner_status_updated",
        )

    def upsert(self, context: RequestContext, definition: SkillDefinition) -> dict[str, Any]:
        now = datetime.now(UTC)
        document = self.collection.find_one_and_update(
            {**self._owner(context), "slug": definition.slug},
            {
                "$setOnInsert": {
                    "_id": str(uuid4()),
                    **self._owner(context),
                    "criada_em": now,
                },
                "$set": {
                    **definition.model_dump(),
                    "status": "ativa",
                    "atualizada_em": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return serialize(document)

    def get(self, context: RequestContext, slug: str) -> dict[str, Any] | None:
        document = self.collection.find_one(
            {**self._owner(context), "slug": slug, "status": "ativa"}
        )
        return serialize(document) if document is not None else None

    def list(self, context: RequestContext, limit: int) -> list[dict[str, Any]]:
        documents = list(
            self.collection.find({**self._owner(context), "status": "ativa"})
            .sort("atualizada_em", -1)
            .limit(limit)
        )
        return serialize(documents)

    def delete(self, context: RequestContext, slug: str) -> bool:
        result = self.collection.update_one(
            {**self._owner(context), "slug": slug, "status": "ativa"},
            {"$set": {"status": "excluida", "excluida_em": datetime.now(UTC)}},
        )
        return result.matched_count == 1

