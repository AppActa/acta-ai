from functools import lru_cache

from pymongo import MongoClient

from clients.mcp_acta_client import MCPRequestContext
from config import (
    ACTA_MEMORY_INFERRED_RETENTION_DAYS,
    ACTA_MEMORY_MESSAGE_RETENTION_DAYS,
    ACTA_MEMORY_RECENT_MESSAGES,
    ACTA_MEMORY_SUMMARY_EVERY_MESSAGES,
    ACTA_SYSTEM_FEATURES_DB_NAME,
    MONGODB_URI,
    QDRANT_API_KEY,
    QDRANT_CLUSTER_ENDPOINT,
    QDRANT_MEMORY_COLLECTION_NAME,
    QDRANT_MEMORY_MESSAGES_COLLECTION_NAME,
    QDRANT_MEMORY_VECTOR_SIZE,
    QDRANT_TIMEOUT_SECONDS,
)
from agents.helpers.memory.repository import MemoryRepository
from agents.helpers.memory.service import MemoryService
from agents.helpers.skills.repository import SkillsRepository
from agents.helpers.skills.service import SkillsService


@lru_cache(maxsize=1)
def _mongo_database():
    return MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)[ACTA_SYSTEM_FEATURES_DB_NAME]


@lru_cache(maxsize=1)
def _qdrant_client():
    if not (QDRANT_CLUSTER_ENDPOINT and QDRANT_API_KEY):
        return None
    from qdrant_client import QdrantClient

    return QdrantClient(
        url=QDRANT_CLUSTER_ENDPOINT,
        api_key=QDRANT_API_KEY,
        timeout=QDRANT_TIMEOUT_SECONDS,
        cloud_inference=False,
    )


@lru_cache(maxsize=1)
def get_memory_service() -> MemoryService:
    repository = MemoryRepository(
        _mongo_database(),
        _qdrant_client(),
        messages_collection_name=QDRANT_MEMORY_MESSAGES_COLLECTION_NAME,
        memories_collection_name=QDRANT_MEMORY_COLLECTION_NAME,
        vector_size=QDRANT_MEMORY_VECTOR_SIZE,
        message_retention_days=ACTA_MEMORY_MESSAGE_RETENTION_DAYS,
        inferred_retention_days=ACTA_MEMORY_INFERRED_RETENTION_DAYS,
    )
    repository.ensure_indexes()
    return MemoryService(
        repository,
        recent_messages=ACTA_MEMORY_RECENT_MESSAGES,
        summary_every_messages=ACTA_MEMORY_SUMMARY_EVERY_MESSAGES,
    )


@lru_cache(maxsize=1)
def get_skills_service() -> SkillsService:
    service = SkillsService(SkillsRepository(_mongo_database()))
    service.ensure_indexes()
    return service


def current_identity() -> MCPRequestContext:
    from clients.mcp_acta_client import current_mcp_request_context

    return current_mcp_request_context()
