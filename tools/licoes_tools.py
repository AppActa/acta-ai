"""Tools MCP do agente conversacional de lições aprendidas."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from langchain_core.tools import tool

from clients.mcp_acta_client import call_acta_tool

_active_cycle_id: ContextVar[int | None] = ContextVar("acta_ai_lesson_cycle", default=None)
_cross_cycle_reads_allowed: ContextVar[bool] = ContextVar(
    "acta_ai_cross_cycle_lesson_reads_allowed", default=False
)


@contextmanager
def licoes_context(*, id_ciclo: int | None, permitir_entre_ciclos: bool = False):
    cycle_token = _active_cycle_id.set(id_ciclo)
    cross_cycle_token = _cross_cycle_reads_allowed.set(permitir_entre_ciclos)
    try:
        yield
    finally:
        _cross_cycle_reads_allowed.reset(cross_cycle_token)
        _active_cycle_id.reset(cycle_token)


def _cycle(id_ciclo: int | None = None) -> int:
    cycle_id = id_ciclo if id_ciclo is not None else _active_cycle_id.get()
    if cycle_id is None:
        raise ValueError("Informe o ciclo para consultar lições aprendidas.")
    return cycle_id


def _entre_ciclos_permitido() -> dict[str, str] | None:
    if _cross_cycle_reads_allowed.get():
        return None
    return {"status": "fora_do_escopo"}


@tool("licoes_criar")
def criar_licao_aprendida(id_ciclo: int, contexto: str, expectativa: str) -> dict[str, Any]:
    """Cria uma lição, gera o PDF e o anexa ao ciclo ativo autorizado."""
    return call_acta_tool("licoes_criar", {"id_ciclo": id_ciclo, "contexto": contexto, "expectativa": expectativa})

@tool
def resumir_licoes_aprendidas(id_ciclo: int | None = None) -> dict[str, Any]:
    """Resume lições do ciclo informado ou do ciclo ativo autorizado."""
    return call_acta_tool("licoes_resumir", {"id_ciclo": _cycle(id_ciclo)})


@tool
def consultar_licoes_aprendidas(pergunta: str, id_ciclo: int | None = None) -> dict[str, Any]:
    """Consulta lições do ciclo informado ou do ciclo ativo autorizado."""
    return call_acta_tool(
        "licoes_perguntar",
        {"id_ciclo": _cycle(id_ciclo), "pergunta": pergunta},
    )


@tool
def listar_licoes_entre_ciclos(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """Lista lições aprendidas nos ciclos autorizados do usuário."""
    blocked = _entre_ciclos_permitido()
    if blocked:
        return blocked

    return call_acta_tool("licoes_listar_entre_ciclos", {"limit": limit, "offset": offset})


@tool
def resumir_licoes_entre_ciclos(limit: int = 200) -> dict[str, Any]:
    """Resume lições aprendidas entre ciclos autorizados."""
    blocked = _entre_ciclos_permitido()
    if blocked:
        return blocked

    return call_acta_tool("licoes_resumir_entre_ciclos", {"limit": limit})


@tool
def consultar_licoes_entre_ciclos(pergunta: str, limit: int = 200) -> dict[str, Any]:
    """Responde usando lições entre ciclos autorizados e informa ciclo de cada referência."""
    blocked = _entre_ciclos_permitido()
    if blocked:
        return blocked

    return call_acta_tool(
        "licoes_perguntar_entre_ciclos", {"pergunta": pergunta, "limit": limit}
    )


TOOLS = [
    criar_licao_aprendida,
    resumir_licoes_aprendidas,
    consultar_licoes_aprendidas,
    listar_licoes_entre_ciclos,
    resumir_licoes_entre_ciclos,
    consultar_licoes_entre_ciclos,
]
