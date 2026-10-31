import asyncio

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage

import agents.execucao as execution
from agents.intencao import EsclarecimentoNecessario, ExecucaoBloqueada
from clients import mcp_acta_client as mcp
from tools.ciclo_tools import ciclos_registrar_causa

WRITE = "ciclos_registrar_causa"
ARGS = {"id_ciclo": 8, "id_problema": 1, "descricao": "Falha no processo"}


def verdict(**changes):
    return {"decisao": "aprovada", "apoio": 0.9, "motivo": "Pedido explícito.", "pergunta": None, **changes}


@pytest.fixture
def transport(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp, "_run_async_in_sync_context", lambda name, args: calls.append((name, args)) or {"status": "ok"})
    return calls


def transaction_context():
    return execution.transacoes_context("Registre a causa", {"tools_autorizadas": [WRITE]})


@pytest.mark.parametrize("support,allowed", [(0.69, False), (0.7, True), (1.0, True)])
def test_only_sufficient_approval_executes(monkeypatch, transport, support, allowed):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: verdict(apoio=support))
    with transaction_context() as records:
        if allowed:
            assert mcp.call_acta_tool(WRITE, ARGS)["status"] == "ok"
        else:
            with pytest.raises(ExecucaoBloqueada):
                mcp.call_acta_tool(WRITE, ARGS)

    assert len(transport) == int(allowed)
    assert records[0]["intencao"]["tool"] == WRITE


def test_correction_executes_only_corrected_payload(monkeypatch, transport):
    decisions = iter([verdict(decisao="corrigir_proposta"), verdict()])
    reviewed = []

    def judge(**kwargs):
        reviewed.append(kwargs["intencao"].argumentos.copy())
        return next(decisions)

    monkeypatch.setattr(execution, "avaliar_intencao", judge)
    with transaction_context():
        assert mcp.call_acta_tool(WRITE, ARGS)["status"] == "corrigir_proposta"
        assert transport == []
        mcp.call_acta_tool(WRITE, {**ARGS, "descricao": "Causa corrigida"})

    assert len(transport) == 1
    assert transport[0][1] == reviewed[-1]
    assert transport[0][1]["descricao"] == "Causa corrigida"


def test_two_retries_allow_exactly_three_evaluations(monkeypatch, transport):
    calls = []
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: calls.append(1) or verdict(decisao="corrigir_proposta"))
    with transaction_context():
        for _ in range(2):
            assert mcp.call_acta_tool(WRITE, ARGS)["status"] == "corrigir_proposta"
        with pytest.raises(ExecucaoBloqueada):
            mcp.call_acta_tool(WRITE, ARGS)

    assert len(calls) == 3
    assert transport == []


@pytest.mark.parametrize("result", [
    verdict(apoio=True), verdict(apoio="0.9"), verdict(apoio=float("nan")),
    verdict(apoio=float("inf")), verdict(pergunta="Contradição"),
    verdict(decisao="invalida"), {}, TimeoutError("judge timeout"),
])
def test_invalid_or_failed_judge_never_executes(monkeypatch, transport, result):
    def judge(**_):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(execution, "avaliar_intencao", judge)
    with transaction_context(), pytest.raises(ExecucaoBloqueada):
        mcp.call_acta_tool(WRITE, ARGS)
    assert transport == []


def test_clarification_interrupts_without_execution(monkeypatch, transport):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: verdict(decisao="pedir_esclarecimento", pergunta="Qual causa deseja registrar?"))
    with transaction_context(), pytest.raises(EsclarecimentoNecessario, match="Qual causa"):
        mcp.call_acta_tool(WRITE, ARGS)
    assert transport == []


def test_reads_do_not_require_judge(monkeypatch, transport):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: pytest.fail("Consulta não deve passar pelo juiz de intenção"))
    assert mcp.call_acta_tool("ciclo_visao_geral", {"id_ciclo": 8})["status"] == "ok"
    assert len(transport) == 1


def test_write_requires_context_even_after_cache_or_scope_cleanup(monkeypatch, transport):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: verdict())
    with mcp.mcp_tool_cache_context(), transaction_context():
        mcp.call_acta_tool(WRITE, ARGS)
    with pytest.raises(ExecucaoBloqueada):
        mcp.call_acta_tool(WRITE, ARGS)
    assert len(transport) == 1


@pytest.mark.parametrize("name,args", [(WRITE, {**ARGS, "surpresa": True}), (WRITE, {**ARGS, "id_ciclo": "8"}), ("nova_tool_desconhecida", {})])
def test_invalid_payload_or_unknown_tool_blocks_before_judge(monkeypatch, transport, name, args):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: pytest.fail("Intenção inválida"))
    with transaction_context(), pytest.raises(ExecucaoBloqueada):
        mcp.call_acta_tool(name, args)
    assert transport == []


def test_out_of_scope_write_does_not_reach_judge(monkeypatch, transport):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: pytest.fail("Escopo inválido"))
    with transaction_context(), mcp.mcp_cycle_scope_context([1]):
        assert mcp.call_acta_tool(WRITE, ARGS)["status"] == "forbidden"
    assert transport == []


def test_write_timeout_has_no_transport_retry(monkeypatch):
    calls = []

    async def fail(*_):
        calls.append(1)
        raise TimeoutError("timeout")

    monkeypatch.setattr(mcp, "_call_tool_once", fail)
    monkeypatch.setenv("ACTA_MCP_MAX_ATTEMPTS", "3")
    with pytest.raises(mcp.MCPActaError):
        asyncio.run(mcp._call_tool_async(WRITE, ARGS))
    assert calls == [1]


class ToolModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_real_agent_receives_correction_and_resubmits(monkeypatch, transport):
    decisions = iter([verdict(decisao="corrigir_proposta"), verdict()])
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: next(decisions))
    proposals = [
        AIMessage(content="", tool_calls=[{"id": "first", "name": WRITE, "args": ARGS}]),
        AIMessage(content="", tool_calls=[{"id": "second", "name": WRITE, "args": {**ARGS, "descricao": "Corrigida"}}]),
        AIMessage(content="Causa registrada."),
    ]
    agent = create_agent(model=ToolModel(responses=proposals), tools=[ciclos_registrar_causa])
    with transaction_context():
        result = agent.invoke({"messages": [HumanMessage(content="Registre a causa")]})
    assert result["messages"][-1].content == "Causa registrada."
    assert "corrigir_proposta" in result["messages"][2].content
    assert len(transport) == 1
    assert transport[0][1]["descricao"] == "Corrigida"


def test_real_agent_propagates_clarification(monkeypatch, transport):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: verdict(decisao="pedir_esclarecimento", pergunta="Qual causa?"))
    model = ToolModel(responses=[AIMessage(content="", tool_calls=[{"id": "first", "name": WRITE, "args": ARGS}])])
    agent = create_agent(model=model, tools=[ciclos_registrar_causa])
    with transaction_context(), pytest.raises(EsclarecimentoNecessario):
        agent.invoke({"messages": [HumanMessage(content="Registre a causa")]})
    assert transport == []


def test_write_batch_is_blocked_before_any_dispatch(monkeypatch, transport):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: pytest.fail("Lote não pode chegar ao juiz"))
    calls = [{"id": str(index), "name": WRITE, "args": ARGS} for index in range(2)]
    agent = create_agent(
        model=ToolModel(responses=[AIMessage(content="", tool_calls=calls)]),
        tools=[ciclos_registrar_causa], middleware=[execution.bloquear_lote_de_escrita],
    )
    with transaction_context(), pytest.raises(ExecucaoBloqueada):
        agent.invoke({"messages": [HumanMessage(content="Registre a causa")]})
    assert transport == []


def test_transaction_context_resets_retries_between_rounds(monkeypatch, transport):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: verdict(decisao="corrigir_proposta"))
    for _ in range(2):
        with transaction_context() as records:
            assert mcp.call_acta_tool(WRITE, ARGS)["status"] == "corrigir_proposta"
            assert len(records) == 1
    assert transport == []


def test_approved_writes_do_not_use_read_cache(monkeypatch, transport):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: verdict())
    with transaction_context(), mcp.mcp_tool_cache_context():
        for _ in range(execution.MAX_ACOES_ESPECIALISTA):
            mcp.call_acta_tool(WRITE, ARGS)
        with pytest.raises(ExecucaoBloqueada):
            mcp.call_acta_tool(WRITE, ARGS)
    assert len(transport) == execution.MAX_ACOES_ESPECIALISTA


def test_write_outside_specialist_is_blocked(monkeypatch, transport):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: pytest.fail("Domínio não autorizado"))
    with execution.transacoes_context("Registre", {"tools_autorizadas": []}), pytest.raises(ExecucaoBloqueada):
        mcp.call_acta_tool(WRITE, ARGS)
    assert transport == []


def test_uncertain_write_is_not_reported_as_unexecuted(monkeypatch):
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: verdict())

    def fail(*_):
        raise TimeoutError("O servidor pode já ter aplicado a alteração")

    monkeypatch.setattr(mcp, "_run_async_in_sync_context", fail)
    with transaction_context(), pytest.raises(ExecucaoBloqueada, match="Não consegui confirmar"):
        mcp.call_acta_tool(WRITE, ARGS)


def test_clarification_stops_other_specialists_and_bypasses_synthesis(monkeypatch):
    import agents.estado as state

    def clarify(_):
        raise EsclarecimentoNecessario("Qual título deseja?")

    monkeypatch.setattr(state, "REGISTRO_ESPECIALISTAS", {
        "primeiro": clarify, "segundo": lambda _: pytest.fail("Rodada deve estar encerrada"),
    })
    monkeypatch.setattr(state, "orquestrador", type("NoSynthesis", (), {"invoke": lambda *_: pytest.fail("Não substituir esclarecimento")})())
    result = state.no_orquestrador({
        "messages": [HumanMessage(content="Crie um formulário")], "rota": "especialistas",
        "especialistas": ["primeiro", "segundo"], "id_ciclo": [1], "session_id": "clarification-test",
    })
    assert result["messages"][0]["content"] == "Qual título deseja?"
    assert result["rota"] == "interrompido"
    assert len(result["respostas_especialistas"]) == 1


def test_specialist_cannot_claim_success_with_pending_correction(monkeypatch, transport):
    import agents.estado as state

    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: verdict(decisao="corrigir_proposta"))

    def propose(_):
        mcp.call_acta_tool(WRITE, ARGS)
        return "Registrado com sucesso!"

    monkeypatch.setitem(state.REGISTRO_ESPECIALISTAS, "ciclo", propose)
    result = state.executar_especialistas({"messages": [HumanMessage(content="Registre a causa")], "especialistas": ["ciclo"]})
    assert result[0]["interrompido"] is True
    assert "sucesso" not in result[0]["resposta"]
    assert transport == []


@pytest.mark.parametrize("name,args", [
    ("tarefas_detalhes", {"id_tarefa": 1, "id_ciclo": 8}),
    ("tarefas_atualizar", {"id_tarefa": 1, "id_ciclo": 8, "titulo": "Atualizado"}),
    ("tarefas_atualizar_status", {"id_tarefa": 1, "id_ciclo": 8, "status": "EM_ANDAMENTO"}),
])
def test_task_wrappers_preserve_cycle_required_by_mcp(monkeypatch, transport, name, args):
    from tools import tarefas_tools

    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: verdict())
    with execution.transacoes_context("Atualize a tarefa", {"tools_autorizadas": [name]}), mcp.mcp_cycle_scope_context([8]):
        getattr(tarefas_tools, name).invoke(args)
    assert len(transport) == 1
    assert transport[0][1]["id_ciclo"] == 8
