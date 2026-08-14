"""Agente que consolida respostas produzidas por múltiplos especialistas."""

from langchain.agents import create_agent

from agents.helpers.llms import llm_fast
from agents.prompts.prompt_orquestrador import ORQUESTRADOR_PROMPT_COMPLETO

orquestrador = create_agent(
    model=llm_fast,
    system_prompt=ORQUESTRADOR_PROMPT_COMPLETO,
)
