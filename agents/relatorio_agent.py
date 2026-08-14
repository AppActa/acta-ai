"""Agente especialista em relatórios executivos do ACTA."""

from langchain.agents import create_agent

from agents.helpers.llms import llm_agents
from agents.prompts.prompt_relatorio import RELATORIO_PROMPT_COMPLETO
from tools.relatorio_tools import TOOLS as RELATORIO_TOOLS

relatorios_agent = create_agent(
    model=llm_agents,
    tools=RELATORIO_TOOLS,
    system_prompt=RELATORIO_PROMPT_COMPLETO,
)
