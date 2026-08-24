"""Configuração e infraestrutura compartilhadas do MongoDB."""

from datetime import UTC, datetime

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection

from config import MONGODB_DB_NAME, MONGODB_SESSIONS_COLLECTION, MONGODB_URI

__all__ = [
    "MONGODB_DB_NAME",
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
        [("user_id", ASCENDING), ("iniciada_em", DESCENDING)],
        name="idx_user_id_iniciada_em",
    )
    col.create_index(
        [("status", ASCENDING), ("atualizada_em", DESCENDING)],
        name="idx_status_atualizada_em",
    )
    col.create_index(
        [("mensagens.agent", ASCENDING)],
        name="idx_mensagens_agent",
    )
