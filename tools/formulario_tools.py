"""Tools LangChain de formulários do ACTA."""

from typing import Literal

from langchain_core.tools import tool

from tools.common import call_mcp_tool


@tool
def formularios_listar(
    id_ciclo: int,
    id_formulario: str | None = None,
    tipo: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict | str:
    """Lista formulários autorizados do ciclo com filtros opcionais."""

    return call_mcp_tool(
        "formularios_listar",
        id_ciclo=id_ciclo,
        id_formulario=id_formulario,
        tipo=tipo,
        status=status,
        limit=limit,
    )


@tool
def formularios_detalhes(
    id_ciclo: int,
    id_formulario: str,
    limit_respostas: int = 100,
) -> dict | str:
    """Obtém um formulário autorizado e suas respostas."""

    return call_mcp_tool(
        "formularios_detalhes",
        id_ciclo=id_ciclo,
        id_formulario=id_formulario,
        limit_respostas=limit_respostas,
    )


@tool
def formularios_respostas(
    id_ciclo: int,
    id_formulario: str | None = None,
    limit: int = 100,
) -> dict | str:
    """Consulta as respostas dos formulários autorizados de um ciclo."""

    return call_mcp_tool(
        "formularios_respostas",
        id_ciclo=id_ciclo,
        id_formulario=id_formulario,
        limit=limit,
    )


@tool
def formularios_resumo_respostas(
    id_ciclo: int,
    id_formulario: str | None = None,
    limit: int = 200,
) -> dict | str:
    """Resume respostas e identifica frequências e padrões repetidos."""

    return call_mcp_tool(
        "formularios_resumo_respostas",
        id_ciclo=id_ciclo,
        id_formulario=id_formulario,
        limit=limit,
    )


@tool
def formularios_criar_rascunho(
    id_ciclo: int,
    titulo: str,
    tipo: str,
    descricao: str | None = None,
) -> dict | str:
    """Cria um formulário em rascunho; todas as tools de formulários exigem geral."""
    return call_mcp_tool(
        "formularios_criar_rascunho",
        id_ciclo=id_ciclo,
        titulo=titulo,
        tipo=tipo,
        descricao=descricao,
    )


@tool
def formularios_adicionar_pergunta(
    id_ciclo: int,
    id_formulario: str,
    texto: str,
    tipo_resposta: Literal[
        "TEXTO", "NUMERO", "DATA", "BOOLEANO", "SELECAO_UNICA", "MULTIPLA"
    ],
    obrigatoria: bool = False,
    opcoes: list[str] | None = None,
) -> dict | str:
    """Adiciona uma pergunta estruturada a um formulário em rascunho."""
    return call_mcp_tool(
        "formularios_adicionar_pergunta",
        id_ciclo=id_ciclo,
        id_formulario=id_formulario,
        texto=texto,
        tipo_resposta=tipo_resposta,
        obrigatoria=obrigatoria,
        opcoes=opcoes,
    )


@tool
def formularios_publicar(id_ciclo: int, id_formulario: str) -> dict | str:
    """Publica um formulário com perguntas após solicitação explícita."""
    return call_mcp_tool(
        "formularios_publicar",
        id_ciclo=id_ciclo,
        id_formulario=id_formulario,
    )


TOOLS = [
    formularios_listar,
    formularios_detalhes,
    formularios_respostas,
    formularios_resumo_respostas,
    formularios_criar_rascunho,
    formularios_adicionar_pergunta,
    formularios_publicar,
]
