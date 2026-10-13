from unittest.mock import Mock

import pytest

import agents.agents as agent_tools
import clients.memory_client as memory_client
import clients.skill_client as skill_client
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


def test_skill_facade_uses_system_service_instead_of_mcp(monkeypatch):
    class SkillsService:
        def obter(self, context, *, nome):
            return {"slug": nome, "objetivo": "Resumir"}

    monkeypatch.setattr(skill_client, "get_skills_service", lambda: SkillsService(), raising=False)
    monkeypatch.setattr(
        skill_client,
        "call_acta_tool",
        lambda *_args, **_kwargs: pytest.fail("skills não devem chamar o MCP"),
        raising=False,
    )

    with mcp_acta_client.mcp_request_context(usuario_id=7, empresa_id=3):
        question, skill = skill_client.resolver_comando_skill("/resumo Mostre o andamento")

    assert question == "Mostre o andamento"
    assert skill["slug"] == "resumo"


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
        Mock(invoke=lambda prompt: Mock(content=f"Resposta baseada em {prompt}")),
    )

    result = agent_tools.responder_faq("Como funciona o PDCA?")

    assert "Contexto PDCA" in result
    assert calls == [("faq_retriever", {"question": "Como funciona o PDCA?", "limit": 3})]


def test_all_memory_facade_operations_call_the_system_service(monkeypatch):
    service = Mock()
    service.garantir_sessao.return_value = None
    service.salvar_mensagem.return_value = None
    service.obter_contexto.return_value = {"contexto": "contexto"}
    service.material_resumo.return_value = {"deve_resumir": True}
    service.encerrar_sessao.return_value = True
    service.listar_chats.return_value = [{"session_id": "s"}]
    service.atualizar_resumo.return_value = None
    service.registrar.return_value = True
    service.buscar.return_value = [{"_id": "searched"}]
    service.listar.return_value = [{"_id": "m"}]
    service.excluir.return_value = None
    service.obter_consentimento.return_value = {"modo": "automatica"}
    service.configurar_consentimento.return_value = {"modo": "desativado"}
    monkeypatch.setattr(memory_client, "get_memory_service", lambda: service)

    with mcp_acta_client.mcp_request_context(usuario_id=7, empresa_id=3):
        memory_client.garantir_sessao("s")
        memory_client.salvar_mensagem(session_id="s", role="human", content="Oi", agent="teste")
        assert memory_client.obter_contexto_detalhado("s", "Oi")["contexto"] == "contexto"
        assert memory_client.obter_contexto("s", "Oi") == "contexto"
        assert memory_client.obter_material_resumo("s")["deve_resumir"] is True
        assert memory_client.encerrar_sessao("s") is True
        assert memory_client.listar_chats()[0]["session_id"] == "s"
        memory_client.atualizar_resumo("s", "resumo", "2026-09-01T00:00:00+00:00")
        assert memory_client.registrar_memoria(
            tipo="preferencia", conteudo="curto", session_id="s"
        ) is True
        assert memory_client.buscar_memorias("curto")[0]["_id"] == "searched"
        assert memory_client.listar_memorias()[0]["_id"] == "m"
        memory_client.excluir_memoria("m")
        assert memory_client.obter_consentimento()["modo"] == "automatica"
        assert memory_client.configurar_consentimento("desativado")["modo"] == "desativado"

    assert service.garantir_sessao.call_count == 1
    assert service.salvar_mensagem.call_args.kwargs["role"] == "usuario"
    assert service.obter_contexto.call_count == 2
    assert service.material_resumo.call_count == 1
    assert service.encerrar_sessao.call_count == 1
    assert service.listar_chats.call_count == 1
    assert service.atualizar_resumo.call_args.kwargs["resumido_ate"].isoformat() == (
        "2026-09-01T00:00:00+00:00"
    )
    assert service.registrar.call_args.kwargs["session_id_origem"] == "s"
    assert service.buscar.call_args.kwargs["pergunta"] == "curto"
    assert service.listar.call_count == 1
    assert service.excluir.call_count == 1
    assert service.obter_consentimento.call_count == 1
    assert service.configurar_consentimento.call_count == 1


def test_skill_crud_facades_use_system_service(monkeypatch):
    service = Mock()
    service.criar.return_value = {"slug": "resumo"}
    service.listar.return_value = [{"slug": "resumo"}]
    service.obter.return_value = {"slug": "resumo"}
    service.excluir.return_value = {"excluida": True}
    monkeypatch.setattr(skill_client, "get_skills_service", lambda: service)
    markdown = "# Resumo\n\n# objetivo\n\nResumir resultados.\n\n# regras\n\nUsar tópicos."

    with mcp_acta_client.mcp_request_context(usuario_id=7, empresa_id=3):
        assert skill_client.criar_skill(markdown)["slug"] == "resumo"
        assert skill_client.listar_skills()[0]["slug"] == "resumo"
        assert skill_client.obter_skill("resumo")["slug"] == "resumo"
        assert skill_client.excluir_skill("resumo")["excluida"] is True

    assert service.criar.call_args.kwargs == {"conteudo_markdown": markdown}
    assert service.listar.call_count == 1
    assert service.obter.call_count == 1
    assert service.excluir.call_count == 1
