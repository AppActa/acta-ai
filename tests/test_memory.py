from langchain_core.messages import AIMessage

import agents.estado as state_module
from clients import mcp_acta_client


def test_explicit_preference_is_registered_without_llm(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "clients.memory_client.registrar_memoria",
        lambda **kwargs: calls.append(kwargs),
    )

    state_module._registrar_memorias_explicitas(
        "session-1", "Eu prefiro respostas curtas e objetivas."
    )

    assert calls == [
        {
            "tipo": "preferencia",
            "conteudo": "respostas curtas e objetivas",
            "session_id": "session-1",
        }
    ]


def test_summary_and_inferred_memories_are_consolidated_in_one_llm_call(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "clients.memory_client.obter_material_resumo",
        lambda _: {
            "deve_resumir": True,
            "resumo_anterior": "Resumo anterior",
            "conversa_formatada": "usuario: A entrega ficou para sexta.",
            "resumido_ate": "2026-08-01T12:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        "clients.memory_client.atualizar_resumo",
        lambda *args: calls.append(("resumo", args)),
    )
    monkeypatch.setattr(
        "clients.memory_client.registrar_memoria",
        lambda **kwargs: calls.append(("memoria", kwargs)),
    )

    class FakeLLM:
        def invoke(self, _):
            return AIMessage(
                content=(
                    '{"resumo":"Entrega combinada para sexta.",'
                    '"memorias":[{"tipo":"decisao","conteudo":"Entrega na sexta",'
                    '"confianca":0.9}]}'
                )
            )

    monkeypatch.setattr(state_module, "llm", FakeLLM())
    state_module.consolidar_memoria("session-1")

    assert calls[0][0] == "resumo"
    assert calls[1] == (
        "memoria",
        {
            "tipo": "decisao",
            "conteudo": "Entrega na sexta",
            "origem": "inferida",
            "confianca": 0.9,
            "session_id": "session-1",
        },
    )


def test_local_checkpointer_scope_isolated_by_authenticated_owner() -> None:
    with mcp_acta_client.mcp_request_context(usuario_id=1, empresa_id=2):
        first = mcp_acta_client.mcp_identity_scope()
    with mcp_acta_client.mcp_request_context(usuario_id=2, empresa_id=2):
        second = mcp_acta_client.mcp_identity_scope()

    assert first != second
    assert first == "empresa:2:usuario:1"
