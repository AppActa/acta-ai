"""Tools LangChain do domínio de ciclos do ACTA."""

from datetime import date
from typing import Literal

from langchain_core.tools import tool

from tools.common import call_mcp_tool


@tool
def ciclo_visao_geral(id_ciclo: int) -> dict | str:
    """Consulta visão geral, contagens e status de um ciclo PDCA autorizado."""

    return call_mcp_tool("ciclo_visao_geral", id_ciclo=id_ciclo)


@tool
def ciclos_buscar_por_descricao(termo: str, limit: int = 5) -> dict | str:
    """Busca ciclos autorizados por título ou trecho da descrição."""

    return call_mcp_tool(
        "ciclos_buscar_por_descricao",
        termo=termo,
        limit=limit,
    )


@tool
def ciclo_problema_principal(id_ciclo: int) -> dict | str:
    """Consulta o problema principal e sua causa raiz prioritária."""

    return call_mcp_tool("ciclo_problema_principal", id_ciclo=id_ciclo)


@tool
def ciclo_causas_raiz(id_ciclo: int) -> dict | str:
    """Lista causas raiz registradas para o ciclo."""

    return call_mcp_tool("ciclo_causas_raiz", id_ciclo=id_ciclo)


@tool
def ciclo_ishikawa(id_ciclo: int, limit: int = 10) -> dict | str:
    """Consulta o diagrama de Ishikawa do ciclo."""

    return call_mcp_tool("ciclo_ishikawa", id_ciclo=id_ciclo, limit=limit)


@tool
def ciclo_riscos_pendencias(id_ciclo: int) -> dict | str:
    """Consolida tarefas, metas, planos e alertas em risco no ciclo."""

    return call_mcp_tool("ciclo_riscos_pendencias", id_ciclo=id_ciclo)


@tool
def ciclo_treinamentos(id_ciclo: int) -> dict | str:
    """Lista treinamentos e participantes relacionados ao ciclo."""

    return call_mcp_tool("ciclo_treinamentos", id_ciclo=id_ciclo)


@tool
def ciclo_participantes(id_ciclo: int) -> dict | str:
    """Lista os usuários participantes do ciclo e seus papéis."""

    return call_mcp_tool("ciclo_participantes", id_ciclo=id_ciclo)


@tool
def ciclo_relatorio_completo(id_ciclo: int) -> dict | str:
    """Consolida a visão completa do ciclo em resultado estruturado."""

    return call_mcp_tool("ciclo_relatorio_completo", id_ciclo=id_ciclo)


@tool
def ciclos_registrar_causa(
    id_ciclo: int,
    id_problema: int,
    descricao: str,
    id_plano_acao: int | None = None,
    aceita: bool = False,
    principal: bool = False,
) -> dict | str:
    """Registra uma causa-raiz quando o usuário solicitar explicitamente."""
    return call_mcp_tool(
        "ciclos_registrar_causa",
        id_ciclo=id_ciclo,
        id_problema=id_problema,
        descricao=descricao,
        id_plano_acao=id_plano_acao,
        aceita=aceita,
        principal=principal,
    )


@tool
def ciclos_adicionar_item_ishikawa(
    id_ciclo: int,
    categoria: Literal[
        "metodo", "mao_de_obra", "maquina", "material", "medicao", "meio_ambiente"
    ],
    causa: str,
) -> dict | str:
    """Adiciona uma causa a uma categoria permitida do Ishikawa."""
    return call_mcp_tool(
        "ciclos_adicionar_item_ishikawa",
        id_ciclo=id_ciclo,
        categoria=categoria,
        causa=causa,
    )


@tool
def treinamentos_criar(
    id_ciclo: int,
    id_responsavel: int,
    titulo: str,
    data_treinamento: date,
    descricao: str | None = None,
    obrigatorio: bool = True,
    participantes: list[int] | None = None,
) -> dict | str:
    """Cria um treinamento; exige nível geral."""
    return call_mcp_tool(
        "treinamentos_criar",
        id_ciclo=id_ciclo,
        id_responsavel=id_responsavel,
        titulo=titulo,
        data_treinamento=data_treinamento,
        descricao=descricao,
        obrigatorio=obrigatorio,
        participantes=participantes,
    )


TOOLS = [
    ciclos_buscar_por_descricao,
    ciclo_visao_geral,
    ciclo_problema_principal,
    ciclo_causas_raiz,
    ciclo_ishikawa,
    ciclo_riscos_pendencias,
    ciclo_treinamentos,
    ciclo_participantes,
    ciclo_relatorio_completo,
    ciclos_registrar_causa,
    ciclos_adicionar_item_ishikawa,
    treinamentos_criar,
]
