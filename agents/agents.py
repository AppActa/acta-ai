"""Construcao centralizada dos agentes do ACTA."""

import logging

from langchain.agents import create_agent

from agents.helpers.llms import llm
from agents.prompts.prompt_ciclo import CICLO_PROMPT_COMPLETO
from agents.prompts.prompt_colaborador import COLABORADOR_PROMPT_COMPLETO
from agents.prompts.prompt_faq import _PROMPT_FAQ
from agents.prompts.prompt_formulario import FORMULARIO_PROMPT_COMPLETO
from agents.prompts.prompt_indicadores import INDICADORES_PROMPT_COMPLETO
from agents.prompts.prompt_licoes import LICOES_PROMPT_COMPLETO
from agents.prompts.prompt_orquestrador import ORQUESTRADOR_PROMPT_COMPLETO
from agents.prompts.prompt_relatorio import RELATORIO_PROMPT_COMPLETO
from agents.prompts.prompt_tarefas import TAREFAS_PROMPT_COMPLETO
from clients.mcp_acta_client import call_acta_tool
from tools.ciclo_tools import TOOLS as CICLO_TOOLS
from tools.colaborador_tools import TOOLS as COLABORADOR_TOOLS
from tools.formulario_tools import TOOLS as FORMULARIO_TOOLS
from tools.indicador_tools import TOOLS as INDICADORES_TOOLS
from tools.licoes_tools import TOOLS as LICOES_MCP_TOOLS
from tools.relatorio_tools import TOOLS as RELATORIO_TOOLS
from tools.tarefas_tools import TOOLS as TAREFAS_TOOLS

logger = logging.getLogger(__name__)

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

ciclo_agent = create_agent(
    model=llm,
    tools=CICLO_TOOLS,
    system_prompt=CICLO_PROMPT_COMPLETO,
)
licoes_agent = create_agent(
    model=llm,
    tools=LICOES_MCP_TOOLS,
    system_prompt=LICOES_PROMPT_COMPLETO,
)
colaboradores_agent = create_agent(
    model=llm,
    tools=COLABORADOR_TOOLS,
    system_prompt=COLABORADOR_PROMPT_COMPLETO,
)
formularios_agent = create_agent(
    model=llm,
    tools=FORMULARIO_TOOLS,
    system_prompt=FORMULARIO_PROMPT_COMPLETO,
)
indicadores_agent = create_agent(
    model=llm,
    tools=INDICADORES_TOOLS,
    system_prompt=INDICADORES_PROMPT_COMPLETO,
)
relatorios_agent = create_agent(
    model=llm,
    tools=RELATORIO_TOOLS,
    system_prompt=RELATORIO_PROMPT_COMPLETO,
)
tarefas_agent = create_agent(
    model=llm,
    tools=TAREFAS_TOOLS,
    system_prompt=TAREFAS_PROMPT_COMPLETO,
)

orquestrador = create_agent(
    model=llm,
    system_prompt=ORQUESTRADOR_PROMPT_COMPLETO,
)


def responder_faq(pergunta: str) -> str:
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
        resposta = llm.invoke(
            _PROMPT_FAQ.format(contexto=contexto, pergunta=pergunta)
        ).content
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
    "indicadores_agent",
    "licoes_agent",
    "orquestrador",
    "responder_faq",
    "relatorios_agent",
    "tarefas_agent",
]
