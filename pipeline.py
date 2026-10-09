"""Construção e ponto de entrada da pipeline LangGraph do chatbot ACTA."""

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.estado import (
    Estado,
    decidir_pos_guardrail_entrada,
    decidir_pos_roteador,
    no_guardrail_entrada,
    no_guardrail_saida,
    no_juiz,
    no_orquestrador,
    no_roteador,
)
from agents.estado import (
    _pergunta_abrangente as _pergunta_comparativa,
)
from agents.guardrail import anonimizar_entrada, guardrail_entrada
from agents.skill_builder import gerar_markdown_skill
from clients.mcp_acta_client import (
    mcp_cycle_scope_context,
    mcp_identity_scope,
    mcp_tool_cache_context,
)
from clients.skill_client import (
    SkillClientError,
    criar_skill,
    eh_pedido_criacao_skill,
    resolver_comando_skill,
)

logger = logging.getLogger(__name__)


def _normalizar_ids_ciclo(id_ciclo: int | list[int] | None) -> list[int]:
    if id_ciclo is None:
        return []
    raw_ids = [id_ciclo] if isinstance(id_ciclo, int) else id_ciclo
    if len(raw_ids) > 20:
        raise ValueError("id_ciclo aceita no máximo 20 ciclos.")
    if any(not isinstance(cycle_id, int) or cycle_id <= 0 for cycle_id in raw_ids):
        raise ValueError("id_ciclo deve conter somente inteiros positivos.")
    return list(dict.fromkeys(raw_ids))


def _criar_skill_pelo_chatbot(request: str) -> str:
    """Gera o contrato mínimo e só persiste depois da validação final no MCP."""

    anonymized, pii_map = anonimizar_entrada(request)
    if pii_map:
        raise SkillClientError("Não inclua dados pessoais na definição de uma skill.")
    guardrail_result = guardrail_entrada(anonymized)
    if not guardrail_result["valido"]:
        return guardrail_result["mensagem"]

    markdown = gerar_markdown_skill(anonymized)
    skill = criar_skill(markdown)
    return (
        f"Skill criada: {skill['comando']}\n\n"
        f"Use assim: `{skill['comando']} sua pergunta`"
    )


def construir_fluxo():
    """Monta e compila o grafo principal com memória por sessão."""

    graph = StateGraph(Estado)

    graph.add_node("guardrail_entrada", no_guardrail_entrada)
    graph.add_node("roteador", no_roteador)
    graph.add_node("orquestrador", no_orquestrador)
    graph.add_node("juiz", no_juiz)
    graph.add_node("guardrail_saida", no_guardrail_saida)

    graph.set_entry_point("guardrail_entrada")
    graph.add_conditional_edges(
        "guardrail_entrada",
        decidir_pos_guardrail_entrada,
        {"roteador": "roteador", "fim": END},
    )
    graph.add_conditional_edges(
        "roteador",
        decidir_pos_roteador,
        {
            "orquestrador": "orquestrador",
            "fim": END,
        },
    )
    graph.add_edge("orquestrador", "juiz")
    graph.add_edge("juiz", "guardrail_saida")
    graph.add_edge("guardrail_saida", END)

    return graph.compile(checkpointer=MemorySaver())


fluxo_agentes = construir_fluxo()


def executar_fluxo_acta(
    pergunta_usuario: str,
    session_id: str,
    id_ciclo: int | list[int] | None = None,
    ciclo_ativo: int | None = None,
) -> str:
    """Executa uma rodada do chatbot preservando o histórico pelo ``session_id``."""

    raw_question = pergunta_usuario.strip()
    if eh_pedido_criacao_skill(raw_question):
        return _criar_skill_pelo_chatbot(raw_question)

    question, active_skill = resolver_comando_skill(raw_question)
    session_key = session_id.strip()
    if not question:
        raise ValueError("pergunta_usuario é obrigatória.")
    if not session_key:
        raise ValueError("session_id é obrigatório.")
    cycle_ids = _normalizar_ids_ciclo(id_ciclo)
    if ciclo_ativo is not None and ciclo_ativo not in cycle_ids:
        raise ValueError("ciclo_ativo deve estar presente em id_ciclo.")
    if ciclo_ativo is not None:
        cycle_ids.remove(ciclo_ativo)
        cycle_ids.insert(0, ciclo_ativo)

    initial_state = {
        "messages": [{"role": "human", "content": question}],
        "rota": "",
        "especialistas": [],
        "respostas_especialistas": [],
        "evidencias_tools": [],
        "mapa_pii": {},
        "session_id": session_key,
        "id_ciclo": cycle_ids,
        "ciclo_ativo": ciclo_ativo,
        "contexto_memoria": "",
        "resposta_final": "",
        "skill_ativa": active_skill,
    }
    query_scope = cycle_ids
    if ciclo_ativo is not None and not _pergunta_comparativa(question):
        query_scope = [ciclo_ativo]
    with mcp_tool_cache_context(), mcp_cycle_scope_context(query_scope):
        final_state = fluxo_agentes.invoke(
            initial_state,
            config={
                "configurable": {
                    "thread_id": f"{mcp_identity_scope()}:{session_key}",
                }
            },
        )

    answer = final_state.get("resposta_final", "").strip()
    if answer:
        return answer

    messages = final_state.get("messages", [])
    if messages:
        content = messages[-1].content
        return content if isinstance(content, str) else str(content)
    return "Não foi possível gerar uma resposta."


def get_response(
    message: str,
    session_id: str,
    id_ciclo: int | list[int] | None = None,
    ciclo_ativo: int | None = None,
) -> str:
    """Mantém o contrato utilizado pela API FastAPI."""

    return executar_fluxo_acta(
        message,
        session_id,
        id_ciclo=id_ciclo,
        ciclo_ativo=ciclo_ativo,
    )
