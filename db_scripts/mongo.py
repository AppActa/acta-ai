"""Configuração e infraestrutura compartilhadas do MongoDB."""

from datetime import UTC, datetime

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection

from config import (
    ACTA_SYSTEM_FEATURES_DB_NAME,
    MONGODB_MESSAGES_COLLECTION,
    MONGODB_SESSIONS_COLLECTION,
    MONGODB_URI,
)

__all__ = [
    "ACTA_SYSTEM_FEATURES_DB_NAME",
    "MONGODB_MESSAGES_COLLECTION",
    "MONGODB_SESSIONS_COLLECTION",
    "MONGODB_URI",
    "agora",
    "criar_cliente_mongo",
    "criar_indices_chat_sessoes",
]


def agora() -> datetime:
    """Retorna a data e hora atual em UTC para documentos do MongoDB."""

    return datetime.now(UTC)


def criar_cliente_mongo() -> MongoClient:
    """Cria um cliente MongoDB com o timeout padrão da aplicação."""

    return MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=5000,
    )


def criar_indices_chat_sessoes(col: Collection) -> None:
    """Cria ou valida todos os índices da collection de sessões."""

    col.create_index(
        [("session_id", ASCENDING)],
        unique=True,
        name="idx_session_id_unique",
    )
    col.create_index(
        [("empresa_id", ASCENDING), ("usuario_id", ASCENDING), ("atualizada_em", DESCENDING)],
        name="idx_empresa_usuario_atualizada",
    )
    col.create_index(
        [("status", ASCENDING), ("atualizada_em", DESCENDING)],
        name="idx_status_atualizada_em",
    )


def criar_indices_chat_mensagens(col: Collection) -> None:
    col.create_index(
        [("session_id", ASCENDING), ("criada_em", DESCENDING)],
        name="idx_session_criada_em",
    )
