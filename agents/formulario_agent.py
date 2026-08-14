"""Agente especialista em formulários e respostas do ACTA."""

from langchain.agents import create_agent

from agents.helpers.llms import llm_agents
from agents.prompts.prompt_formulario import FORMULARIO_PROMPT_COMPLETO
from tools.formulario_tools import TOOLS as FORMULARIO_TOOLS

formularios_agent = create_agent(
    model=llm_agents,
    tools=FORMULARIO_TOOLS,
    system_prompt=FORMULARIO_PROMPT_COMPLETO,
)
