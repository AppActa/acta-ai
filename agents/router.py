"""Agente responsável apenas por selecionar especialistas."""

from langchain.agents import create_agent

from agents.helpers.llms import llm_fast
from agents.prompts.prompt_roteador import _PROMPT_ROTEADOR

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

router = create_agent(
    model=llm_fast,
    system_prompt=_PROMPT_ROTEADOR,
)
