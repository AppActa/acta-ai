from types import SimpleNamespace

from agents.estado import no_roteador
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


def test_jev_routes_lesson_question_to_lessons_specialist(monkeypatch) -> None:
    from langchain_core.messages import HumanMessage

    from agents import estado

    class FakeJevClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def system_one(self, *, state, questions):
            return SimpleNamespace(
                choices={
                    "tipo_mensagem": SimpleNamespace(choice="negocio"),
                    "escopo_ciclos": SimpleNamespace(choice="ativo"),
                },
                nouls={
                    name: SimpleNamespace(noul=0.9 if name == "licoes" else 0.1)
                    for name in questions
                    if name not in {"tipo_mensagem", "escopo_ciclos"}
                }
            )

    monkeypatch.setattr(estado, "TypeSafeClient", lambda **_kwargs: FakeJevClient())
    result = no_roteador(
        {
            "messages": [HumanMessage(content="O que aprendemos no ciclo 1?")],
            "id_ciclo": [1],
            "latencias_ms": {},
        }
    )

    assert result["rota"] == "especialistas"
    assert result["especialistas"] == ["licoes"]


def test_jev_router_receives_recent_context_and_logs_scores(monkeypatch, caplog) -> None:
    import logging

    from langchain_core.messages import AIMessage, HumanMessage

    from agents import estado

    calls = []

    class FakeJevClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def system_one(self, *, state, questions):
            calls.append((state, questions))
            return SimpleNamespace(
                choices={
                    "tipo_mensagem": SimpleNamespace(choice="negocio"),
                    "escopo_ciclos": SimpleNamespace(choice="ativo"),
                },
                nouls={
                    name: SimpleNamespace(noul=0.9 if name == "rag" else 0.1)
                    for name in questions
                    if name not in {"tipo_mensagem", "escopo_ciclos"}
                },
            )

    monkeypatch.setattr(estado, "TypeSafeClient", lambda **_kwargs: FakeJevClient())
    with caplog.at_level(logging.INFO, logger="agents.estado"):
        result = no_roteador(
            {
                "messages": [
                    HumanMessage(content="Quais são as etapas do PDCA?"),
                    AIMessage(content="O PDCA tem quatro etapas: Planejar, Fazer, Checar e Agir."),
                    HumanMessage(content="E qual delas vem primeiro?"),
                ],
                "session_id": "sessao-teste",
                "id_ciclo": [],
                "latencias_ms": {},
            }
        )

    routed_state, routed_questions = calls[0]
    assert "Quais são as etapas do PDCA?" in routed_state["contexto_conversa"]
    assert "E qual delas vem primeiro?" in routed_state["contexto_conversa"]
    assert "exemplos" in routed_questions["rag"].instructions.casefold()
    assert "etapas do pdca" in routed_questions["rag"].instructions.casefold()
    assert "não deve ser escolhido para explicar" in routed_questions["ciclo"].instructions.casefold()
    assert "não deve ser escolhido para perguntas conceituais sobre pdca" in (
        routed_questions["licoes"].instructions.casefold()
    )
    assert "Roteamento JEV" in caplog.text
    assert "rag=0.90" in caplog.text
    assert result["rota"] == "especialistas"
