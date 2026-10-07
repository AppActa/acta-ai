import asyncio

import pytest

from clients import mcp_acta_client


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
