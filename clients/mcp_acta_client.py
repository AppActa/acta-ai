import asyncio
import json
import logging
import os
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
from uuid import uuid4

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from config import (
    ACTA_MCP_API_KEY,
    ACTA_MCP_EMPRESA_ID,
    ACTA_MCP_MAX_ATTEMPTS,
    ACTA_MCP_TIMEOUT_SECONDS,
    ACTA_MCP_URL,
    ACTA_MCP_USUARIO_ID,
)

logger = logging.getLogger(__name__)


class MCPActaError(RuntimeError):
    """Falha de comunicação ou execução no servidor MCP ACTA."""


@dataclass(frozen=True, slots=True)
class MCPRequestContext:
    usuario_id: int
    empresa_id: int
    trace_id: str = ""


_request_context: ContextVar[MCPRequestContext | None] = ContextVar(
    "acta_ai_mcp_request_context",
    default=None,
)
_request_cache: ContextVar[dict[str, dict | str] | None] = ContextVar(
    "acta_ai_mcp_request_cache",
    default=None,
)
_tool_evidence: ContextVar[list[dict[str, object]] | None] = ContextVar(
    "acta_ai_mcp_tool_evidence",
    default=None,
)
_cycle_scope: ContextVar[frozenset[int] | None] = ContextVar(
    "acta_ai_cycle_scope",
    default=None,
)


@contextmanager
def mcp_cycle_scope_context(cycle_ids: list[int]) -> Iterator[None]:
    """Limita as chamadas MCP desta rodada aos ciclos recebidos pelo chatbot."""

    token = _cycle_scope.set(frozenset(cycle_ids))
    try:
        yield
    finally:
        _cycle_scope.reset(token)


@contextmanager
def mcp_tool_cache_context() -> Iterator[dict[str, dict | str]]:
    """Mantém resultados MCP somente durante uma execução da pipeline."""

    cache: dict[str, dict | str] = {}
    token = _request_cache.set(cache)
    try:
        yield cache
    finally:
        _request_cache.reset(token)


@contextmanager
def mcp_tool_evidence_context() -> Iterator[list[dict[str, object]]]:
    """Coleta, isoladamente, as chamadas MCP reais feitas por um especialista."""

    evidence: list[dict[str, object]] = []
    token = _tool_evidence.set(evidence)
    try:
        yield evidence
    finally:
        _tool_evidence.reset(token)


def _record_tool_evidence(
    tool_name: str,
    arguments: dict,
    result: dict | str,
    *,
    cached: bool,
) -> None:
    evidence = _tool_evidence.get()
    if evidence is not None:
        evidence.append(
            {
                "tool": tool_name,
                "argumentos": arguments,
                "resultado": result,
                "cache": cached,
            }
        )


@contextmanager
def mcp_request_context(
    *,
    usuario_id: int,
    empresa_id: int,
    trace_id: str | None = None,
) -> Iterator[MCPRequestContext]:
    """Define o contexto autenticado propagado às chamadas MCP deste fluxo."""
    context = MCPRequestContext(
        usuario_id=usuario_id,
        empresa_id=empresa_id,
        trace_id=trace_id or str(uuid4()),
    )
    token = _request_context.set(context)
    try:
        yield context
    finally:
        _request_context.reset(token)


def _current_context() -> MCPRequestContext:
    context = _request_context.get()
    if context is not None:
        return context
    try:
        return MCPRequestContext(
            usuario_id=ACTA_MCP_USUARIO_ID,
            empresa_id=ACTA_MCP_EMPRESA_ID,
            trace_id=str(uuid4()),
        )
    except RuntimeError as exc:
        raise MCPActaError(
            f"{exc} Não há contexto MCP ativo para a requisição."
        ) from exc


def current_mcp_request_context() -> MCPRequestContext:
    """Retorna a identidade autenticada ativa, sem fallback de ambiente."""

    context = _request_context.get()
    if context is None:
        raise MCPActaError("Não há contexto autenticado ativo para a requisição.")
    return context


def mcp_identity_scope() -> str:
    """Escopo estável para caches locais, sem expor a identidade ao modelo."""

    context = _request_context.get()
    if context is None:
        return "local"
    return f"empresa:{context.empresa_id}:usuario:{context.usuario_id}"


def _headers() -> dict[str, str]:
    context = _current_context()
    headers = {
        "X-Acta-Usuario-Id": str(context.usuario_id),
        "X-Acta-Empresa-Id": str(context.empresa_id),
        "X-Trace-Id": context.trace_id,
    }
    api_key = os.getenv("ACTA_MCP_API_KEY", ACTA_MCP_API_KEY)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _is_transient_error(exc: BaseException) -> bool:
    """Reconhece apenas falhas temporárias que podem melhorar numa nova tentativa."""

    if isinstance(exc, BaseExceptionGroup):
        return any(_is_transient_error(nested) for nested in exc.exceptions)
    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout)):
        return True
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code in {408, 429, 500, 502, 503, 504}:
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "timed out",
            "timeout",
            "connection reset",
            "connection refused",
            "temporarily unavailable",
            "server disconnected",
            "status 429",
            "status 502",
            "status 503",
            "status 504",
        )
    )


async def _call_tool_once(tool_name: str, arguments: dict) -> dict | str:
    url = os.getenv("ACTA_MCP_URL", ACTA_MCP_URL)
    timeout = float(os.getenv("ACTA_MCP_TIMEOUT_SECONDS", str(ACTA_MCP_TIMEOUT_SECONDS)))

    async with streamablehttp_client(
        url,
        headers=_headers(),
        timeout=timeout,
        sse_read_timeout=timeout,
    ) as streams:
        read_stream, write_stream, _ = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.call_tool(tool_name, arguments)

    if response.isError:
        messages = [getattr(content, "text", str(content)) for content in response.content]
        raise MCPActaError(f"A tool MCP '{tool_name}' retornou erro: {' '.join(messages)}")

    if response.structuredContent is not None:
        return response.structuredContent

    text_parts = [content.text for content in response.content if hasattr(content, "text")]
    raw = "\n".join(text_parts)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


async def _call_tool_async(tool_name: str, arguments: dict) -> dict | str:
    max_attempts = max(1, int(os.getenv("ACTA_MCP_MAX_ATTEMPTS", str(ACTA_MCP_MAX_ATTEMPTS))))
    for attempt in range(1, max_attempts + 1):
        try:
            return await _call_tool_once(tool_name, arguments)
        except Exception as exc:
            if attempt == max_attempts or not _is_transient_error(exc):
                raise MCPActaError(f"Falha ao chamar a tool MCP '{tool_name}': {exc}") from exc
            logger.warning(
                "Falha MCP transitória em %s (tentativa %s/%s): %s",
                tool_name,
                attempt,
                max_attempts,
                exc,
            )
            await asyncio.sleep(0.2 * attempt)

    raise MCPActaError(f"Falha inesperada ao chamar a tool MCP '{tool_name}'.")


def _run_async_in_sync_context(tool_name: str, arguments: dict) -> dict | str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_call_tool_async(tool_name, arguments))

    result: list[dict | str] = []
    error: list[Exception] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(_call_tool_async(tool_name, arguments)))
        except Exception as exc:  # noqa: BLE001 - propagado para a thread chamadora
            error.append(exc)

    thread = threading.Thread(target=copy_context().run, args=(runner,), daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]


def call_acta_tool(tool_name: str, arguments: dict) -> dict | str:
    """Executa uma tool no MCP ACTA preservando resultado estruturado."""
    sanitized = {
        key: value for key, value in arguments.items() if value is not None and key != "id_empresa"
    }
    allowed_cycles = _cycle_scope.get()
    if allowed_cycles is not None and tool_name != "faq_retriever" and (
        not allowed_cycles or sanitized.get("id_ciclo") not in allowed_cycles
    ):
        result = {"status": "forbidden", "erro": "Ciclo fora do escopo desta requisição."}
        _record_tool_evidence(tool_name, sanitized, result, cached=False)
        return result
    cache = _request_cache.get()
    cache_key = json.dumps(
        [tool_name, sanitized],
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    if cache is not None and cache_key in cache:
        logger.debug("Cache MCP da requisição: hit em %s", tool_name)
        cached_result = cache[cache_key]
        _record_tool_evidence(tool_name, sanitized, cached_result, cached=True)
        return cached_result

    try:
        result = _run_async_in_sync_context(tool_name, sanitized)
    except Exception as exc:
        _record_tool_evidence(
            tool_name,
            sanitized,
            {"status": "error", "tipo": type(exc).__name__},
            cached=False,
        )
        raise
    if cache is not None:
        cache[cache_key] = result
    _record_tool_evidence(tool_name, sanitized, result, cached=False)
    return result
