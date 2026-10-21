from langchain_core.messages import AIMessage

import agents.estado as state_module


def test_summary_is_consolidated_without_creating_separate_memories(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "clients.memory_client.obter_material_resumo",
        lambda *_args, **_kwargs: {
            "deve_resumir": True,
            "resumo_anterior": "Resumo anterior",
            "conversa_formatada": "usuario: Entrega na sexta.",
            "resumido_ate": "2026-08-01T12:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        "clients.memory_client.atualizar_resumo",
        lambda *args: calls.append(args),
    )

    class FakeLLM:
        def invoke(self, _prompt):
            return AIMessage(content='{"resumo":"Entrega combinada para sexta.","memorias":[]}')

    monkeypatch.setattr(state_module, "llm", FakeLLM())
    assert state_module.consolidar_memoria("s1") is True
    assert calls[0][1] == "Entrega combinada para sexta."
