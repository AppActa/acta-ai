"""Tools LangChain do domínio de tarefas do ACTA."""

from datetime import date
from typing import Literal

from langchain_core.tools import tool

from tools.common import call_mcp_tool

StatusTarefa = Literal[
    "PENDENTE",
    "EM_ANDAMENTO",
    "BLOQUEADA",
    "CONCLUIDA",
    "ATRASADA",
    "CANCELADA",
]
PrioridadeTarefa = Literal["BAIXA", "MEDIA", "ALTA", "CRITICA"]


@tool
def tarefas_consultar(
    id_ciclo: int,
    id_responsavel: int | None = None,
    status: StatusTarefa | None = None,
    prioridade: PrioridadeTarefa | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    apenas_atrasadas: bool = False,
    limit: int = 50,
) -> dict | str:
    """Consulta tarefas autorizadas de um ciclo com filtros opcionais."""

    return call_mcp_tool(
        "tarefas_consultar",
        id_ciclo=id_ciclo,
        id_responsavel=id_responsavel,
        status=status,
        prioridade=prioridade,
        data_inicio=data_inicio,
        data_fim=data_fim,
        apenas_atrasadas=apenas_atrasadas,
        limit=limit,
    )


@tool
def tarefas_atrasadas(id_ciclo: int, limit: int = 50) -> dict | str:
    """Lista tarefas atrasadas ou vencidas de um ciclo autorizado."""

    return call_mcp_tool("tarefas_atrasadas", id_ciclo=id_ciclo, limit=limit)


@tool
def tarefas_concluidas(
    id_ciclo: int,
    id_responsavel: int | None = None,
    prioridade: PrioridadeTarefa | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    limit: int = 50,
) -> dict | str:
    """Lista tarefas concluídas de um ciclo autorizado."""

    return call_mcp_tool(
        "tarefas_concluidas",
        id_ciclo=id_ciclo,
        id_responsavel=id_responsavel,
        prioridade=prioridade,
        data_inicio=data_inicio,
        data_fim=data_fim,
        limit=limit,
    )


@tool
def tarefas_detalhes(id_tarefa: int) -> dict | str:
    """Consulta detalhes, dependências e bloqueios de uma tarefa autorizada."""

    return call_mcp_tool("tarefas_detalhes", id_tarefa=id_tarefa)


@tool
def tarefas_por_responsavel(
    id_ciclo: int,
    id_responsavel: int | None = None,
) -> dict | str:
    """Agrupa tarefas por responsável e status no ciclo."""

    return call_mcp_tool(
        "tarefas_por_responsavel",
        id_ciclo=id_ciclo,
        id_responsavel=id_responsavel,
    )


@tool
def tarefas_alertas_prazo(
    id_ciclo: int,
    somente_nao_lidos: bool = False,
) -> dict | str:
    """Consulta alertas de prazo das tarefas do ciclo."""

    return call_mcp_tool(
        "tarefas_alertas_prazo",
        id_ciclo=id_ciclo,
        somente_nao_lidos=somente_nao_lidos,
    )


@tool
def tarefas_relatorio_completo(id_ciclo: int, limit: int = 50) -> dict | str:
    """Consolida tarefas, atrasos, responsáveis e alertas de prazo."""

    return call_mcp_tool(
        "tarefas_relatorio_completo",
        id_ciclo=id_ciclo,
        limit=limit,
    )


@tool
def tarefas_criar(
    id_ciclo: int,
    id_plano_acao: int,
    id_responsavel: int,
    titulo: str,
    descricao: str,
    data_fim_prevista: date,
    prioridade: PrioridadeTarefa = "MEDIA",
) -> dict | str:
    """Cria uma tarefa quando o usuário pedir explicitamente e possuir acesso create."""
    return call_mcp_tool(
        "tarefas_criar",
        id_ciclo=id_ciclo,
        id_plano_acao=id_plano_acao,
        id_responsavel=id_responsavel,
        titulo=titulo,
        descricao=descricao,
        data_fim_prevista=data_fim_prevista,
        prioridade=prioridade,
    )


@tool
def tarefas_atualizar(
    id_tarefa: int,
    titulo: str | None = None,
    descricao: str | None = None,
    id_responsavel: int | None = None,
    prioridade: PrioridadeTarefa | None = None,
    data_fim_prevista: date | None = None,
) -> dict | str:
    """Atualiza somente os campos explicitamente solicitados de uma tarefa."""
    return call_mcp_tool(
        "tarefas_atualizar",
        id_tarefa=id_tarefa,
        titulo=titulo,
        descricao=descricao,
        id_responsavel=id_responsavel,
        prioridade=prioridade,
        data_fim_prevista=data_fim_prevista,
    )


@tool
def tarefas_atualizar_status(id_tarefa: int, status: StatusTarefa) -> dict | str:
    """Atualiza o status de uma tarefa quando solicitado explicitamente."""
    return call_mcp_tool("tarefas_atualizar_status", id_tarefa=id_tarefa, status=status)


TOOLS = [
    tarefas_consultar,
    tarefas_atrasadas,
    tarefas_concluidas,
    tarefas_detalhes,
    tarefas_por_responsavel,
    tarefas_alertas_prazo,
    tarefas_relatorio_completo,
    tarefas_criar,
    tarefas_atualizar,
    tarefas_atualizar_status,
]
