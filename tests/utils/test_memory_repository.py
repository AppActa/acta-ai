from types import SimpleNamespace

import pytest
from qdrant_client import models

from clients.mcp_acta_client import MCPRequestContext as RequestContext
from utils.memory import repository as memory_repository
from utils.memory.repository import MemoryRepository

CONTEXT = RequestContext(
    usuario_id=7,
    empresa_id=3,
    trace_id="memory-repository-test",
)


class FakeQdrant:
    def __init__(self, *, vector_size: int = 768) -> None:
        self.vector_size = vector_size
        self.deletions: list[str] = []

    def collection_exists(self, _: str) -> bool:
        return True

    def get_collection(self, _: str) -> SimpleNamespace:
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE,
                    )
                )
            )
        )

    def create_payload_index(self, **_: object) -> None:
        return None

    def delete(self, collection_name: str, **_: object) -> None:
        self.deletions.append(collection_name)


class FakeCollection:
    def __init__(self, documents: list[dict] | None = None) -> None:
        self.documents = documents or []
        self.inserted: list[dict] = []
        self.updates: list[tuple[tuple[object, ...], dict]] = []

    def update_one(self, *args: object, **kwargs: object) -> None:
        self.updates.append((args, kwargs))
        return None

    def insert_one(self, document: dict) -> None:
        self.inserted.append(document)

    def update_many(self, *_: object, **__: object) -> None:
        return None

    def delete_many(self, *_: object, **__: object) -> None:
        return None

    def find(self, *_: object, **__: object) -> list[dict]:
        return self.documents

    def find_one(self, *_: object, **__: object) -> dict:
        return {"usuario_id": 7, "empresa_id": 3, "modo": "desativado", "retencao_dias": None}


def _repository(qdrant: FakeQdrant) -> MemoryRepository:
    repository = object.__new__(MemoryRepository)
    repository.qdrant = qdrant
    repository.vector_size = 768
    repository.messages_collection_name = "memoria_mensagens"
    repository.memories_collection_name = "memoria_usuario"
    repository.consents = FakeCollection()
    repository.memories = FakeCollection([{ "_id": "memory-1" }])
    repository.messages = FakeCollection([{ "_id": "message-1" }])
    repository.sessions = FakeCollection()
    return repository


def test_existing_vector_collection_must_match_configured_dimension() -> None:
    repository = _repository(FakeQdrant(vector_size=384))

    with pytest.raises(ValueError, match="dimensão 768"):
        repository._ensure_vector_collection("memoria_usuario")


def test_disabling_consent_deletes_memory_and_message_vectors() -> None:
    qdrant = FakeQdrant()
    repository = _repository(qdrant)

    repository.set_consent(CONTEXT, "desativado", None)

    assert qdrant.deletions == ["memoria_usuario", "memoria_mensagens"]


def test_cleanup_expired_deletes_memory_and_message_vectors() -> None:
    qdrant = FakeQdrant()
    repository = _repository(qdrant)

    repository.cleanup_expired()

    assert qdrant.deletions == ["memoria_usuario", "memoria_mensagens"]


def test_message_is_kept_in_mongo_when_qdrant_indexing_fails() -> None:
    class FailingQdrant(FakeQdrant):
        def upsert(self, **_: object) -> None:
            raise RuntimeError("Qdrant indisponível")

    repository = _repository(FailingQdrant())
    repository.message_retention_days = 90
    repository.ensure_session = lambda *_args, **_kwargs: {}  # type: ignore[method-assign]

    message = repository.add_message(
        CONTEXT,
        session_id="session-1",
        role="usuario",
        content="Mensagem canônica",
        agent=None,
        metadata={},
    )

    assert message["indice_status"] == "pendente"
    assert repository.messages.inserted[0]["content"] == "Mensagem canônica"
    assert repository.sessions.updates


def test_message_stays_in_mongo_without_configured_qdrant() -> None:
    repository = _repository(None)
    repository.message_retention_days = 90
    repository.ensure_session = lambda *_args, **_kwargs: {}  # type: ignore[method-assign]

    message = repository.add_message(
        CONTEXT,
        session_id="session-1",
        role="usuario",
        content="Mongo sem índice",
        agent=None,
        metadata={},
    )

    assert message["content"] == "Mongo sem índice"
    assert repository.messages.inserted[0]["indice_status"] == "pendente"


def test_memory_is_kept_in_mongo_when_qdrant_indexing_fails() -> None:
    class FailingQdrant(FakeQdrant):
        def upsert(self, **_: object) -> None:
            raise RuntimeError("Qdrant indisponível")

    repository = _repository(FailingQdrant())
    repository.memories = FakeCollection()
    repository.memories.find_one = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    repository.inferred_retention_days = 90
    repository.cleanup_expired = lambda *_args, **_kwargs: 0  # type: ignore[method-assign]
    repository.get_consent = lambda *_args: {"modo": "somente_explicitas"}  # type: ignore[method-assign]

    memory = repository.store_memory(
        CONTEXT,
        {
            "tipo": "objetivo",
            "conteudo": "Memória canônica",
            "origem": "explicita",
            "confianca": 1.0,
            "fonte_session_id": "session-1",
            "metadata": {},
        },
    )

    assert memory is not None
    assert memory["indice_status"] == "pendente"
    assert repository.memories.inserted[0]["conteudo"] == "Memória canônica"


def test_memory_stays_in_mongo_without_configured_qdrant() -> None:
    repository = _repository(None)
    repository.memories = FakeCollection()
    repository.memories.find_one = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    repository.inferred_retention_days = 90
    repository.cleanup_expired = lambda *_args, **_kwargs: 0  # type: ignore[method-assign]
    repository.get_consent = lambda *_args: {"modo": "somente_explicitas"}  # type: ignore[method-assign]

    memory = repository.store_memory(
        CONTEXT,
        {
            "tipo": "objetivo",
            "conteudo": "Memória somente no Mongo",
            "origem": "explicita",
            "confianca": 1.0,
            "fonte_session_id": "session-1",
            "metadata": {},
        },
    )

    assert memory is not None
    assert repository.memories.inserted[0]["conteudo"] == "Memória somente no Mongo"


def test_pending_indexes_are_retried_from_mongo(monkeypatch) -> None:
    class RecoveringQdrant(FakeQdrant):
        def __init__(self) -> None:
            super().__init__()
            self.upserts = 0

        def upsert(self, **_: object) -> None:
            self.upserts += 1

    qdrant = RecoveringQdrant()
    repository = _repository(qdrant)
    repository.messages = FakeCollection(
        [
            {
                "_id": "message-1",
                "content": "Mensagem pendente",
                "usuario_id": 7,
                "empresa_id": 3,
                "session_id": "session-1",
                "role": "usuario",
                "indice_status": "pendente",
            }
        ]
    )
    repository.memories = FakeCollection(
        [
            {
                "_id": "memory-1",
                "conteudo": "Memória pendente",
                "usuario_id": 7,
                "empresa_id": 3,
                "tipo": "objetivo",
                "indice_status": "pendente",
            }
        ]
    )
    monkeypatch.setattr(memory_repository, "gerar_embedding", lambda _: [0.5] * 768)

    repository._retry_pending_indexes()

    assert qdrant.upserts == 2
    assert len(repository.messages.updates) == 1
    assert len(repository.memories.updates) == 1
