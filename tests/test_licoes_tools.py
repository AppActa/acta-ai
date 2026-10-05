from agents.estado import no_roteador, rotear_deterministicamente
from clients.mcp_acta_client import mcp_request_context
from tools import licoes_tools
from tools.ciclo_tools import TOOLS as CICLO_TOOLS


def test_create_lesson_tool_forwards_only_agent_authored_fields(monkeypatch) -> None:
    from tools.licoes_tools import criar_licao_aprendida

    received = []
    monkeypatch.setattr(
        "tools.licoes_tools.call_acta_tool",
        lambda name, arguments: received.append((name, arguments)) or {"status": "ok", "mensagem": "Criada."},
    )

    with mcp_request_context(usuario_id=3, empresa_id=4), licoes_tools.licoes_context(id_ciclo=7):
        result = criar_licao_aprendida.invoke(
            {
                "contexto": "Síntese criada pelo agente de ciclos.",
                "expectativa": "Evitar a recorrência do problema.",
            }
        )

    assert result == {"status": "ok", "mensagem": "Criada."}
    assert received == [
        (
            "licoes_criar",
            {
                "id_ciclo": 7,
                "contexto": "Síntese criada pelo agente de ciclos.",
                "expectativa": "Evitar a recorrência do problema.",
            },
        ),
    ]


def test_cycle_mcp_tools_do_not_offer_the_legacy_lesson_writer() -> None:
    assert "licoes_aprendidas_registrar" not in {tool.name for tool in CICLO_TOOLS}


def test_lesson_question_routes_to_lessons_specialist() -> None:
    assert rotear_deterministicamente("O que aprendemos no ciclo 1?") == ["licoes"]


def test_runtime_router_selects_lessons_without_calling_the_llm(monkeypatch) -> None:
    from langchain_core.messages import HumanMessage

    from agents import estado

    monkeypatch.setattr(estado.router, "invoke", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM router should not run")))
    result = no_roteador(
        {
            "messages": [HumanMessage(content="O que aprendemos no ciclo 1?")],
            "id_ciclo": 1,
            "latencias_ms": {},
        }
    )

    assert result["rota"] == "especialistas"
    assert result["especialistas"] == ["licoes"]
