from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from qdrant_client import models

from agents.helpers.errors import AuthorizationError, NotFoundError
from agents.helpers.memory.repository import MemoryRepository
from clients.mcp_acta_client import MCPRequestContext as RequestContext

CONTEXT = RequestContext(usuario_id=7, empresa_id=3, trace_id="memory-test")


class Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *_args):
        return self

    def limit(self, amount):
        self.docs = self.docs[:amount]
        return self

    def __iter__(self):
        return iter(self.docs)


class Collection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.indexes = []
        self.index_info = {}
        self.updates = []
        self.inserted = []
        self.find_one_result = None
        self.matched_count = 1

    def create_index(self, *args, **kwargs):
        self.indexes.append((args, kwargs))

    def index_information(self):
        return self.index_info

    def drop_index(self, name):
        self.dropped_index = name

    def find(self, query=None, *_args, **_kwargs):
        return Cursor(self.docs)

    def find_one(self, query=None, *_args, **_kwargs):
        if self.find_one_result is not None:
            return self.find_one_result
        return next((item for item in self.docs if not query or all(item.get(k) == v for k, v in query.items())), None)

    def update_one(self, query, update, **_kwargs):
        self.updates.append((query, update))
        return SimpleNamespace(matched_count=self.matched_count)

    def insert_one(self, doc):
        self.inserted.append(doc)


class Database:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, Collection())


class Qdrant:
    def __init__(self, dimension=768, fail_upsert=False, exists=True):
        self.dimension = dimension
        self.fail_upsert = fail_upsert
        self.exists = exists
        self.points = []
        self.payload_indexes = []
        self.created = []

    def collection_exists(self, _name):
        return self.exists

    def get_collection(self, _name):
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=models.VectorParams(size=self.dimension, distance=models.Distance.COSINE))))

    def create_collection(self, **kwargs):
        self.created.append(kwargs)

    def create_payload_index(self, **kwargs):
        self.payload_indexes.append(kwargs)

    def upsert(self, **kwargs):
        if self.fail_upsert:
            raise RuntimeError("Qdrant indisponível")
        self.points.extend(kwargs["points"])

    def query_points(self, **kwargs):
        self.query = kwargs
        return SimpleNamespace(points=self.search_results)


def repository(qdrant=None):
    database = Database()
    return MemoryRepository(database, qdrant, messages_collection_name="memoria_mensagens", vector_size=768), database


def test_repository_uses_only_sessions_and_messages_and_drops_old_ttl_indexes():
    repo, db = repository()
    db["memoria_sessoes"].index_info = {"expira_em_1": {"expireAfterSeconds": 0}}
    db["memoria_mensagens"].index_info = {"expira_em_1": {"expireAfterSeconds": 0}}

    repo.ensure_indexes()

    assert set(db.collections) == {"memoria_sessoes", "memoria_mensagens"}
    assert db["memoria_sessoes"].dropped_index == "expira_em_1"
    assert db["memoria_mensagens"].dropped_index == "expira_em_1"
    assert all("expireAfterSeconds" not in opts for _, opts in db["memoria_mensagens"].indexes)


def test_qdrant_collection_dimension_must_match():
    repo, _ = repository(Qdrant(dimension=384))
    with pytest.raises(ValueError, match="dimensão 768"):
        repo._ensure_vector_collection()


def test_message_is_saved_without_expiry_and_indexed_in_qdrant(monkeypatch):
    qdrant = Qdrant()
    repo, db = repository(qdrant)
    repo.ensure_session = lambda *_args, **_kwargs: {}
    db["memoria_mensagens"].find_one_result = {"indice_status": "sincronizado"}
    monkeypatch.setattr("agents.helpers.memory.repository.gerar_embedding", lambda _: [0.5] * 768)

    message = repo.add_message(CONTEXT, session_id="s1", role="usuario", content="Olá", agent=None, metadata={})

    assert message["indice_status"] == "sincronizado"
    assert "expira_em" not in db["memoria_mensagens"].inserted[0]
    assert qdrant.points[0].payload["session_id"] == "s1"


def test_qdrant_failure_keeps_message_in_mongo(monkeypatch):
    repo, db = repository(Qdrant(fail_upsert=True))
    repo.ensure_session = lambda *_args, **_kwargs: {}
    db["memoria_mensagens"].find_one_result = {"indice_status": "pendente"}
    monkeypatch.setattr("agents.helpers.memory.repository.gerar_embedding", lambda _: [0.5] * 768)

    message = repo.add_message(CONTEXT, session_id="s1", role="usuario", content="Olá", agent=None, metadata={})

    assert message["content"] == "Olá"
    assert message["indice_status"] == "pendente"
    assert len(db["memoria_mensagens"].inserted) == 1


def test_context_load_is_capped_at_30_messages_and_owner_is_checked():
    repo, db = repository()
    db["memoria_sessoes"].find_one_result = {"session_id": "s1", "usuario_id": 7, "empresa_id": 3, "resumo": "resumo"}
    db["memoria_mensagens"].docs = [{"_id": f"m{i}"} for i in range(40)]

    session, messages = repo.session_context(CONTEXT, "s1", limit=100)

    assert session["resumo"] == "resumo"
    assert len(messages) == 30
    db["memoria_sessoes"].find_one_result = {"session_id": "s1", "usuario_id": 99, "empresa_id": 3}
    with pytest.raises(AuthorizationError):
        repo.session_context(CONTEXT, "s1", 30)


def test_semantic_search_loads_owned_messages_from_other_sessions(monkeypatch):
    qdrant = Qdrant()
    qdrant.search_results = [
        SimpleNamespace(id="m1", score=0.91),
        SimpleNamespace(id="current", score=0.89),
        SimpleNamespace(id="foreign", score=0.87),
    ]
    repo, db = repository(qdrant)
    db["memoria_mensagens"].docs = [
        {"_id": "m1", "session_id": "old", "usuario_id": 7, "empresa_id": 3,
         "role": "assistente", "content": "A empresa está no Lucro Real."},
        {"_id": "current", "session_id": "current-session", "usuario_id": 7,
         "empresa_id": 3, "role": "usuario", "content": "mensagem atual"},
        {"_id": "foreign", "session_id": "old", "usuario_id": 8, "empresa_id": 3,
         "role": "assistente", "content": "dado de outro usuário"},
    ]
    db["memoria_sessoes"].docs = [
        {"session_id": "old", "usuario_id": 7, "empresa_id": 3, "titulo": "Tributação", "resumo": "Contexto fiscal"}
    ]
    monkeypatch.setattr("agents.helpers.memory.repository.gerar_embedding", lambda _: [0.5] * 768)

    memories = repo.search_relevant_memories(CONTEXT, session_id="current-session", query="regime tributário")

    assert len(memories) == 1
    assert memories[0]["content"] == "A empresa está no Lucro Real."
    assert memories[0]["titulo"] == "Tributação"
    assert qdrant.query["query_filter"].must_not[0].key == "session_id"
    assert {condition.key for condition in qdrant.query["query_filter"].must} == {"usuario_id", "empresa_id"}


def test_session_creation_close_summary_and_missing_session():
    repo, db = repository()
    db["memoria_sessoes"].find_one_result = {"session_id": "s1", "usuario_id": 7, "empresa_id": 3}
    repo.ensure_session(CONTEXT, "s1")
    assert db["memoria_sessoes"].updates
    assert repo.close_session_if_has_messages(CONTEXT, "s1")
    repo.update_summary(CONTEXT, "s1", "Resumo 123.456.789-00", datetime.now(UTC))
    assert db["memoria_sessoes"].updates[-1][1]["$set"]["resumo"] == "Resumo 123.456.789-00"
    db["memoria_sessoes"].matched_count = 0
    with pytest.raises(NotFoundError):
        repo.update_summary(CONTEXT, "missing", "resumo", datetime.now(UTC))


def test_listing_chats_and_messages():
    repo, db = repository()
    db["memoria_sessoes"].find_one_result = {"session_id": "s1", "usuario_id": 7, "empresa_id": 3}
    db["memoria_sessoes"].docs = [{"session_id": "s1", "usuario_id": 7, "empresa_id": 3, "total_mensagens": 2}]
    db["memoria_mensagens"].docs = [{"_id": "m1", "session_id": "s1", "usuario_id": 7, "empresa_id": 3, "role": "usuario", "content": "Pergunta"}]
    assert repo.list_chats(CONTEXT, 5)[0]["titulo"] == "Pergunta"
    assert repo.list_messages(CONTEXT, "s1", 10)[0]["_id"] == "m1"
    db["memoria_sessoes"].find_one_result = None
    with pytest.raises(NotFoundError):
        repo.list_messages(CONTEXT, "missing", 10)
