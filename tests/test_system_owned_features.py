from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage

import agents.agents as agent_tools
import clients.memory_client as memory_client
from clients import mcp_acta_client


def test_memory_facade_uses_system_service_instead_of_mcp(monkeypatch):
    calls = []

    class MemoryService:
        def garantir_sessao(self, context, *, session_id, metadata=None):
            calls.append((context.usuario_id, context.empresa_id, session_id, metadata))
            return None

    monkeypatch.setattr(memory_client, "get_memory_service", lambda: MemoryService(), raising=False)
    monkeypatch.setattr(
        memory_client,
        "call_acta_tool",
        lambda *_args, **_kwargs: pytest.fail("memória não deve chamar o MCP"),
        raising=False,
    )

    with mcp_acta_client.mcp_request_context(usuario_id=7, empresa_id=3):
        memory_client.garantir_sessao("session-1", {"origem": "teste"})

    assert calls == [(7, 3, "session-1", {"origem": "teste"})]


def test_faq_agent_uses_mcp_tool(monkeypatch):
    calls = []
    monkeypatch.setattr(
        agent_tools,
        "call_acta_tool",
        lambda name, arguments: calls.append((name, arguments))
        or {
            "status": "ok",
            "resultados": [{"source": "ACTA_DOCS::pdca", "title": "PDCA", "content": "Contexto PDCA"}],
        },
    )
    monkeypatch.setattr(
        agent_tools,
        "llm",
        Mock(invoke=lambda prompt: AIMessage(content=f"Resposta baseada em {prompt}")),
    )

    result = agent_tools.responder_faq("Como funciona o PDCA?")

    assert "Contexto PDCA" in result
    assert calls == [("faq_retriever", {"question": "Como funciona o PDCA?", "limit": 3})]


def test_conversation_memory_facades_call_the_system_service(monkeypatch):
    service = Mock()
    service.garantir_sessao.return_value = None
    service.salvar_mensagem.return_value = None
    service.obter_contexto.return_value = {"contexto": "contexto"}
    service.material_resumo.return_value = {"deve_resumir": True}
    service.encerrar_sessao.return_value = True
    service.listar_chats.return_value = [{"session_id": "s"}]
    service.listar_mensagens.return_value = [{"_id": "m"}]
    service.atualizar_resumo.return_value = None
    monkeypatch.setattr(memory_client, "get_memory_service", lambda: service)

    with mcp_acta_client.mcp_request_context(usuario_id=7, empresa_id=3):
        memory_client.garantir_sessao("s")
        memory_client.salvar_mensagem(session_id="s", role="human", content="Oi", agent="teste")
        assert memory_client.obter_contexto_detalhado("s")["contexto"] == "contexto"
        assert memory_client.obter_contexto("s") == "contexto"
        assert memory_client.obter_material_resumo("s")["deve_resumir"] is True
        assert memory_client.encerrar_sessao("s") is True
        assert memory_client.listar_chats()[0]["session_id"] == "s"
        memory_client.atualizar_resumo("s", "resumo", "2026-09-01T00:00:00+00:00")
        assert memory_client.listar_mensagens("s")[0]["_id"] == "m"

    assert service.garantir_sessao.call_count == 1
    assert service.salvar_mensagem.call_args.kwargs["role"] == "usuario"
    assert service.obter_contexto.call_count == 2
    assert service.material_resumo.call_count == 1
    assert service.encerrar_sessao.call_count == 1
    assert service.listar_chats.call_count == 1
    assert service.atualizar_resumo.call_args.kwargs["resumido_ate"].isoformat() == (
        "2026-09-01T00:00:00+00:00"
    )
    assert service.listar_mensagens.call_args.kwargs == {"session_id": "s", "limit": 30}
