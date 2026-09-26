from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from qdrant_client import models

from clients.mcp_acta_client import MCPRequestContext as RequestContext
from utils.errors import AuthorizationError, NotFoundError
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
        self.points = []
        self.created_collections = []
        self.payload_indexes = []

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
        self.payload_indexes.append(_)

    def create_collection(self, **kwargs: object) -> None:
        self.created_collections.append(kwargs)

    def upsert(self, **kwargs: object) -> None:
        self.points.extend(kwargs.get("points", []))

    def query_points(self, **kwargs: object) -> SimpleNamespace:
        self.query = kwargs
        return SimpleNamespace(points=[SimpleNamespace(id="memory-1", score=0.87654321)])

    def delete(self, collection_name: str, **_: object) -> None:
        self.deletions.append(collection_name)


class FakeCollection:
    def __init__(self, documents: list[dict] | None = None) -> None:
        self.documents = documents or []
        self.inserted: list[dict] = []
        self.updates: list[tuple[tuple[object, ...], dict]] = []
        self.update_many_calls = []
        self.delete_many_calls = []
        self.find_calls = []
        self.indexes = []
        self.index_info = {}
        self.matched_count = 1
        self.find_one_result = None

    def create_index(self, *args: object, **kwargs: object) -> None:
        self.indexes.append((args, kwargs))

    def index_information(self) -> dict:
        return self.index_info

    def drop_index(self, name: str) -> None:
        self.dropped_index = name

    def update_one(self, *args: object, **kwargs: object) -> None:
        self.updates.append((args, kwargs))
        return SimpleNamespace(matched_count=self.matched_count)

    def insert_one(self, document: dict) -> None:
        self.inserted.append(document)

    def update_many(self, *args: object, **kwargs: object) -> None:
        self.update_many_calls.append((args, kwargs))

    def delete_many(self, *args: object, **kwargs: object) -> None:
        self.delete_many_calls.append((args, kwargs))

    def find(self, *args: object, **kwargs: object):
        self.find_calls.append((args, kwargs))
        return FakeCursor(self.documents)

    def find_one(self, *_: object, **__: object) -> dict | None:
        if self.find_one_result is not None:
            return self.find_one_result
        return {"usuario_id": 7, "empresa_id": 3, "modo": "desativado", "retencao_dias": None}


class FakeCursor:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = list(documents)

    def sort(self, *_: object) -> "FakeCursor":
        return self

    def limit(self, amount: int) -> "FakeCursor":
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(self.documents)


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


def test_ensure_indexes_reconciles_mongo_and_qdrant_indexes() -> None:
    qdrant = FakeQdrant()
    repository = _repository(qdrant)
    repository.memories = FakeCollection()
    repository.messages = FakeCollection()
    repository.sessions = FakeCollection()
    repository.consents = FakeCollection()
    repository.memories.index_info = {"expira_em_1": {"expireAfterSeconds": 0}}

    repository.ensure_indexes()

    assert repository.memories.dropped_index == "expira_em_1"
    assert len(repository.sessions.indexes) == 3
    assert len(repository.messages.indexes) == 2
    assert len(repository.memories.indexes) == 2
    assert len(repository.consents.indexes) == 1
    assert len(qdrant.payload_indexes) == 10


def test_session_context_and_summary_material_enforce_owner_and_order() -> None:
    repository = _repository(None)
    repository.cleanup_expired = lambda *_args, **_kwargs: 0  # type: ignore[method-assign]
    repository.sessions.find_one_result = {
        "session_id": "session-1",
        "usuario_id": 7,
        "empresa_id": 3,
        "resumo": "Resumo atual",
        "resumido_ate": "2026-01-01T00:00:00+00:00",
    }
    repository.messages.documents = [{"_id": "message-1", "content": "Mensagem"}]

    session, messages = repository.session_context(CONTEXT, "session-1", limit=5)
    summary_session, material = repository.summary_material(CONTEXT, "session-1")

    assert session["resumo"] == "Resumo atual"
    assert messages == [{"_id": "message-1", "content": "Mensagem"}]
    assert summary_session["session_id"] == "session-1"
    assert material[0]["content"] == "Mensagem"
    assert repository.messages.find_calls[-1][0][0]["criada_em"]["$gt"]


def test_existing_session_rejects_a_different_owner() -> None:
    repository = _repository(None)
    repository.sessions.find_one_result = {
        "session_id": "session-1",
        "usuario_id": 999,
        "empresa_id": 3,
    }

    with pytest.raises(AuthorizationError, match="não pertence ao usuário autenticado"):
        repository._existing_session(CONTEXT, "session-1")


def test_session_close_summary_update_and_consent_paths() -> None:
    repository = _repository(None)
    repository.sessions.matched_count = 1
    repository.consents.find_one_result = {
        "usuario_id": 7,
        "empresa_id": 3,
        "modo": "automatica",
        "retencao_dias": 20,
    }

    assert repository.close_session_if_has_messages(CONTEXT, "session-1") is True
    repository.update_summary(CONTEXT, "session-1", "Resumo 123.456.789-00", datetime.now(UTC))
    assert repository.sessions.updates[-1][0][1]["$set"]["resumo"] == "Resumo [CPF OMITIDO]"
    assert repository.get_consent(CONTEXT)["modo"] == "automatica"
    assert repository.set_consent(CONTEXT, "automatica", 20)["retencao_dias"] == 20

    repository.sessions.matched_count = 0
    assert repository.close_session_if_has_messages(CONTEXT, "session-1") is False
    with pytest.raises(NotFoundError, match="Sessão não encontrada"):
        repository.update_summary(CONTEXT, "missing", "Resumo", datetime.now(UTC))


def test_list_and_semantic_search_return_only_matching_memory_documents(monkeypatch) -> None:
    qdrant = FakeQdrant()
    repository = _repository(qdrant)
    repository.cleanup_expired = lambda *_args, **_kwargs: 0  # type: ignore[method-assign]
    repository.memories.documents = [
        {"_id": "memory-1", "usuario_id": 7, "empresa_id": 3, "status": "ativa"}
    ]
    monkeypatch.setattr(memory_repository, "gerar_embedding", lambda _: [0.25] * 768)

    listed = repository.list_memories(CONTEXT, tipo="preferencia", limit=3)
    found = repository.semantic_search(CONTEXT, "como prefiro", limit=4)

    assert listed[0]["_id"] == "memory-1"
    assert repository.memories.find_calls[0][0][0]["tipo"] == "preferencia"
    assert found == [{"_id": "memory-1", "usuario_id": 7, "empresa_id": 3, "status": "ativa", "score": 0.876543}]
    assert qdrant.query["limit"] == 4


def test_delete_memory_soft_deletes_and_removes_vector() -> None:
    qdrant = FakeQdrant()
    repository = _repository(qdrant)

    assert repository.delete_memory(CONTEXT, "memory-1") is True
    assert qdrant.deletions == ["memoria_usuario"]

    repository.memories.matched_count = 0
    assert repository.delete_memory(CONTEXT, "missing") is False


def test_index_creation_and_successful_message_vector_sync(monkeypatch) -> None:
    class MissingCollectionQdrant(FakeQdrant):
        def collection_exists(self, _: str) -> bool:
            return False

    qdrant = MissingCollectionQdrant()
    repository = _repository(qdrant)
    repository.message_retention_days = 90
    repository.ensure_session = lambda *_args, **_kwargs: {}  # type: ignore[method-assign]
    monkeypatch.setattr(memory_repository, "gerar_embedding", lambda _: [0.5] * 768)

    repository._ensure_vector_collection("memoria_usuario")
    message = repository.add_message(
        CONTEXT,
        session_id="session-1",
        role="usuario",
        content="Meu e-mail é contato@example.com",
        agent=None,
        metadata={},
    )

    assert qdrant.created_collections[0]["collection_name"] == "memoria_usuario"
    assert len(qdrant.points) == 1
    assert message["indice_status"] == "sincronizado"
    assert "contato@example.com" not in message["content"]
