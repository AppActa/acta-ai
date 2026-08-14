"""Agente especialista em indicadores e metas dos ciclos ACTA."""

from langchain.agents import create_agent

from agents.helpers.llms import llm_fast_agents
from agents.prompts.prompt_indicadores import INDICADORES_PROMPT_COMPLETO
from tools.indicador_tools import TOOLS as INDICADORES_TOOLS

indicadores_agent = create_agent(
    model=llm_fast_agents,
    tools=INDICADORES_TOOLS,
    system_prompt=INDICADORES_PROMPT_COMPLETO,
)
