"""
agents/agents_ciclo.py

Agente de Ciclo do Chatbot ACTA.

Responsabilidade:
- Responder perguntas sobre ciclos PDCA reais.
- Usar tools para consultar dados do ciclo.
- Consultar informações autorizadas do ciclo.
- Consultar a análise de Ishikawa quando necessário.
- Retornar a resposta final para o fluxo LangGraph.
"""

from langchain.agents import create_agent

from agents.helpers.llms import llm_agents
from agents.prompts.prompt_ciclo import CICLO_PROMPT_COMPLETO
from tools.ciclo_tools import TOOLS as CICLO_TOOLS

ciclo_agent = create_agent(
    model=llm_agents,
    tools=CICLO_TOOLS,
    system_prompt=CICLO_PROMPT_COMPLETO,
)
