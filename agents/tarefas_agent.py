"""
agents/agents_tarefas.py

Agente de Tarefas do Chatbot ACTA.

Responsabilidade:
- Responder perguntas sobre tarefas reais de ciclos PDCA.
- Usar tools para consultar tarefas atribuídas, atrasadas, concluídas, responsáveis e prazos.
- Consultar informações autorizadas sobre tarefas, responsáveis, prazos, status, planos de ação, dependências e alertas.
- Retornar a resposta final para o fluxo LangGraph.
"""

from langchain.agents import create_agent

from agents.helpers.llms import llm_agents
from agents.prompts.prompt_tarefas import TAREFAS_PROMPT_COMPLETO
from tools.tarefas_tools import TOOLS as TAREFAS_TOOLS

tarefas_agent = create_agent(
    model=llm_agents,
    tools=TAREFAS_TOOLS,
    system_prompt=TAREFAS_PROMPT_COMPLETO,
)
