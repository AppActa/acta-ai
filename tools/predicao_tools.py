"""Tools LangChain de predição do ACTA."""

from langchain_core.tools import tool

from tools.common import call_mcp_tool


@tool
def predicoes_risco_atraso_tarefa(id_tarefa: int) -> dict | str:
    """Estima a probabilidade de atraso de uma tarefa."""
    return call_mcp_tool("predicoes_risco_atraso_tarefa", id_tarefa=id_tarefa)


@tool
def predicoes_estimativa_conclusao_tarefa(id_tarefa: int) -> dict | str:
    """Estima a data de conclusão de uma tarefa."""
    return call_mcp_tool("predicoes_estimativa_conclusao_tarefa", id_tarefa=id_tarefa)


@tool
def predicoes_risco_atraso_ciclo(id_ciclo: int) -> dict | str:
    """Estima a probabilidade de atraso de um ciclo."""
    return call_mcp_tool("predicoes_risco_atraso_ciclo", id_ciclo=id_ciclo)


@tool
def predicoes_estimativa_conclusao_ciclo(id_ciclo: int) -> dict | str:
    """Estima a data de conclusão de um ciclo."""
    return call_mcp_tool("predicoes_estimativa_conclusao_ciclo", id_ciclo=id_ciclo)


@tool
def predicoes_conclusao_treinamento(
    id_ciclo: int,
    id_treinamento: int,
) -> dict | str:
    """Estima a chance de conclusão de um treinamento por participante."""
    return call_mcp_tool(
        "predicoes_conclusao_treinamento",
        id_ciclo=id_ciclo,
        id_treinamento=id_treinamento,
    )


@tool
def predicoes_sobrecarga_colaborador(
    id_ciclo: int,
    id_colaborador: int | None = None,
) -> dict | str:
    """Estima risco de sobrecarga dos colaboradores do ciclo."""
    return call_mcp_tool(
        "predicoes_sobrecarga_colaborador",
        id_ciclo=id_ciclo,
        id_colaborador=id_colaborador,
    )


@tool
def predicoes_atingimento_meta(
    id_ciclo: int,
    id_meta: int | None = None,
) -> dict | str:
    """Estima a probabilidade de atingimento das metas do ciclo."""
    return call_mcp_tool(
        "predicoes_atingimento_meta",
        id_ciclo=id_ciclo,
        id_meta=id_meta,
    )


@tool
def predicoes_respostas_atipicas(
    id_ciclo: int,
    id_formulario: str,
    limit: int = 200,
) -> dict | str:
    """Detecta respostas estatisticamente atípicas em um formulário."""
    return call_mcp_tool(
        "predicoes_respostas_atipicas",
        id_ciclo=id_ciclo,
        id_formulario=id_formulario,
        limit=limit,
    )


@tool
def predicoes_tema_formulario(
    id_ciclo: int,
    id_formulario: str,
    limit: int = 200,
) -> dict | str:
    """Classifica os temas das respostas de um formulário."""
    return call_mcp_tool(
        "predicoes_tema_formulario",
        id_ciclo=id_ciclo,
        id_formulario=id_formulario,
        limit=limit,
    )


@tool
def predicoes_recorrencia_problema(
    id_ciclo: int,
    id_problema: int | None = None,
) -> dict | str:
    """Estima a recorrência dos problemas do ciclo."""
    return call_mcp_tool(
        "predicoes_recorrencia_problema",
        id_ciclo=id_ciclo,
        id_problema=id_problema,
    )


TOOLS = [
    predicoes_risco_atraso_tarefa,
    predicoes_estimativa_conclusao_tarefa,
    predicoes_risco_atraso_ciclo,
    predicoes_estimativa_conclusao_ciclo,
    predicoes_conclusao_treinamento,
    predicoes_sobrecarga_colaborador,
    predicoes_atingimento_meta,
    predicoes_respostas_atipicas,
    predicoes_tema_formulario,
    predicoes_recorrencia_problema,
]
