"""Tools LangChain de relatórios do ACTA."""

from langchain_core.tools import tool

from tools.common import call_mcp_tool


@tool
def relatorios_contexto_ciclo(id_ciclo: int, limit: int = 50) -> dict | str:
    """Coleta evidências atuais para produzir um relatório textual do ciclo."""

    return call_mcp_tool(
        "relatorios_contexto_ciclo",
        id_ciclo=id_ciclo,
        limit=limit,
    )


TOOLS = [relatorios_contexto_ciclo]
