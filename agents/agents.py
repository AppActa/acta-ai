"""Construcao centralizada dos agentes do ACTA."""

import logging

from langchain.agents import create_agent

from agents.execucao import bloquear_lote_de_escrita
from agents.helpers.llms import llm
from agents.prompts.prompt_ciclo import CICLO_PROMPT_COMPLETO
from agents.prompts.prompt_colaborador import COLABORADOR_PROMPT_COMPLETO
from agents.prompts.prompt_faq import _PROMPT_FAQ
from agents.prompts.prompt_formulario import FORMULARIO_PROMPT_COMPLETO
from agents.prompts.prompt_licoes import LICOES_PROMPT_COMPLETO
from agents.prompts.prompt_orquestrador import ORQUESTRADOR_PROMPT_COMPLETO
from agents.prompts.prompt_relatorio import RELATORIO_PROMPT_COMPLETO
from agents.prompts.prompt_tarefas import TAREFAS_PROMPT_COMPLETO
from clients.mcp_acta_client import call_acta_tool
from tools.ciclo_tools import TOOLS as CICLO_TOOLS
from tools.ciclo_tools import ciclos_buscar_por_descricao
from tools.colaborador_tools import TOOLS as COLABORADOR_TOOLS
from tools.formulario_tools import TOOLS as FORMULARIO_TOOLS
from tools.licoes_tools import TOOLS as LICOES_MCP_TOOLS
from tools.relatorio_tools import TOOLS as RELATORIO_TOOLS
from tools.tarefas_tools import TOOLS as TAREFAS_TOOLS

logger = logging.getLogger(__name__)

def _tools_com_busca_de_ciclo(tools):
    if ciclos_buscar_por_descricao in tools:
        return tools
    return [*tools, ciclos_buscar_por_descricao]

ESPECIALISTAS_VALIDOS = (
    "rag",
    "ciclo",
    "licoes",
    "tarefas",
    "colaboradores",
    "formularios",
    "indicadores",
    "relatorios",
)
ALIASES_ESPECIALISTAS = {"faq": "rag"}

TOOLS_POR_ESPECIALISTA = {
    "rag": [],
    "ciclo": CICLO_TOOLS,
    "indicadores": CICLO_TOOLS,
    "licoes": _tools_com_busca_de_ciclo(LICOES_MCP_TOOLS),
    "tarefas": _tools_com_busca_de_ciclo(TAREFAS_TOOLS),
    "colaboradores": _tools_com_busca_de_ciclo(COLABORADOR_TOOLS),
    "formularios": _tools_com_busca_de_ciclo(FORMULARIO_TOOLS),
    "relatorios": _tools_com_busca_de_ciclo(RELATORIO_TOOLS),
}

ciclo_agent = create_agent(
    model=llm,
    tools=TOOLS_POR_ESPECIALISTA["ciclo"],
    system_prompt=CICLO_PROMPT_COMPLETO,
    middleware=[bloquear_lote_de_escrita],
)
licoes_agent = create_agent(
    model=llm,
    tools=TOOLS_POR_ESPECIALISTA["licoes"],
    system_prompt=LICOES_PROMPT_COMPLETO,
    middleware=[bloquear_lote_de_escrita],
)
colaboradores_agent = create_agent(
    model=llm,
    tools=TOOLS_POR_ESPECIALISTA["colaboradores"],
    system_prompt=COLABORADOR_PROMPT_COMPLETO,
    middleware=[bloquear_lote_de_escrita],
)
formularios_agent = create_agent(
    model=llm,
    tools=TOOLS_POR_ESPECIALISTA["formularios"],
    system_prompt=FORMULARIO_PROMPT_COMPLETO,
    middleware=[bloquear_lote_de_escrita],
)
relatorios_agent = create_agent(
    model=llm,
    tools=TOOLS_POR_ESPECIALISTA["relatorios"],
    system_prompt=RELATORIO_PROMPT_COMPLETO,
    middleware=[bloquear_lote_de_escrita],
)
tarefas_agent = create_agent(
    model=llm,
    tools=TOOLS_POR_ESPECIALISTA["tarefas"],
    system_prompt=TAREFAS_PROMPT_COMPLETO,
    middleware=[bloquear_lote_de_escrita],
)

orquestrador = create_agent(
    model=llm,
    system_prompt=ORQUESTRADOR_PROMPT_COMPLETO,
)


def responder_faq(pergunta: str, *, feedback: str = "") -> str:
    """Responde perguntas conceituais usando a base de conhecimento do ACTA."""

    pergunta = pergunta.strip()
    if not pergunta:
        return "Não recebi uma pergunta válida para responder."

    try:
        result = call_acta_tool("faq_retriever", {"question": pergunta, "limit": 3})
        if not isinstance(result, dict) or result.get("status") != "ok":
            return "Não consegui consultar a base de conhecimento do ACTA no momento."
        contexto = "\n\n---\n\n".join(
            "\n".join(
                part
                for part in (
                    f"Fonte: {item.get('source', '')}",
                    f"Título: {item.get('title', '')}",
                    item.get("content", ""),
                )
                if part
            )
            for item in result.get("resultados", [])
        )
        if not contexto or not contexto.strip():
            return "Não encontrei informação suficiente na base do ACTA para responder essa pergunta."
        prompt = _PROMPT_FAQ.format(contexto=contexto, pergunta=pergunta)
        if feedback:
            prompt += f"\nRevisão solicitada pelo juiz: {feedback}\nCorrija somente com as evidências fornecidas."
        resposta = llm.invoke(prompt).text
        return resposta.strip()
    except Exception:
        logger.exception("Falha ao responder pelo especialista FAQ/RAG")
        return (
            "Não consegui consultar a base de conhecimento do ACTA no momento. "
            "Tente novamente em alguns instantes."
        )

__all__ = [
    "ALIASES_ESPECIALISTAS",
    "ESPECIALISTAS_VALIDOS",
    "ciclo_agent",
    "colaboradores_agent",
    "formularios_agent",
    "licoes_agent",
    "orquestrador",
    "responder_faq",
    "relatorios_agent",
    "tarefas_agent",
]
