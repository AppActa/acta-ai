from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

import agents.estado as state
import agents.execucao as execution
import agents.juiz as judge
from agents.intencao import ExecucaoBloqueada
from clients import mcp_acta_client as mcp


def initial_state():
    evidence = {"tool": "tarefas_consultar", "argumentos": {"id_ciclo": 1}, "resultado": {"status": "ok", "count": 3}}
    return {
        "messages": [HumanMessage(content="Quantas tarefas existem?", id="human"), AIMessage(content="Existem 9 tarefas.", id="draft")],
        "rota": "especialistas", "especialistas": ["tarefas", "ciclo"],
        "respostas_especialistas": [
            {"especialista": "tarefas", "resposta": "Existem 3 tarefas.", "evidencias": [evidence]},
            {"especialista": "ciclo", "resposta": "Ciclo em andamento.", "evidencias": []},
        ],
        "evidencias_tools": [evidence], "session_id": "response-review", "id_ciclo": [1],
    }


def correction(action, **extra):
    return {"status": "CORRIGIR", "acao": action, "feedback": "A contagem correta precisa ser confirmada.", "especialista": None, "pergunta": None, **extra}


@pytest.fixture
def persistence(monkeypatch):
    save = Mock()
    monkeypatch.setattr(state, "_persistir_resposta_final", save)
    monkeypatch.setattr(state, "guardrail_saida", lambda text, _: {"valido": True, "mensagem": text})
    return save


def test_reformulates_only_orchestrator_and_reviews_again(monkeypatch, persistence):
    evaluations = iter([correction("reformular_orquestrador"), {"status": "APROVADO", "resposta": "Existem 3 tarefas."}])
    calls = []
    monkeypatch.setattr(state, "avaliar_resposta", lambda **kwargs: calls.append(kwargs) or next(evaluations))
    monkeypatch.setattr(state, "executar_especialistas", lambda _: pytest.fail("Não repetir especialistas para corrigir síntese"))
    orchestrator = Mock()
    orchestrator.invoke.return_value = {"messages": [AIMessage(content="Existem 3 tarefas.")]}
    monkeypatch.setattr(state, "orquestrador", orchestrator)

    result = state.no_juiz(initial_state())

    assert result["resposta_final"] == "Existem 3 tarefas."
    assert len(calls) == 2
    assert "contagem correta" in str(orchestrator.invoke.call_args)
    persistence.assert_called_once()


@pytest.mark.parametrize("feedback", ["Falta consultar as tarefas.", "A resposta do especialista está errada."])
def test_retries_only_responsible_specialist(monkeypatch, persistence, feedback):
    evaluations = iter([correction("repetir_especialista", especialista="tarefas", feedback=feedback), {"status": "APROVADO", "resposta": "Existem 4 tarefas."}])
    monkeypatch.setattr(state, "avaliar_resposta", lambda **_: next(evaluations))
    requests = []

    def retry(current):
        requests.append(current)
        return [{"especialista": "tarefas", "resposta": "Existem 4 tarefas.", "evidencias": [
            {"tool": "tarefas_consultar", "argumentos": {"id_ciclo": 1}, "resultado": {"status": "ok", "count": 4}},
        ]}]

    monkeypatch.setattr(state, "executar_especialistas", retry)
    monkeypatch.setattr(state, "orquestrador", Mock(invoke=lambda _: {"messages": [AIMessage(content="Existem 4 tarefas.")]}))

    result = state.no_juiz(initial_state())

    assert requests[0]["especialistas"] == ["tarefas"]
    assert requests[0]["feedback_juiz"] == feedback
    assert result["respostas_especialistas"][1]["especialista"] == "ciclo"
    counts = [e["resultado"].get("count") for e in result["evidencias_tools"]]
    assert counts == [4]
    persistence.assert_called_once()


def test_clarification_is_filtered_and_delivered_without_tools(monkeypatch, persistence):
    monkeypatch.setattr(state, "avaliar_resposta", lambda **_: correction("pedir_esclarecimento", pergunta="Qual ciclo deseja consultar?"))
    monkeypatch.setattr(state, "guardrail_saida", lambda text, _: {"valido": True, "mensagem": text + " [revisada]"})
    monkeypatch.setattr(state, "executar_especialistas", lambda _: pytest.fail("Pergunta não executa ferramentas"))
    result = state.no_juiz(initial_state())
    assert result["resposta_final"] == "Qual ciclo deseja consultar? [revisada]"
    persistence.assert_called_once()


def test_two_corrections_then_safe_fallback(monkeypatch, persistence):
    reviews = []
    monkeypatch.setattr(state, "avaliar_resposta", lambda **_: reviews.append(1) or correction("reformular_orquestrador"))
    orchestrator = Mock()
    orchestrator.invoke.return_value = {"messages": [AIMessage(content="Ainda incorreta.")]}
    monkeypatch.setattr(state, "orquestrador", orchestrator)
    result = state.no_juiz(initial_state())
    assert len(reviews) == 3
    assert orchestrator.invoke.call_count == 2
    assert result["resposta_final"] == judge._SAFE_FALLBACK
    persistence.assert_called_once()


def test_corrected_answer_must_pass_output_guardrail(monkeypatch, persistence):
    reviews = []
    monkeypatch.setattr(state, "avaliar_resposta", lambda **_: reviews.append(1) or correction("reformular_orquestrador"))
    monkeypatch.setattr(state, "orquestrador", Mock(invoke=lambda _: {"messages": [AIMessage(content="Texto bloqueado.")]}))
    monkeypatch.setattr(state, "guardrail_saida", lambda *_: {"valido": False, "mensagem": "Resposta bloqueada."})
    result = state.no_juiz(initial_state())
    assert result["resposta_final"] == "Resposta bloqueada."
    assert len(reviews) == 1


def test_response_review_cannot_repeat_a_write(monkeypatch, persistence):
    monkeypatch.setattr(state, "avaliar_resposta", lambda **_: correction("repetir_especialista", especialista="tarefas"))
    calls = []
    monkeypatch.setattr(mcp, "_run_async_in_sync_context", lambda *args: calls.append(args))
    monkeypatch.setattr(execution, "avaliar_intencao", lambda **_: pytest.fail("Revisão deve bloquear antes do juiz de escrita"))

    def retry(_):
        with execution.transacoes_context("Crie uma tarefa", {"tools_autorizadas": ["tarefas_criar"]}), pytest.raises(ExecucaoBloqueada):
            mcp.call_acta_tool("tarefas_criar", {
                "id_ciclo": 1, "id_plano_acao": 1, "id_responsavel": 2,
                "titulo": "Não repetir", "descricao": "Transação já concluída",
                "data_fim_prevista": "2026-12-31", "prioridade": "MEDIA",
            })
        return [{"especialista": "tarefas", "resposta": "Bloqueada", "evidencias": [], "interrompido": True}]

    monkeypatch.setattr(state, "executar_especialistas", retry)
    result = state.no_juiz(initial_state())
    assert calls == []
    assert result["resposta_final"] == judge._SAFE_FALLBACK


def test_invalid_correction_target_does_not_execute(monkeypatch, persistence):
    monkeypatch.setattr(state, "avaliar_resposta", lambda **_: correction("repetir_especialista", especialista="inexistente"))
    monkeypatch.setattr(state, "executar_especialistas", lambda _: pytest.fail("Destino inválido"))
    assert state.no_juiz(initial_state())["resposta_final"] == judge._SAFE_FALLBACK


def semantic_client(monkeypatch, *, failure=None):
    client = MagicMock()
    response = SimpleNamespace(nouls={
        "fidelidade": SimpleNamespace(noul=0.1),
        "compliance": SimpleNamespace(noul=0.9),
        "relevancia": SimpleNamespace(noul=0.9),
    })
    client.__enter__.return_value.system_one.return_value = response
    client.__enter__.return_value.system_one.side_effect = failure
    monkeypatch.setattr(judge, "TypeSafeClient", lambda **_: client)
    return client


@pytest.mark.parametrize("action,extra", [
    ("repetir_especialista", {"especialista": "tarefas"}),
    ("reformular_orquestrador", {}),
    ("pedir_esclarecimento", {"pergunta": "Qual ciclo?"}),
])
def test_judge_returns_validated_correction_with_redacted_context(monkeypatch, action, extra):
    semantic_client(monkeypatch)
    model = Mock()
    plan = {key: value for key, value in correction(action, **extra).items() if key != "status"}
    model.with_structured_output.return_value.invoke.return_value = plan
    monkeypatch.setattr(judge, "llm", model)
    current = initial_state()
    result = judge.avaliar_resposta(
        pergunta="Contato gestor@acta.com", respostas_especialistas=current["respostas_especialistas"],
        evidencias_tools=current["evidencias_tools"], resposta_orquestrador="Existem 9 tarefas.",
    )
    assert result["status"] == "CORRIGIR"
    assert result["acao"] == action
    assert "gestor@acta.com" not in str(model.with_structured_output.return_value.invoke.call_args)


@pytest.mark.parametrize("changes", [
    {"acao": "executar_tool"}, {"especialista": "tarefas"},
    {"pergunta": "Qual ciclo?"}, {"feedback": " "},
    {"acao": "repetir_especialista"}, {"acao": "pedir_esclarecimento"},
])
def test_invalid_or_contradictory_correction_is_rejected(changes):
    with pytest.raises(ValidationError):
        judge.CorrecaoResposta.model_validate({
            "acao": "reformular_orquestrador", "especialista": None,
            "feedback": "Corrija os fatos.", "pergunta": None, **changes,
        })


def test_judge_failure_does_not_request_a_retry(monkeypatch):
    semantic_client(monkeypatch, failure=TimeoutError("JEV indisponível"))
    model = Mock()
    monkeypatch.setattr(judge, "llm", model)
    result = judge.avaliar_resposta(pergunta="Quantas?", respostas_especialistas=[], evidencias_tools=[], resposta_orquestrador="3")
    assert result["status"] == "SUBSTITUIDO"
    model.with_structured_output.assert_not_called()


def test_unknown_specialist_from_correction_model_is_blocked(monkeypatch):
    semantic_client(monkeypatch)
    model = Mock()
    model.with_structured_output.return_value.invoke.return_value = {
        "acao": "repetir_especialista", "especialista": "inexistente",
        "feedback": "Corrija", "pergunta": None,
    }
    monkeypatch.setattr(judge, "llm", model)
    result = judge.avaliar_resposta(pergunta="Quantas?", respostas_especialistas=[], evidencias_tools=[], resposta_orquestrador="3")
    assert result["status"] == "SUBSTITUIDO"


def test_evidence_merge_preserves_write_receipts_and_refreshes_reads():
    receipt = {"tool": "tarefas_criar", "argumentos": {"id_ciclo": 1}, "resultado": {"status": "ok", "id": 21}}
    previous = initial_state()["evidencias_tools"][0]
    fresh = {**previous, "resultado": {"status": "ok", "count": 4}}
    merged = state._mesclar_evidencias([previous, receipt, receipt], [fresh])
    assert merged == [receipt, receipt, fresh]


def test_specialist_retry_uses_fresh_query_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp, "_run_async_in_sync_context", lambda *_: calls.append(1) or {"status": "ok", "count": len(calls)})
    monkeypatch.setattr(state, "orquestrador", Mock(invoke=lambda _: {"messages": [AIMessage(content="Existem 2 tarefas.")]}))
    monkeypatch.setitem(state.REGISTRO_ESPECIALISTAS, "tarefas", lambda _: str(mcp.call_acta_tool("tarefas_consultar", {"id_ciclo": 1})["count"]))
    current = initial_state()
    with mcp.mcp_tool_cache_context():
        mcp.call_acta_tool("tarefas_consultar", {"id_ciclo": 1})
        state._corrigir_resposta(current, judge.CorrecaoResposta(
            acao="repetir_especialista", especialista="tarefas", feedback="Consulte novamente.", pergunta=None,
        ))
    assert len(calls) == 2
    assert current["evidencias_tools"][0]["resultado"]["count"] == 2


def test_correction_model_failure_uses_safe_fallback(monkeypatch):
    semantic_client(monkeypatch)
    model = Mock()
    model.with_structured_output.return_value.invoke.side_effect = TimeoutError("Planejamento indisponível")
    monkeypatch.setattr(judge, "llm", model)
    result = judge.avaliar_resposta(pergunta="Quantas?", respostas_especialistas=[], evidencias_tools=[], resposta_orquestrador="3")
    assert result["status"] == "SUBSTITUIDO"


def test_revision_read_only_context_is_cleared_after_exception():
    with pytest.raises(RuntimeError), execution.revisao_resposta_context():
        raise RuntimeError("Falha durante a revisão")
    assert execution._revisao_resposta.get() is False


def test_lesson_revision_keeps_comparison_scope_and_feedback(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "_executar_agente", lambda *_: pytest.fail("Revisão de lições mantém consultas explícitas por ciclo"))
    monkeypatch.setattr(state, "call_acta_tool", lambda name, args: calls.append((name, args)) or {"status": "ok", "resposta": "Dados confirmados"})
    state._executar_licoes({
        "messages": [HumanMessage(content="Compare as lições dos ciclos")],
        "id_ciclo": [1, 3], "escopo_ciclos": "comparacao", "feedback_juiz": "Explique as diferenças.",
    })
    assert [args["id_ciclo"] for _, args in calls] == [1, 3]
    assert all(name == "licoes_perguntar" for name, _ in calls)
    assert all("Explique as diferenças" in args["pergunta"] for _, args in calls)
