"""
agents/colaborador_agent.py

Agente de Colaboradores do Chatbot ACTA.

Responsabilidade:
- Responder perguntas sobre colaboradores reais.
- Analisar colaboradores, usuários, setores/áreas, cargos e participação em ciclos.
- Analisar carga de trabalho e possíveis realocações por área/cargo.
- Usar tools para buscar dados antes de responder.
- Retornar a resposta final para o fluxo LangGraph.
"""

from langchain.agents import create_agent

from agents.helpers.llms import llm_agents
from agents.prompts.prompt_colaborador import COLABORADOR_PROMPT_COMPLETO
from tools.colaborador_tools import TOOLS as COLABORADOR_TOOLS

colaboradores_agent = create_agent(
    model=llm_agents,
    tools=COLABORADOR_TOOLS,
    system_prompt=COLABORADOR_PROMPT_COMPLETO,
)
