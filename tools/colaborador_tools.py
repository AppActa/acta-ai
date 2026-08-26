"""Tools LangChain de colaboradores do ACTA."""

from typing import Literal

from langchain_core.tools import tool

from tools.common import call_mcp_tool

StatusColaborador = Literal["ATIVO", "INATIVO", "PENDENTE", "BLOQUEADO", "ARQUIVADO"]
TipoUsuario = Literal["ADMIN", "GESTOR", "COLABORADOR"]


@tool
def colaboradores_consultar(
    id_ciclo: int | None = None,
    nome: str | None = None,
    area: str | None = None,
    cargo: str | None = None,
    status: StatusColaborador | None = None,
    tipo_usuario: TipoUsuario | None = None,
    permissao_gestor: bool | None = None,
    limit: int = 50,
) -> dict | str:
    """Consulta colaboradores da empresa autenticada com filtros opcionais."""

    return call_mcp_tool(
        "colaboradores_consultar",
        id_ciclo=id_ciclo,
        nome=nome,
        area=area,
        cargo=cargo,
        status=status,
        tipo_usuario=tipo_usuario,
        permissao_gestor=permissao_gestor,
        limit=limit,
    )


@tool
def colaborador_detalhes(
    id_colaborador: int,
    id_ciclo: int | None = None,
) -> dict | str:
    """Consulta detalhes profissionais e alocações de um colaborador autorizado."""

    return call_mcp_tool(
        "colaborador_detalhes",
        id_colaborador=id_colaborador,
        id_ciclo=id_ciclo,
    )


@tool
def colaboradores_participantes_ciclo(id_ciclo: int, limit: int = 50) -> dict | str:
    """Lista colaboradores participantes de um ciclo e seus papéis."""

    return call_mcp_tool(
        "colaboradores_participantes_ciclo",
        id_ciclo=id_ciclo,
        limit=limit,
    )


@tool
def colaboradores_por_area() -> dict | str:
    """Agrupa colaboradores por área dentro da empresa autenticada."""

    return call_mcp_tool("colaboradores_por_area")


@tool
def colaboradores_carga_trabalho(id_ciclo: int, limit: int = 50) -> dict | str:
    """Calcula a carga de trabalho dos participantes de um ciclo."""

    return call_mcp_tool(
        "colaboradores_carga_trabalho",
        id_ciclo=id_ciclo,
        limit=limit,
    )


@tool
def colaboradores_sugestao_realocacao(
    id_ciclo: int,
    area: str | None = None,
    cargo: str | None = None,
    limit: int = 20,
) -> dict | str:
    """Sugere candidatos por menor carga e compatibilidade de área/cargo."""

    return call_mcp_tool(
        "colaboradores_sugestao_realocacao",
        id_ciclo=id_ciclo,
        area=area,
        cargo=cargo,
        limit=limit,
    )


@tool
def colaboradores_relatorio_completo(id_ciclo: int, limit: int = 50) -> dict | str:
    """Consolida participantes, carga e candidatos para realocação."""

    return call_mcp_tool(
        "colaboradores_relatorio_completo",
        id_ciclo=id_ciclo,
        limit=limit,
    )


TOOLS = [
    colaboradores_consultar,
    colaborador_detalhes,
    colaboradores_participantes_ciclo,
    colaboradores_por_area,
    colaboradores_carga_trabalho,
    colaboradores_sugestao_realocacao,
    colaboradores_relatorio_completo,
]
