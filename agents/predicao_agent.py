"""Agente especialista em predições do ACTA."""

from langchain.agents import create_agent

from agents.helpers.llms import llm_agents
from agents.prompts.prompt_predicao import PREDICAO_PROMPT_COMPLETO
from tools.predicao_tools import TOOLS as PREDICAO_TOOLS

predicoes_agent = create_agent(
    model=llm_agents,
    tools=PREDICAO_TOOLS,
    system_prompt=PREDICAO_PROMPT_COMPLETO,
)
