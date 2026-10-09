from datetime import UTC, datetime

import pytest

from agents.helpers.memory.service import MemoryService
from clients.mcp_acta_client import MCPRequestContext as RequestContext


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.qdrant = None
        self.consent = {"modo": "somente_explicitas", "retencao_dias": None}
        self.memories = []
        self.summary = ""
        self.summary_messages = [
            {
                "role": "usuario",
                "content": f"Mensagem {index}",
                "criada_em": datetime.now(UTC).isoformat(),
            }
            for index in range(4)
        ]
        self.chats = []
        self.last_list_limit = None
        self.messages = []
        self.last_message_limit = None
        self.semantic_queries = []

    def ensure_session(self, context, session_id, metadata=None):
        return {"session_id": session_id, "resumo": self.summary}

    def add_message(self, context, **kwargs):
        return {"_id": "message-1", **kwargs}

    def session_context(self, context, session_id, limit):
        return (
            {"session_id": session_id, "resumo": self.summary},
            [{"role": "usuario", "content": "Prefiro respostas curtas", "agent": None}],
        )

    def summary_material(self, context, session_id):
        return {"session_id": session_id, "resumo": self.summary}, self.summary_messages

    def close_session_if_has_messages(self, context, session_id):
        return bool(self.summary_messages)

    def list_chats(self, context, limit):
        self.last_list_limit = limit
        return self.chats

    def list_messages(self, context, session_id, limit):
        self.last_message_limit = limit
        return self.messages

    def update_summary(self, context, session_id, summary, summarized_until):
        self.summary = summary

    def get_consent(self, context):
        return self.consent

    def set_consent(self, context, modo, retencao_dias):
        self.consent = {"modo": modo, "retencao_dias": retencao_dias}
        return self.consent

    def store_memory(self, context, data):
        if self.consent["modo"] == "desativado":
            return None
        if data["origem"] == "inferida" and self.consent["modo"] != "automatica":
            return None
        item = {"_id": f"memory-{len(self.memories) + 1}", **data}
        self.memories.append(item)
        return item

    def list_memories(self, context, *, tipo, limit):
        return [item for item in self.memories if tipo is None or item["tipo"] == tipo][:limit]

    def semantic_search(self, context, query, limit):
        self.semantic_queries.append((query, limit))
        return self.memories[:limit]

    def delete_memory(self, context, memory_id):
        return True


CONTEXT = RequestContext(
    usuario_id=7,
    empresa_id=3,
    trace_id="memory-test",
)


def test_context_combines_summary_preferences_and_recent_messages() -> None:
    repository = FakeMemoryRepository()
    repository.qdrant = object()
    repository.summary = "Resumo acumulado"
    repository.memories.append(
        {"_id": "memory-1", "tipo": "preferencia", "conteudo": "Respostas curtas"}
    )
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)

    result = service.obter_contexto(CONTEXT, session_id="session-1", pergunta="Como responder?")

    assert "Resumo acumulado" in result["contexto"]
    assert "Respostas curtas" in result["contexto"]
    assert "Últimas mensagens" in result["contexto"]
    assert repository.semantic_queries == [("Como responder?", 6)]


def test_inferred_memory_requires_automatic_consent() -> None:
    repository = FakeMemoryRepository()
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)

    blocked = service.registrar(
        CONTEXT,
        tipo="ponto_relevante",
        conteudo="Há uma pendência",
        origem="inferida",
    )
    assert blocked is False

    service.configurar_consentimento(CONTEXT, modo="automatica")
    stored = service.registrar(
        CONTEXT,
        tipo="ponto_relevante",
        conteudo="Há uma pendência",
        origem="inferida",
    )
    assert stored is True


def test_memory_search_falls_back_to_mongo_when_qdrant_is_not_configured() -> None:
    repository = FakeMemoryRepository()
    repository.qdrant = None
    repository.memories.append({"_id": "memory-1", "tipo": "decisao"})
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)

    result = service.buscar(CONTEXT, pergunta="atrasos")

    assert result == repository.memories
    assert repository.semantic_queries == []


def test_memory_search_falls_back_to_mongo_when_qdrant_fails() -> None:
    repository = FakeMemoryRepository()
    repository.qdrant = object()
    repository.memories.append({"_id": "memory-1", "tipo": "decisao"})
    repository.semantic_search = lambda *_args: (_ for _ in ()).throw(
        ConnectionError("Qdrant unavailable")
    )
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)

    result = service.buscar(CONTEXT, pergunta="atrasos")

    assert result == repository.memories


def test_successful_empty_qdrant_search_does_not_fall_back_to_mongo() -> None:
    repository = FakeMemoryRepository()
    repository.qdrant = object()
    repository.memories.append({"_id": "memory-1", "tipo": "decisao"})
    repository.semantic_search = lambda *_args: []
    repository.list_memories = lambda *_args, **_kwargs: pytest.fail(
        "An empty semantic result must stay empty"
    )
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)

    result = service.buscar(CONTEXT, pergunta="atrasos")

    assert result == []


def test_summary_is_incremental_and_threshold_based() -> None:
    service = MemoryService(FakeMemoryRepository(), recent_messages=8, summary_every_messages=4)

    material = service.material_resumo(CONTEXT, session_id="session-1")

    assert material["deve_resumir"] is True
    assert material["resumido_ate"] is not None
    assert "Mensagem 3" in material["conversa_formatada"]


def test_forced_summary_uses_nonempty_conversation_below_threshold() -> None:
    repository = FakeMemoryRepository()
    repository.summary_messages = repository.summary_messages[:1]
    service = MemoryService(repository, recent_messages=8, summary_every_messages=10)

    material = service.material_resumo(CONTEXT, session_id="session-1", forcar=True)

    assert material["tem_mensagens"] is True
    assert material["deve_resumir"] is True


def test_close_empty_session_does_not_close_a_chat() -> None:
    repository = FakeMemoryRepository()
    repository.summary_messages = []
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)

    result = service.encerrar_sessao(CONTEXT, session_id="missing")

    assert result is False


def test_list_chats_clamps_limit_and_returns_repository_results() -> None:
    repository = FakeMemoryRepository()
    repository.chats = [{"session_id": "recent", "total_mensagens": 2}]
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)

    result = service.listar_chats(CONTEXT, limit=999)

    assert result == repository.chats
    assert repository.last_list_limit == 100


def test_list_messages_clamps_limit_and_passes_session_id() -> None:
    repository = FakeMemoryRepository()
    repository.messages = [{"_id": "message-1", "content": "Olá"}]
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)

    result = service.listar_mensagens(CONTEXT, session_id="session-1", limit=999)

    assert result == repository.messages
    assert repository.last_message_limit == 100


def test_disabled_consent_stops_session_persistence_and_retrieval() -> None:
    repository = FakeMemoryRepository()
    repository.consent = {"modo": "desativado", "retencao_dias": None}
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)

    session = service.garantir_sessao(CONTEXT, session_id="session-1")
    message = service.salvar_mensagem(
        CONTEXT,
        session_id="session-1",
        role="usuario",
        content="Não persista isto",
        agent="pytest",
        metadata={},
    )
    context = service.obter_contexto(CONTEXT, session_id="session-1", pergunta="O que foi dito?")

    assert session is None
    assert message is None
    assert context["contexto"] == ""
