import asyncio
import json
import logging
import os
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
_discovered_cycle_scope: ContextVar[set[int] | None] = ContextVar(
    "acta_ai_discovered_cycle_scope",
    default=None,
)
FERRAMENTAS_LEITURA_ENTRE_CICLOS = frozenset({
    "tarefas_resumo_entre_ciclos",
    "tarefas_consultar_entre_ciclos",
    "licoes_listar_entre_ciclos",
    "licoes_resumir_entre_ciclos",
    "licoes_perguntar_entre_ciclos",
})


@contextmanager
def mcp_cycle_scope_context(cycle_ids: list[int]) -> Iterator[None]:
    """Limita as chamadas MCP desta rodada aos ciclos recebidos pelo chatbot."""

    token_ciclos = _cycle_scope.set(frozenset(cycle_ids))
    token_ciclos_descobertos = _discovered_cycle_scope.set(set())
    try:
        yield
    finally:
        _discovered_cycle_scope.reset(token_ciclos_descobertos)
        _cycle_scope.reset(token_ciclos)


@contextmanager
def mcp_discovered_cycle_scope_context() -> Iterator[None]:
    """Inicializa o escopo descoberto caso a chamada não esteja dentro de uma requisição."""

    token_escopo = None
    if _discovered_cycle_scope.get() is None:
        token_escopo = _discovered_cycle_scope.set(set())
    try:
        yield
    finally:
        if token_escopo is not None:
            _discovered_cycle_scope.reset(token_escopo)


@contextmanager
def mcp_tool_cache_context() -> Iterator[dict[str, dict | str]]:
    """Mantém resultados MCP somente durante uma execução da pipeline."""

    cache_ferramentas: dict[str, dict | str] = {}
    token_cache = _request_cache.set(cache_ferramentas)
    try:
        yield cache_ferramentas
    finally:
        _request_cache.reset(token_cache)


@contextmanager
def mcp_tool_evidence_context() -> Iterator[list[dict[str, object]]]:
    """Coleta, isoladamente, as chamadas MCP reais feitas por um especialista."""

    evidencias: list[dict[str, object]] = []
    token_evidencias = _tool_evidence.set(evidencias)
    try:
        yield evidencias
    finally:
        _tool_evidence.reset(token_evidencias)


def _registrar_evidencia_tool(
    nome_ferramenta: str,
    argumentos: dict,
    resultado: dict | str,
    *,
    cached: bool,
) -> None:
    evidencias = _tool_evidence.get()
    if evidencias is not None:
        evidencias.append(
            {
                "tool": nome_ferramenta,
                "argumentos": argumentos,
                "resultado": resultado,
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
    contexto = MCPRequestContext(
        usuario_id=usuario_id,
        empresa_id=empresa_id,
        trace_id=trace_id or str(uuid4()),
    )
    token_contexto = _request_context.set(contexto)
    try:
        yield contexto
    finally:
        _request_context.reset(token_contexto)


def _current_context() -> MCPRequestContext:
    contexto = _request_context.get()
    if contexto is not None:
        return contexto

    return MCPRequestContext(
        usuario_id=ACTA_MCP_USUARIO_ID,
        empresa_id=ACTA_MCP_EMPRESA_ID,
        trace_id=str(uuid4()),
    )


def current_mcp_request_context() -> MCPRequestContext:
    """Retorna a identidade autenticada ativa, sem fallback de ambiente."""

    contexto = _request_context.get()
    if contexto is None:
        raise MCPActaError("Não há contexto autenticado ativo para a requisição.")
    return contexto


def mcp_identity_scope() -> str:
    """Escopo estável para caches locais, sem expor a identidade ao modelo."""

    contexto = _request_context.get()
    if contexto is None:
        return "local"
    return f"empresa:{contexto.empresa_id}:usuario:{contexto.usuario_id}"


def _headers() -> dict[str, str]:
    contexto = _current_context()
    cabecalhos = {
        "X-Acta-Usuario-Id": str(contexto.usuario_id),
        "X-Acta-Empresa-Id": str(contexto.empresa_id),
        "X-Trace-Id": contexto.trace_id,
    }
    chave_api = os.getenv("ACTA_MCP_API_KEY", ACTA_MCP_API_KEY)
    if chave_api:
        cabecalhos["Authorization"] = f"Bearer {chave_api}"
    return cabecalhos


def _is_transient_error(erro: BaseException) -> bool:
    """Reconhece apenas falhas temporárias que podem melhorar numa nova tentativa."""

    if isinstance(erro, BaseExceptionGroup):
        return any(_is_transient_error(erro_interno) for erro_interno in erro.exceptions)
    if isinstance(erro, (TimeoutError, ConnectionError)):
        return True
    codigo_status = getattr(getattr(erro, "response", None), "status_code", None)
    if codigo_status in {408, 429, 500, 502, 503, 504}:
        return True
    mensagem_erro = str(erro).lower()
    return any(
        marcador in mensagem_erro
        for marcador in (
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


async def _call_tool_once(nome_ferramenta: str, argumentos: dict) -> dict | str:
    endereco = os.getenv("ACTA_MCP_URL", ACTA_MCP_URL)
    limite_tempo = float(
        os.getenv("ACTA_MCP_TIMEOUT_SECONDS", str(ACTA_MCP_TIMEOUT_SECONDS))
    )

    async with streamablehttp_client(
        endereco,
        headers=_headers(),
        timeout=limite_tempo,
        sse_read_timeout=limite_tempo,
    ) as fluxos:
        fluxo_leitura, fluxo_escrita, _ = fluxos
        async with ClientSession(fluxo_leitura, fluxo_escrita) as sessao:
            await sessao.initialize()
            resposta = await sessao.call_tool(nome_ferramenta, argumentos)

    if resposta.isError:
        mensagens = [
            getattr(conteudo, "text", str(conteudo)) for conteudo in resposta.content
        ]
        raise MCPActaError(
            f"A tool MCP '{nome_ferramenta}' retornou erro: {' '.join(mensagens)}"
        )

    if resposta.structuredContent is not None:
        return resposta.structuredContent

    partes_texto = [
        conteudo.text for conteudo in resposta.content if hasattr(conteudo, "text")
    ]
    texto_bruto = "\n".join(partes_texto)
    try:
        return json.loads(texto_bruto)
    except json.JSONDecodeError:
        return texto_bruto


async def _call_tool_async(nome_ferramenta: str, argumentos: dict) -> dict | str:
    from agents.execucao import TOOLS_LEITURA

    max_tentativas = max(
        1,
        int(os.getenv("ACTA_MCP_MAX_ATTEMPTS", str(ACTA_MCP_MAX_ATTEMPTS))),
    )
    if nome_ferramenta not in TOOLS_LEITURA:
        max_tentativas = 1
    for tentativa in range(1, max_tentativas + 1):
        try:
            return await _call_tool_once(nome_ferramenta, argumentos)
        except Exception as erro:
            if tentativa == max_tentativas or not _is_transient_error(erro):
                raise MCPActaError(
                    f"Falha ao chamar a tool MCP '{nome_ferramenta}': {erro}"
                ) from erro
            logger.warning(
                "Falha MCP transitória em %s (tentativa %s/%s): %s",
                nome_ferramenta,
                tentativa,
                max_tentativas,
                erro,
            )
            await asyncio.sleep(0.2 * tentativa)


def _run_async_in_sync_context(nome_ferramenta: str, argumentos: dict) -> dict | str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_call_tool_async(nome_ferramenta, argumentos))

    resultado: list[dict | str] = []
    erro: list[Exception] = []

    def executar() -> None:
        try:
            resultado.append(asyncio.run(_call_tool_async(nome_ferramenta, argumentos)))
        except Exception as erro_execucao:  # noqa: BLE001 - propagado à thread chamadora
            erro.append(erro_execucao)

    fio = threading.Thread(target=copy_context().run, args=(executar,), daemon=True)
    fio.start()
    fio.join()
    if erro:
        raise erro[0]
    return resultado[0]


def _registrar_ciclos_descobertos(resultado: dict | str) -> None:
    if not isinstance(resultado, dict) or resultado.get("status") != "ok":
        return
    ids_descobertos = {
        ciclo.get("id_ciclo")
        for ciclo in resultado.get("ciclos", [])
        if isinstance(ciclo, dict)
        and isinstance(ciclo.get("id_ciclo"), int)
        and ciclo["id_ciclo"] > 0
    }
    escopo_descoberto = _discovered_cycle_scope.get()
    if escopo_descoberto is None:
        _discovered_cycle_scope.set(ids_descobertos)
    else:
        escopo_descoberto.update(ids_descobertos)


def call_acta_tool(tool_name: str, arguments: dict) -> dict | str:
    """Executa uma tool no MCP ACTA preservando resultado estruturado."""
    argumentos_validos = {
        chave: valor
        for chave, valor in arguments.items()
        if valor is not None and chave != "id_empresa"
    }
    ciclos_autorizados = _cycle_scope.get()
    ciclos_descobertos = _discovered_cycle_scope.get() or set()
    busca_ciclos = tool_name == "ciclos_buscar_por_descricao"
    if (
        ciclos_autorizados is not None
        and tool_name not in {
            "faq_retriever",
            "ciclos_buscar_por_descricao",
            *FERRAMENTAS_LEITURA_ENTRE_CICLOS,
        }
        and argumentos_validos.get("id_ciclo") not in (ciclos_autorizados | ciclos_descobertos)
    ):
        resultado = {"status": "forbidden", "erro": "Ciclo fora do escopo desta requisição."}
        _registrar_evidencia_tool(tool_name, argumentos_validos, resultado, cached=False)
        return resultado
    from agents.execucao import TOOLS_LEITURA, avaliar_transacao

    eh_leitura = tool_name in TOOLS_LEITURA
    if not eh_leitura:
        # O wrapper já resolveu defaults/contexto. O juiz recebe o payload efetivo.
        intencao, avaliacao = avaliar_transacao(tool_name, argumentos_validos)
        if avaliacao.decisao == "corrigir_proposta":
            return {
                "status": "corrigir_proposta",
                "motivo": avaliacao.motivo,
                "intencao": intencao.model_dump(),
                "instrucao": "Corrija a proposta com os dados disponíveis e proponha novamente. Nada foi executado.",
            }
        argumentos_validos = intencao.argumentos

    # Escritas nunca usam cache: cada aprovação corresponde a uma chamada real.
    cache = _request_cache.get() if eh_leitura else None
    chave_cache = json.dumps(
        [tool_name, argumentos_validos],
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    if cache is not None and chave_cache in cache:
        logger.debug("Cache MCP da requisição: hit em %s", tool_name)
        resultado_cache = cache[chave_cache]
        if busca_ciclos:
            _registrar_ciclos_descobertos(resultado_cache)
        _registrar_evidencia_tool(
            tool_name, argumentos_validos, resultado_cache, cached=True
        )
        return resultado_cache

    try:
        resultado = _run_async_in_sync_context(tool_name, argumentos_validos)
    except Exception as erro:
        _registrar_evidencia_tool(
            tool_name,
            argumentos_validos,
            {"status": "error", "tipo": type(erro).__name__},
            cached=False,
        )
        if not eh_leitura:
            from agents.intencao import ExecucaoBloqueada

            raise ExecucaoBloqueada(
                "Não consegui confirmar o resultado da alteração. A operação não foi repetida automaticamente."
            ) from erro
        raise
    if cache is not None:
        cache[chave_cache] = resultado
    if busca_ciclos:
        _registrar_ciclos_descobertos(resultado)
    _registrar_evidencia_tool(tool_name, argumentos_validos, resultado, cached=False)
    return resultado
