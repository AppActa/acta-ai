"""Construcao centralizada dos agentes do ACTA."""

import logging

from langchain.agents import create_agent

from agents.helpers.llms import llm_fast, llm_tool_agents, llm_tool_fast_agents
from agents.prompts.prompt_ciclo import CICLO_PROMPT_COMPLETO
from agents.prompts.prompt_colaborador import COLABORADOR_PROMPT_COMPLETO
from agents.prompts.prompt_faq import _PROMPT_FAQ
from agents.prompts.prompt_formulario import FORMULARIO_PROMPT_COMPLETO
from agents.prompts.prompt_indicadores import INDICADORES_PROMPT_COMPLETO
from agents.prompts.prompt_juiz import JUIZ_PROMPT_COMPLETO
from agents.prompts.prompt_orquestrador import ORQUESTRADOR_PROMPT_COMPLETO
from agents.prompts.prompt_predicao import PREDICAO_PROMPT_COMPLETO
from agents.prompts.prompt_relatorio import RELATORIO_PROMPT_COMPLETO
from agents.prompts.prompt_roteador import _PROMPT_ROTEADOR
from agents.prompts.prompt_tarefas import TAREFAS_PROMPT_COMPLETO
from tools.ciclo_tools import TOOLS as CICLO_TOOLS
from tools.colaborador_tools import TOOLS as COLABORADOR_TOOLS
from tools.faq_tools import faq_retriever
from tools.formulario_tools import TOOLS as FORMULARIO_TOOLS
from tools.indicador_tools import TOOLS as INDICADORES_TOOLS
from tools.licoes_tools import TOOLS as LICOES_A2A_TOOLS
from tools.predicao_tools import TOOLS as PREDICAO_TOOLS
from tools.relatorio_tools import TOOLS as RELATORIO_TOOLS
from tools.tarefas_tools import TOOLS as TAREFAS_TOOLS

logger = logging.getLogger(__name__)

ESPECIALISTAS_VALIDOS = (
    "rag",
    "ciclo",
    "tarefas",
    "colaboradores",
    "formularios",
    "indicadores",
    "relatorios",
    "predicoes",
)
ALIASES_ESPECIALISTAS = {"faq": "rag"}

ciclo_agent = create_agent(
    model=llm_tool_agents,
    tools=[*CICLO_TOOLS, *LICOES_A2A_TOOLS],
    system_prompt=CICLO_PROMPT_COMPLETO,
)
colaboradores_agent = create_agent(
    model=llm_tool_agents,
    tools=COLABORADOR_TOOLS,
    system_prompt=COLABORADOR_PROMPT_COMPLETO,
)
formularios_agent = create_agent(
    model=llm_tool_agents,
    tools=FORMULARIO_TOOLS,
    system_prompt=FORMULARIO_PROMPT_COMPLETO,
)
indicadores_agent = create_agent(
    model=llm_tool_fast_agents,
    tools=INDICADORES_TOOLS,
    system_prompt=INDICADORES_PROMPT_COMPLETO,
)
predicoes_agent = create_agent(
    model=llm_tool_agents,
    tools=PREDICAO_TOOLS,
    system_prompt=PREDICAO_PROMPT_COMPLETO,
)
relatorios_agent = create_agent(
    model=llm_tool_agents,
    tools=RELATORIO_TOOLS,
    system_prompt=RELATORIO_PROMPT_COMPLETO,
)
tarefas_agent = create_agent(
    model=llm_tool_agents,
    tools=TAREFAS_TOOLS,
    system_prompt=TAREFAS_PROMPT_COMPLETO,
)

router = create_agent(model=llm_fast, system_prompt=_PROMPT_ROTEADOR)
orquestrador = create_agent(
    model=llm_fast,
    system_prompt=ORQUESTRADOR_PROMPT_COMPLETO,
)
juiz = create_agent(model=llm_fast, system_prompt=JUIZ_PROMPT_COMPLETO)


def responder_faq(pergunta: str) -> str:
    """Responde perguntas conceituais usando a base de conhecimento do ACTA."""

    pergunta = pergunta.strip()
    if not pergunta:
        return "Não recebi uma pergunta válida para responder."

    try:
        contexto = faq_retriever.invoke(pergunta)
        if not contexto or not contexto.strip():
            return "Não encontrei informação suficiente na base do ACTA para responder essa pergunta."
        resposta = llm_fast.invoke(
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
    "juiz",
    "orquestrador",
    "predicoes_agent",
    "responder_faq",
    "relatorios_agent",
    "router",
    "tarefas_agent",
]
