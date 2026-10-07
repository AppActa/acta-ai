import asyncio
import threading

import pytest
from langchain_core.messages import HumanMessage

import agents.estado as state_module
import agents.guardrail as guardrail_module
import clients.mcp_acta_client as mcp_client
from clients.mcp_acta_client import mcp_request_context


def _state(*specialists: str) -> dict:
    return {
        "messages": [HumanMessage(content="Pergunta de teste")],
        "agentes_chamados": [],
        "rota": "especialistas",
        "especialistas": list(specialists),
        "respostas_especialistas": [],
        "mapa_pii": {},
        "session_id": "optimization::test",
        "id_ciclo": [1],
        "contexto_memoria": "",
        "resposta_final": "",
        "latencias_ms": {},
    }


def test_specialists_run_in_parallel_and_keep_mcp_context(monkeypatch) -> None:
    monkeypatch.setenv("ACTA_ENFORCE_SPECIALIST_TOOL", "false")
    barrier = threading.Barrier(2, timeout=1)

    def executor(_estado: dict) -> str:
        context = mcp_client._current_context()
        barrier.wait()
        return f"{context.usuario_id}:{context.empresa_id}:{context.trace_id}"

    monkeypatch.setattr(
        state_module,
        "REGISTRO_ESPECIALISTAS",
        {"primeiro": executor, "segundo": executor},
    )

    with mcp_request_context(
        usuario_id=7,
        empresa_id=9,
        trace_id="trace-paralelo",
    ):
        responses, called = state_module.executar_especialistas(_state("primeiro", "segundo"))

    assert called == ["primeiro", "segundo"]
    assert [item["especialista"] for item in responses] == called
    assert {item["resposta"] for item in responses} == {"7:9:trace-paralelo"}


@pytest.mark.parametrize("specialist", ["ciclo", "indicadores"])
def test_specialist_answer_is_not_replaced_by_graph_tool_fallback(
    monkeypatch,
    specialist: str,
) -> None:
    calls = []
    monkeypatch.setitem(
        state_module.REGISTRO_ESPECIALISTAS,
        specialist,
        lambda _state: "Resposta produzida pelo especialista.",
    )
    monkeypatch.setattr(
        state_module,
        "call_acta_tool",
        lambda name, args: calls.append((name, args)) or {"status": "ok"},
    )

    responses, called = state_module.executar_especialistas(_state(specialist))

    assert called == [specialist]
    assert responses[0]["resposta"] == "Resposta produzida pelo especialista."
    assert responses[0]["evidencias"] == []
    assert calls == []


def test_mcp_cache_is_limited_to_request_context(monkeypatch) -> None:
    calls = []

    def fake_call(tool_name: str, arguments: dict) -> dict:
        calls.append((tool_name, arguments))
        return {"status": "ok", "numero": len(calls)}

    monkeypatch.setattr(mcp_client, "_run_async_in_sync_context", fake_call)

    with mcp_request_context(usuario_id=1, empresa_id=1):
        first = mcp_client.call_acta_tool("tool_teste", {"b": 2, "a": 1})
        second = mcp_client.call_acta_tool("tool_teste", {"a": 1, "b": 2})

    with mcp_request_context(usuario_id=1, empresa_id=1):
        third = mcp_client.call_acta_tool("tool_teste", {"a": 1, "b": 2})

    assert first == second == {"status": "ok", "numero": 1}
    assert third == {"status": "ok", "numero": 2}
    assert len(calls) == 2


def test_mcp_records_real_and_cached_tool_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_run_async_in_sync_context",
        lambda tool_name, arguments: {
            "status": "ok",
            "tool_recebida": tool_name,
            "argumentos_recebidos": arguments,
        },
    )

    with (
        mcp_request_context(usuario_id=1, empresa_id=1),
        mcp_client.mcp_tool_evidence_context() as evidence,
    ):
        mcp_client.call_acta_tool("tool_teste", {"id_ciclo": 1})
        mcp_client.call_acta_tool("tool_teste", {"id_ciclo": 1})

    assert len(evidence) == 2
    assert evidence[0]["cache"] is False
    assert evidence[1]["cache"] is True
    assert evidence[0]["resultado"]["status"] == "ok"


def test_mcp_retries_only_transient_failures(monkeypatch) -> None:
    calls = 0

    async def temporary_failure(_tool_name: str, _arguments: dict) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("timeout")
        return {"status": "ok"}

    monkeypatch.setenv("ACTA_MCP_MAX_ATTEMPTS", "2")
    monkeypatch.setattr(mcp_client, "_call_tool_once", temporary_failure)

    assert asyncio.run(mcp_client._call_tool_async("tool_teste", {})) == {"status": "ok"}
    assert calls == 2


def test_mcp_detects_transient_failure_inside_exception_group() -> None:
    error = ExceptionGroup("task group", [TimeoutError("timeout")])

    assert mcp_client._is_transient_error(error) is True


def test_mcp_does_not_retry_non_transient_failures(monkeypatch) -> None:
    calls = 0

    async def permanent_failure(_tool_name: str, _arguments: dict) -> dict:
        nonlocal calls
        calls += 1
        raise ValueError("argumento inválido")

    monkeypatch.setenv("ACTA_MCP_MAX_ATTEMPTS", "3")
    monkeypatch.setattr(mcp_client, "_call_tool_once", permanent_failure)

    with pytest.raises(mcp_client.MCPActaError, match="argumento inválido"):
        asyncio.run(mcp_client._call_tool_async("tool_teste", {}))
    assert calls == 1


def test_output_guardrail_skips_optional_llm_review(monkeypatch) -> None:
    class UnexpectedLLM:
        def invoke(self, _prompt: str):
            raise AssertionError("A LLM de saída não deveria ser chamada")

    monkeypatch.setattr(guardrail_module, "LLM_OUTPUT_REVIEW", False)
    monkeypatch.setattr(guardrail_module, "llm", UnexpectedLLM())

    result = guardrail_module.guardrail_saida(
        "Contato: gestor@acta.com",
        {},
    )

    assert result["mensagem"] == "Contato: [EMAIL OMITIDO]"
