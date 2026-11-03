import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

import agents.estado as state_module
import agents.roteador as router_module
import pipeline as pipeline_module
from pipeline import fluxo_agentes, get_response
from tools.ciclo_tools import ciclo_visao_geral
from tools.formulario_tools import formularios_resumo_respostas
from tools.relatorio_tools import relatorios_contexto_ciclo


class FakeAgent:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls = []

    def invoke(self, payload: dict) -> dict:
        self.calls.append(payload)
        return {"messages": [*payload["messages"], AIMessage(content=self.answer)]}

    def with_retry(self, **_):
        return self


class FakeToolAgent(FakeAgent):
    def __init__(self, tool, arguments: dict, answer: str) -> None:
        super().__init__(answer)
        self.tool = tool
        self.arguments = arguments

    def invoke(self, payload: dict) -> dict:
        self.calls.append(payload)
        self.tool.invoke(self.arguments)
        return {"messages": [*payload["messages"], AIMessage(content=self.answer)]}


def test_model_text_blocks_are_rendered_as_plain_text():
    message = AIMessage(content=[{"type": "text", "text": "Rascunho criado."}])
    assert pipeline_module._texto_resposta(message.content) == "Rascunho criado."


class FakeJevClient:
    def __init__(self, message_type="negocio", selected=(), cycle_scope="ativo"):
        self.message_type = message_type
        self.selected = set(selected)
        self.cycle_scope = cycle_scope
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def system_one(self, *, state, questions):
        self.calls.append((state, questions))
        return SimpleNamespace(
            choices={
                "tipo_mensagem": SimpleNamespace(choice=self.message_type),
                "escopo_ciclos": SimpleNamespace(choice=self.cycle_scope),
            },
            nouls={
                name: SimpleNamespace(noul=0.9 if name in self.selected else 0.1)
                for name in questions
                if name not in {"tipo_mensagem", "escopo_ciclos"}
            },
        )


def _set_jev(monkeypatch, *, message_type="negocio", selected=(), cycle_scope="ativo"):
    client = FakeJevClient(message_type, selected, cycle_scope)
    monkeypatch.setattr(router_module, "TypeSafeClient", lambda **_kwargs: client)
    return client


def _disable_external_memory(monkeypatch) -> None:
    monkeypatch.setenv("ACTA_ENFORCE_SPECIALIST_TOOL", "false")
    monkeypatch.setattr(state_module, "_carregar_contexto_memoria", lambda *_: "")
    monkeypatch.setattr(state_module, "_salvar_mensagem", lambda **_: None)
    monkeypatch.setattr(state_module, "consolidar_memoria", lambda *_: None)
    def echo_orchestrator(payload):
        prompt = payload["messages"][0]["content"]
        match = re.search(
            r"RESPOSTA:\n(.*?)(?:\n\nRETORNOS BRUTOS DAS TOOLS:|$)",
            prompt,
            re.DOTALL,
        )
        answer = match.group(1).strip() if match else "Resposta consolidada de teste."
        return {"messages": [*payload["messages"], AIMessage(content=answer)]}

    monkeypatch.setattr(
        state_module,
        "orquestrador",
        SimpleNamespace(invoke=echo_orchestrator),
    )
    monkeypatch.setattr(
        state_module,
        "avaliar_resposta",
        lambda **kwargs: {
            "status": "APROVADO",
            "problemas": [],
            "resposta": kwargs["resposta_orquestrador"],
        },
    )


def test_blocked_message_stops_before_router(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    jev = _set_jev(monkeypatch, selected=("rag",))
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": False, "motivo": "teste", "mensagem": "Bloqueada."},
    )

    response = get_response("mensagem perigosa", f"teste::{uuid4()}")

    assert response == "Bloqueada."
    assert jev.calls == []


def test_faq_passes_through_router_and_output_guardrail(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": True, "motivo": "aprovado", "mensagem": ""},
    )
    _set_jev(monkeypatch, selected=("rag",))
    monkeypatch.setattr(state_module, "responder_faq", lambda _: "Resposta do FAQ")
    monkeypatch.setattr(
        state_module,
        "guardrail_saida",
        lambda answer, _: {
            "valido": True,
            "motivo": "saida_revisada",
            "mensagem": f"Revisada: {answer}",
        },
    )

    response = get_response("O que é o ACTA?", f"teste::{uuid4()}")

    assert response == "Revisada: Resposta do FAQ"


@pytest.mark.parametrize("approved", [True, False])
def test_output_guardrail_precedes_judge_and_persists_final_answer(monkeypatch, approved):
    _disable_external_memory(monkeypatch)
    events = []
    saved = []
    monkeypatch.setattr(state_module, "_salvar_mensagem", lambda **item: saved.append(item))
    monkeypatch.setattr(state_module, "guardrail_entrada", lambda _: {"valido": True})
    _set_jev(monkeypatch, selected=("rag",))
    monkeypatch.setattr(state_module, "responder_faq", lambda _: "Rascunho")

    def review(answer, _):
        events.append("guardrail")
        assert answer == "Rascunho"
        return {"valido": approved, "mensagem": "Revisada" if approved else "Bloqueada"}

    def judge(**kwargs):
        events.append("juiz")
        assert kwargs["resposta_orquestrador"] == "Revisada"
        return {"status": "SUBSTITUIDO", "resposta": "Resposta segura do juiz"}

    monkeypatch.setattr(state_module, "guardrail_saida", review)
    monkeypatch.setattr(state_module, "avaliar_resposta", judge)

    answer = get_response("O que é o ACTA?", f"teste::{uuid4()}")

    assert events == (["guardrail", "juiz"] if approved else ["guardrail"])
    assert answer == ("Resposta segura do juiz" if approved else "Bloqueada")
    assert [item["content"] for item in saved if item["role"] == "assistant"] == [answer]


def test_casual_conversation_uses_recent_context_and_persists_answers(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    saved_messages = []
    prompts = []
    monkeypatch.setattr(
        state_module, "_salvar_mensagem", lambda **item: saved_messages.append(item)
    )
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": True, "motivo": "aprovado", "mensagem": ""},
    )
    _set_jev(monkeypatch, message_type="conversa")

    def answer_general(payload: dict) -> dict:
        prompt = payload["messages"][-1]["content"]
        prompts.append(prompt)
        content = (
            "Resposta inicial"
            if len(prompts) == 1
            else "Você perguntou sobre organização do tempo."
        )
        return {
            "messages": [*payload["messages"], AIMessage(content=content)]
        }

    monkeypatch.setattr(
        state_module,
        "resposta_geral_agent",
        SimpleNamespace(invoke=answer_general),
    )
    monkeypatch.setattr(
        state_module,
        "guardrail_saida",
        lambda answer, _: {"valido": True, "motivo": "ok", "mensagem": answer},
    )
    session_id = f"teste::{uuid4()}"

    first_answer = get_response("Oi, tudo bem?", session_id)
    followup_answer = get_response("Qual foi minha pergunta anterior?", session_id)

    assert first_answer == "Resposta inicial"
    assert followup_answer == "Você perguntou sobre organização do tempo."
    assert "Você é Cato, o gato laranja do ACTA" in prompts[0]
    assert "Usuário: Oi, tudo bem?" in prompts[1]
    assert "ACTA: Resposta inicial" in prompts[1]
    assert [item["role"] for item in saved_messages] == [
        "human",
        "assistant",
        "human",
        "assistant",
    ]


def test_off_scope_recipe_code_request_is_rejected_before_generation(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    _set_jev(monkeypatch, message_type="fora_escopo", selected=("rag", "ciclo"))
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": True, "motivo": "aprovado", "mensagem": ""},
    )
    monkeypatch.setattr(
        state_module,
        "resposta_geral_agent",
        SimpleNamespace(invoke=lambda _: pytest.fail("Pergunta fora de escopo não deve gerar texto.")),
    )

    response = get_response(
        "me manda um codigo para fazer uma receita de macarrao com salsicha",
        f"teste::{uuid4()}",
    )

    assert response == state_module.RESPOSTAS_TRIAGEM["fora_escopo"]


def test_cycle_agent_receives_authorized_cycle_id(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    cycle_agent = FakeAgent("Dados do ciclo")
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": True, "motivo": "aprovado", "mensagem": ""},
    )
    _set_jev(monkeypatch, selected=("ciclo",))
    monkeypatch.setattr(
        "tools.ciclo_tools.call_acta_tool", lambda *_args, **_kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(state_module, "ciclo_agent", cycle_agent)
    monkeypatch.setitem(
        state_module.REGISTRO_ESPECIALISTAS,
        "ciclo",
        lambda state: state_module._executar_agente(cycle_agent, state),
    )
    monkeypatch.setattr(
        state_module,
        "guardrail_saida",
        lambda answer, _: {
            "valido": True,
            "motivo": "saida_revisada",
            "mensagem": answer,
        },
    )

    response = get_response("Como está o ciclo?", f"teste::{uuid4()}", id_ciclo=[7])

    assert response == "Dados do ciclo"
    system_message = cycle_agent.calls[0]["messages"][0]
    assert system_message.type == "system"
    assert (
        "IDs de ciclos autorizados nesta requisição, na ordem de consulta: [7]"
        in system_message.content
    )


def test_get_response_accepts_legacy_single_cycle_id(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    cycle_agent = FakeAgent("Dados do ciclo")
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": True, "motivo": "ok", "mensagem": ""},
    )
    _set_jev(monkeypatch, selected=("ciclo",))
    monkeypatch.setattr(
        "tools.ciclo_tools.call_acta_tool", lambda *_args, **_kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(state_module, "ciclo_agent", cycle_agent)
    monkeypatch.setitem(
        state_module.REGISTRO_ESPECIALISTAS,
        "ciclo",
        lambda state: state_module._executar_agente(cycle_agent, state),
    )
    monkeypatch.setattr(
        state_module,
        "guardrail_saida",
        lambda answer, _: {"valido": True, "motivo": "ok", "mensagem": answer},
    )

    response = get_response("Como está o ciclo?", f"teste::{uuid4()}", id_ciclo=7)

    assert response == "Dados do ciclo"
    assert "IDs de ciclos autorizados nesta requisição, na ordem de consulta: [7]" in (
        cycle_agent.calls[0]["messages"][0].content
    )


def test_cycle_normalization_accepts_more_than_20_unique_ids() -> None:
    cycle_ids = [*range(1, 24), 1]

    assert pipeline_module._normalizar_ids_ciclo(cycle_ids) == list(range(1, 24))


def test_router_uses_structured_comparative_scope_for_multiple_cycles(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": True, "motivo": "ok", "mensagem": ""},
    )
    jev = _set_jev(monkeypatch, selected=("ciclo",), cycle_scope="comparacao")
    cycle_agent = FakeAgent("Comparação")
    monkeypatch.setattr(state_module, "ciclo_agent", cycle_agent)
    monkeypatch.setitem(
        state_module.REGISTRO_ESPECIALISTAS,
        "ciclo",
        lambda state: state_module._executar_agente(cycle_agent, state),
    )
    monkeypatch.setattr(
        state_module,
        "guardrail_saida",
        lambda answer, _: {"valido": True, "motivo": "ok", "mensagem": answer},
    )

    answer = get_response(
        "Compare os ciclos", f"teste::{uuid4()}", id_ciclo=[8, 4, 8], ciclo_ativo=4
    )

    assert answer == "Comparação"
    assert len(jev.calls) == 1
    agent_context = cycle_agent.calls[0]["messages"][0].content
    assert "[4, 8]" in agent_context


def test_cycle_query_without_scope_does_not_call_mcp_tools(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    calls = []
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": True, "motivo": "ok", "mensagem": ""},
    )
    monkeypatch.setattr(
        state_module,
        "guardrail_saida",
        lambda answer, _: {"valido": True, "motivo": "ok", "mensagem": answer},
    )
    _set_jev(monkeypatch, selected=("ciclo",))
    monkeypatch.setattr(
        "tools.ciclo_tools.call_acta_tool",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    cycle_agent = FakeAgent("Informe o ciclo pelo título ou descrição.")
    monkeypatch.setattr(state_module, "ciclo_agent", cycle_agent)
    monkeypatch.setitem(
        state_module.REGISTRO_ESPECIALISTAS,
        "ciclo",
        lambda state: state_module._executar_agente(cycle_agent, state),
    )

    answer = get_response("Qual é a situação do ciclo?", f"teste::{uuid4()}")

    assert "informe" in answer.lower() and "ciclo" in answer.lower()
    assert calls == []


@pytest.mark.parametrize(
    ("scope", "cycle_ids", "active_cycle", "expected"),
    [
        ("ativo", [4, 8], 4, [4]),
        ("todos", [4, 8], 4, [4, 8]),
        ("comparacao", [4, 8], 4, [4, 8]),
        ("ativo", [8], None, [8]),
        ("ativo", [4, 8], None, []),
    ],
)
def test_cycle_query_scope_comes_from_router_decision(
    scope: str,
    cycle_ids: list[int],
    active_cycle: int | None,
    expected: list[int],
) -> None:
    state = {
        "id_ciclo": cycle_ids,
        "ciclo_ativo": active_cycle,
        "escopo_ciclos": scope,
    }

    assert state_module._ciclos_para_consulta(state) == expected


def test_specialists_are_parallel_graph_nodes() -> None:
    nodes = set(fluxo_agentes.get_graph().nodes)

    assert set(state_module.NOS_ESPECIALISTAS).issubset(nodes)
    assert "especialistas" not in nodes
    assert state_module.decidir_pos_roteador(
        {"rota": "especialistas", "especialistas": ["ciclo", "tarefas"]}
    ) == ["ciclo", "tarefas"]


def test_router_can_call_multiple_specialists(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    cycle_agent = FakeAgent("Situação do ciclo")
    tasks_agent = FakeAgent("Tarefas atrasadas")
    orchestrator = FakeAgent("Resposta consolidada")
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": True, "motivo": "aprovado", "mensagem": ""},
    )
    _set_jev(monkeypatch, selected=("ciclo", "tarefas"))
    monkeypatch.setattr(
        "tools.ciclo_tools.call_acta_tool", lambda *_args, **_kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(
        "tools.tarefas_tools.call_acta_tool", lambda *_args, **_kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(state_module, "ciclo_agent", cycle_agent)
    monkeypatch.setattr(state_module, "tarefas_agent", tasks_agent)
    monkeypatch.setitem(
        state_module.REGISTRO_ESPECIALISTAS,
        "ciclo",
        lambda state: state_module._executar_agente(cycle_agent, state),
    )
    monkeypatch.setitem(
        state_module.REGISTRO_ESPECIALISTAS,
        "tarefas",
        lambda state: state_module._executar_agente(tasks_agent, state),
    )
    monkeypatch.setattr(state_module, "orquestrador", orchestrator)
    monkeypatch.setattr(
        state_module,
        "guardrail_saida",
        lambda answer, _: {
            "valido": True,
            "motivo": "saida_revisada",
            "mensagem": answer,
        },
    )

    response = get_response(
        "Como está o ciclo e quais tarefas estão atrasadas?",
        f"teste::{uuid4()}",
        id_ciclo=[4],
    )

    assert response == "Resposta consolidada"
    assert len(cycle_agent.calls) == 1
    assert len(tasks_agent.calls) == 1
    orchestrator_prompt = orchestrator.calls[0]["messages"][0]["content"]
    assert "Situação do ciclo" in orchestrator_prompt
    assert "Tarefas atrasadas" in orchestrator_prompt


def test_orchestrator_always_uses_llm_for_multiple_answers(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    orchestrator = FakeAgent("Resposta consolidada pelo orquestrador")
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": True, "motivo": "aprovado", "mensagem": ""},
    )
    monkeypatch.setattr(state_module, "ciclo_agent", FakeAgent("Situação do ciclo"))
    monkeypatch.setattr(state_module, "tarefas_agent", FakeAgent("Tarefas atrasadas"))
    monkeypatch.setitem(
        state_module.REGISTRO_ESPECIALISTAS,
        "ciclo",
        lambda state: state_module._executar_agente(state_module.ciclo_agent, state),
    )
    monkeypatch.setitem(
        state_module.REGISTRO_ESPECIALISTAS,
        "tarefas",
        lambda state: state_module._executar_agente(state_module.tarefas_agent, state),
    )
    _set_jev(monkeypatch, selected=("ciclo", "tarefas"))
    monkeypatch.setattr(
        "tools.ciclo_tools.call_acta_tool", lambda *_args, **_kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(
        "tools.tarefas_tools.call_acta_tool", lambda *_args, **_kwargs: {"status": "ok"}
    )
    monkeypatch.setattr(state_module, "orquestrador", orchestrator)
    monkeypatch.setattr(
        state_module,
        "guardrail_saida",
        lambda answer, _: {
            "valido": True,
            "motivo": "saida_revisada",
            "mensagem": answer,
        },
    )

    response = get_response(
        "Mostre a situação do ciclo e as tarefas atrasadas.",
        f"teste::{uuid4()}",
        id_ciclo=[4],
    )

    assert response == "Resposta consolidada pelo orquestrador"
    assert len(orchestrator.calls) == 1


def test_langchain_tool_forwards_to_mcp_client(monkeypatch) -> None:
    calls = []

    def fake_call(name: str, arguments: dict):
        calls.append((name, arguments))
        return {"status": "ok"}

    monkeypatch.setattr("tools.ciclo_tools.call_acta_tool", fake_call)

    response = ciclo_visao_geral.invoke({"id_ciclo": 3})

    assert response == {"status": "ok"}
    assert calls == [("ciclo_visao_geral", {"id_ciclo": 3})]


def test_form_tool_forwards_to_mcp_client(monkeypatch) -> None:
    calls = []

    def fake_call(name: str, arguments: dict):
        calls.append((name, arguments))
        return {"status": "ok", "total_respostas": 2}

    monkeypatch.setattr("tools.formulario_tools.call_acta_tool", fake_call)

    response = formularios_resumo_respostas.invoke({"id_ciclo": 3, "id_formulario": "f-1"})

    assert response["total_respostas"] == 2
    assert calls == [
        (
            "formularios_resumo_respostas",
            {"id_ciclo": 3, "id_formulario": "f-1", "limit": 200},
        )
    ]


def test_report_tool_forwards_to_mcp_client(monkeypatch) -> None:
    calls = []

    def fake_call(name: str, arguments: dict):
        calls.append((name, arguments))
        return {"status": "ok", "somente_leitura": True}

    monkeypatch.setattr("tools.relatorio_tools.call_acta_tool", fake_call)

    response = relatorios_contexto_ciclo.invoke({"id_ciclo": 3})

    assert response["somente_leitura"] is True
    assert calls == [("relatorios_contexto_ciclo", {"id_ciclo": 3, "limit": 50})]


def test_lesson_request_is_routed_to_the_lessons_agent_and_mcp_tool(monkeypatch) -> None:
    _disable_external_memory(monkeypatch)
    from tools import licoes_tools

    tool_calls = []

    def fake_call(name, arguments):
        tool_calls.append((name, arguments))
        return {"status": "ok", "resposta": "Resumo das lições.", "referencias": [2]}

    monkeypatch.setattr(licoes_tools, "call_acta_tool", fake_call)
    monkeypatch.setattr(
        state_module,
        "licoes_agent",
        FakeToolAgent(licoes_tools.resumir_licoes_aprendidas, {}, "Resumo das lições."),
    )
    monkeypatch.setattr(
        state_module,
        "guardrail_entrada",
        lambda _: {"valido": True, "motivo": "aprovado", "mensagem": ""},
    )
    jev = _set_jev(monkeypatch, selected=("licoes",))
    monkeypatch.setattr(
        state_module,
        "guardrail_saida",
        lambda answer, _: {"valido": True, "motivo": "saida_revisada", "mensagem": answer},
    )

    response = get_response(
        "Resuma as lições aprendidas do ciclo.",
        f"teste::{uuid4()}",
        id_ciclo=[7],
    )

    assert response == "Resumo das lições."
    assert tool_calls == [("licoes_resumir", {"id_ciclo": 7})]
    assert len(jev.calls) == 1
    assert not hasattr(pipeline_module, "enviar_pedido_licao")
