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

@tool("licoes_criar")
def criar_licao_aprendida(id_ciclo: int, contexto: str, expectativa: str) -> dict[str, Any]:
    """Cria uma lição, gera o PDF e o anexa ao ciclo ativo autorizado."""
    return call_acta_tool("licoes_criar", {"id_ciclo": id_ciclo, "contexto": contexto, "expectativa": expectativa})

@tool
def resumir_licoes_aprendidas() -> dict[str, Any]:
    """Resume as lições aprendidas do ciclo ativo autorizado."""
    return call_acta_tool("licoes_resumir", {"id_ciclo": _cycle()})

@tool
def consultar_licoes_aprendidas(pergunta: str) -> dict[str, Any]:
    """Responde usando lições do ciclo ativo e informa as referências consultadas."""
    return call_acta_tool("licoes_perguntar", {"id_ciclo": _cycle(), "pergunta": pergunta})


@tool
def listar_licoes_entre_ciclos(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """Lista lições aprendidas nos ciclos autorizados do usuário."""
    return call_acta_tool("licoes_listar_entre_ciclos", {"limit": limit, "offset": offset})


@tool
def resumir_licoes_entre_ciclos(limit: int = 200) -> dict[str, Any]:
    """Resume lições aprendidas entre ciclos autorizados."""
    return call_acta_tool("licoes_resumir_entre_ciclos", {"limit": limit})


@tool
def consultar_licoes_entre_ciclos(pergunta: str, limit: int = 200) -> dict[str, Any]:
    """Responde usando lições entre ciclos autorizados e informa ciclo de cada referência."""
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
