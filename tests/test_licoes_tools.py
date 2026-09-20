from clients import a2a_client
from clients.mcp_acta_client import mcp_request_context
from tools.ciclo_tools import TOOLS as CICLO_TOOLS


def test_create_lesson_tool_forwards_only_agent_authored_fields(monkeypatch) -> None:
    from tools.licoes_tools import criar_licao_aprendida

    received = []
    monkeypatch.setattr(
        "tools.licoes_tools.enviar_pedido_licao",
        lambda **data: received.append(data) or {"status": "ok", "mensagem": "Criada."},
    )

    with mcp_request_context(usuario_id=3, empresa_id=4), a2a_client.a2a_lesson_context(
        id_ciclo=7
    ):
        result = criar_licao_aprendida.invoke(
            {
                "contexto": "Síntese criada pelo agente de ciclos.",
                "expectativa": "Evitar a recorrência do problema.",
            }
        )

    assert result == {"status": "ok", "mensagem": "Criada."}
    assert received == [
        {
            "skill": "criar_licao",
            "payload": {
                "contexto": "Síntese criada pelo agente de ciclos.",
                "expectativa": "Evitar a recorrência do problema.",
            },
        }
    ]


def test_cycle_mcp_tools_do_not_offer_the_legacy_lesson_writer() -> None:
    assert "licoes_aprendidas_registrar" not in {tool.name for tool in CICLO_TOOLS}
