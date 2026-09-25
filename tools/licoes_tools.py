"""Tools MCP do agente conversacional de lições aprendidas."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from langchain_core.tools import tool

from clients.mcp_acta_client import call_acta_tool

_active_cycle_id: ContextVar[int | None] = ContextVar("acta_ai_lesson_cycle", default=None)


@contextmanager
def licoes_context(*, id_ciclo: int):
    token = _active_cycle_id.set(id_ciclo)
    try:
        yield
    finally:
        _active_cycle_id.reset(token)


def _cycle() -> int:
    cycle_id = _active_cycle_id.get()
    if cycle_id is None:
        raise ValueError("Informe o ciclo para consultar lições aprendidas.")
    return cycle_id


@tool
def criar_licao_aprendida(contexto: str, expectativa: str) -> dict[str, Any]:
    """Cria uma lição, gera o PDF e o anexa ao ciclo ativo autorizado."""
    return call_acta_tool("licoes_criar", {"id_ciclo": _cycle(), "contexto": contexto, "expectativa": expectativa})


@tool
def resumir_licoes_aprendidas() -> dict[str, Any]:
    """Resume as lições aprendidas do ciclo ativo autorizado."""
    return call_acta_tool("licoes_resumir", {"id_ciclo": _cycle()})


@tool
def consultar_licoes_aprendidas(pergunta: str) -> dict[str, Any]:
    """Responde usando lições do ciclo ativo e informa as referências consultadas."""
    return call_acta_tool("licoes_perguntar", {"id_ciclo": _cycle(), "pergunta": pergunta})


TOOLS = [criar_licao_aprendida, resumir_licoes_aprendidas, consultar_licoes_aprendidas]
