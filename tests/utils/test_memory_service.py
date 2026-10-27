from datetime import UTC, datetime

import pytest

from agents.helpers.memory.service import MemoryService
from clients.mcp_acta_client import MCPRequestContext as RequestContext

CONTEXT = RequestContext(usuario_id=7, empresa_id=3, trace_id="memory-test")


class Repository:
    qdrant = None

    def __init__(self):
        self.summary_messages = [{"role": "usuario", "content": f"Mensagem {i}", "criada_em": datetime.now(UTC).isoformat()} for i in range(4)]
        self.summary = "Resumo existente"
        self.last_limit = None
        self.updated = None

    def ensure_indexes(self):
        self.ready = True

    def ensure_session(self, _context, session_id, metadata=None):
        return {"session_id": session_id, "metadata": metadata}

    def add_message(self, _context, **kwargs):
        return {"_id": "m1", **kwargs}

    def session_context(self, _context, session_id, limit):
        self.last_limit = limit
        return {"session_id": session_id, "resumo": self.summary}, self.summary_messages[-limit:]

    def search_relevant_memories(self, _context, **_kwargs):
        return []

    def summary_material(self, _context, session_id):
        return {"session_id": session_id, "resumo": self.summary}, self.summary_messages

    def update_summary(self, _context, _session, summary, until):
        self.updated = (summary, until)

    def close_session_if_has_messages(self, _context, _session):
        return True

    def list_chats(self, _context, limit):
        self.chat_limit = limit
        return [{"session_id": "s1"}]

    def list_messages(self, _context, session, limit):
        self.message_args = (session, limit)
        return [{"_id": "m1"}]


def test_context_includes_summary_recent_messages_and_caps_at_30():
    repository = Repository()
    service = MemoryService(repository, recent_messages=100, summary_every_messages=4)

    context = service.obter_contexto(CONTEXT, session_id="s1")

    assert repository.last_limit == 30
    assert len(context["mensagens_recentes"]) == 4
    assert "Resumo existente" in context["contexto"]
    assert "Últimas mensagens" in context["contexto"]
    assert context["preferencias"] == []
    assert context["memorias_relevantes"] == []


def test_context_searches_and_formats_relevant_memories():
    repository = Repository()
    repository.search_relevant_memories = lambda _context, **kwargs: [
        {"titulo": "Tributação", "role": "assistente", "content": "A empresa está no Lucro Real."}
    ]
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)

    context = service.obter_contexto(CONTEXT, session_id="s1", query="Qual regime tributário?")

    assert len(context["memorias_relevantes"]) == 1
    assert "Memórias relevantes de outras conversas" in context["contexto"]
    assert "A empresa está no Lucro Real." in context["contexto"]


def test_message_session_and_summary_operations():
    repository = Repository()
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)
    assert service.garantir_sessao(CONTEXT, session_id="s1") is None
    assert service.salvar_mensagem(CONTEXT, session_id="s1", role="usuario", content="Oi", agent=None, metadata={}) is None
    material = service.material_resumo(CONTEXT, session_id="s1")
    assert material["deve_resumir"] is True
    assert "Mensagem 3" in material["conversa_formatada"]
    service.atualizar_resumo(CONTEXT, session_id="s1", resumo="novo", resumido_ate=datetime.now(UTC))
    assert repository.updated[0] == "novo"
    with pytest.raises(ValueError, match="resumo é obrigatório"):
        service.atualizar_resumo(CONTEXT, session_id="s1", resumo=" ", resumido_ate=datetime.now(UTC))
    assert service.encerrar_sessao(CONTEXT, session_id="s1") is True


def test_summary_force_and_message_threshold():
    repository = Repository()
    repository.summary_messages = repository.summary_messages[:1]
    service = MemoryService(repository, recent_messages=8, summary_every_messages=10)
    assert service.material_resumo(CONTEXT, session_id="s1")["deve_resumir"] is False
    assert service.material_resumo(CONTEXT, session_id="s1", forcar=True)["deve_resumir"] is True
    repository.summary_messages = []
    assert service.material_resumo(CONTEXT, session_id="s1", forcar=True)["tem_mensagens"] is False


def test_list_operations_clamp_limits():
    repository = Repository()
    service = MemoryService(repository, recent_messages=8, summary_every_messages=4)
    assert service.listar_chats(CONTEXT, limit=999) == [{"session_id": "s1"}]
    assert repository.chat_limit == 100
    assert service.listar_mensagens(CONTEXT, session_id="s1", limit=999) == [{"_id": "m1"}]
    assert repository.message_args == ("s1", 100)
