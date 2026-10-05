import asyncio

import pytest

from agents.estado import (
    _evidencia_bem_sucedida,
    _formatar_metas_confirmadas,
    _garantir_evidencia_tool,
)
from clients import mcp_acta_client


@pytest.mark.parametrize(
    ("status", "successful"),
    [("forbidden", False), ("ok", True), ("sem_evidencia", True)],
)
def test_tool_evidence_classifies_failure_statuses(status: str, successful: bool) -> None:
    assert _evidencia_bem_sucedida([{"resultado": {"status": status}}]) is successful


def test_mcp_calls_outside_cycle_request_scope_are_not_sent(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        mcp_acta_client,
        "_run_async_in_sync_context",
        lambda name, arguments: calls.append((name, arguments)) or {"status": "ok"},
    )

    with mcp_acta_client.mcp_cycle_scope_context([8, 4]):
        result = mcp_acta_client.call_acta_tool("ciclo_visao_geral", {"id_ciclo": 9})

    assert result["status"] == "forbidden"
    assert calls == []


def test_mcp_call_inside_cycle_request_scope_is_sent(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        mcp_acta_client,
        "_run_async_in_sync_context",
        lambda name, arguments: calls.append((name, arguments)) or {"status": "ok"},
    )

    with mcp_acta_client.mcp_cycle_scope_context([8, 4]):
        result = mcp_acta_client.call_acta_tool("ciclo_visao_geral", {"id_ciclo": 4})

    assert result == {"status": "ok"}
    assert calls == [("ciclo_visao_geral", {"id_ciclo": 4})]


def test_mcp_call_without_cycle_id_is_rejected_inside_cycle_scope(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        mcp_acta_client,
        "_run_async_in_sync_context",
        lambda *args: calls.append(args) or {"status": "ok"},
    )

    with mcp_acta_client.mcp_cycle_scope_context([8, 4]):
        result = mcp_acta_client.call_acta_tool("ciclo_visao_geral", {})

    assert result["status"] == "forbidden"
    assert calls == []


def test_faq_tool_is_exempt_from_cycle_scope_and_still_propagates_errors(monkeypatch) -> None:
    error = RuntimeError("FAQ indisponível")

    def fail(*_args):
        raise error

    monkeypatch.setattr(mcp_acta_client, "_run_async_in_sync_context", fail)
    with mcp_acta_client.mcp_cycle_scope_context([]):
        with pytest.raises(RuntimeError, match="FAQ indisponível") as raised:
            mcp_acta_client.call_acta_tool("faq_retriever", {"question": "Como funciona?"})

    assert raised.value is error


def test_contextvars_are_copied_to_helper_thread(monkeypatch) -> None:
    observed = {}

    async def capture_context(_name, _arguments):
        observed["request"] = mcp_acta_client._request_context.get()
        observed["cycles"] = mcp_acta_client._cycle_scope.get()
        return {"status": "ok"}

    monkeypatch.setattr(mcp_acta_client, "_call_tool_async", capture_context)

    async def call_from_running_loop():
        return mcp_acta_client._run_async_in_sync_context("ciclo_visao_geral", {})

    with mcp_acta_client.mcp_request_context(usuario_id=3, empresa_id=4):
        with mcp_acta_client.mcp_cycle_scope_context([8, 4]):
            result = asyncio.run(call_from_running_loop())

    assert result == {"status": "ok"}
    assert observed["request"].usuario_id == 3
    assert observed["request"].empresa_id == 4
    assert observed["cycles"] == frozenset({8, 4})


def test_indicator_fallback_keeps_results_for_all_cycles(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        "agents.estado._formatar_metas_confirmadas",
        lambda _result: None,
    )
    monkeypatch.setattr(
        "agents.estado._formatar_resultado_forcado",
        lambda _state, result, **_kwargs: captured.append(result) or "Comparação",
    )
    evidence = [
        {
            "tool": "predicoes_atingimento_meta",
            "argumentos": {"id_ciclo": cycle_id},
            "resultado": {"metas": [{"id_meta": cycle_id}]},
        }
        for cycle_id in (4, 8)
    ]

    answer = _garantir_evidencia_tool("indicadores", {"id_ciclo": [4, 8]}, evidence)

    assert answer == "Comparação"
    assert captured == [
        [
            {"id_ciclo": 4, "resultado": {"metas": [{"id_meta": 4}]}},
            {"id_ciclo": 8, "resultado": {"metas": [{"id_meta": 8}]}},
        ]
    ]


def test_confirmed_indicator_metas_are_labeled_by_cycle() -> None:
    formatted = _formatar_metas_confirmadas(
        [
            {
                "id_ciclo": 4,
                "resultado": {"metas": [{"id_meta": 40, "objetivo": "Meta do ciclo 4"}]},
            },
            {
                "id_ciclo": 8,
                "resultado": {"metas": [{"id_meta": 80, "objetivo": "Meta do ciclo 8"}]},
            },
        ]
    )

    assert formatted is not None
    assert "Ciclo 4:" in formatted and "Meta do ciclo 4" in formatted
    assert "Ciclo 8:" in formatted and "Meta do ciclo 8" in formatted
