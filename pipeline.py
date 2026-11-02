"""Construção e ponto de entrada da pipeline LangGraph do chatbot ACTA."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Overwrite

from agents.estado import (
    NOS_ESPECIALISTAS,
    Estado,
    decidir_pos_guardrail_entrada,
    decidir_pos_guardrail_saida,
    decidir_pos_roteador,
    no_guardrail_entrada,
    no_guardrail_saida,
    no_juiz,
    no_orquestrador,
    no_resposta_geral,
    no_roteador,
)
from agents.guardrail import anonimizar_entrada, guardrail_entrada
from agents.skill_builder import gerar_markdown_skill
from clients.mcp_acta_client import mcp_identity_scope, mcp_tool_cache_context
from clients.skill_client import (
    SkillClientError,
    criar_skill,
    eh_pedido_criacao_skill,
    resolver_comando_skill,
)


def _texto_resposta(conteudo: object) -> str:
    """Retorna somente texto legível quando o modelo entrega blocos multimodais."""
    if isinstance(conteudo, str):
        return conteudo.strip()
    if isinstance(conteudo, list):
        partes = []
        for bloco in conteudo:
            if isinstance(bloco, str):
                partes.append(bloco)
            elif isinstance(bloco, dict) and bloco.get("type") == "text":
                texto = bloco.get("text")
                if isinstance(texto, str) and texto.strip():
                    partes.append(texto.strip())
        if partes:
            return "\n".join(partes)
    return str(conteudo).strip()


def _normalizar_ids_ciclo(id_ciclo: int | list[int] | None) -> list[int]:
    if id_ciclo is None:
        return []
    ids_ciclo = [id_ciclo] if isinstance(id_ciclo, int) else id_ciclo
    if any(not isinstance(ciclo_id, int) or ciclo_id <= 0 for ciclo_id in ids_ciclo):
        raise ValueError("id_ciclo deve conter somente inteiros positivos.")
    return list(dict.fromkeys(ids_ciclo))


def _criar_skill_pelo_chatbot(pedido: str) -> str:
    """Gera o contrato mínimo e só persiste depois da validação final no MCP."""

    pedido_anonimizado, mapa_pii = anonimizar_entrada(pedido)
    if mapa_pii:
        raise SkillClientError("Não inclua dados pessoais na definição de uma skill.")
    resultado_guardrail = guardrail_entrada(pedido_anonimizado)
    if not resultado_guardrail["valido"]:
        return resultado_guardrail["mensagem"]

    markdown = gerar_markdown_skill(pedido_anonimizado)
    skill = criar_skill(markdown)
    return (
        f"Skill criada: {skill['comando']}\n\n"
        f"Use assim: `{skill['comando']} sua pergunta`"
    )


def construir_fluxo():
    """Monta e compila o grafo principal com memória por sessão."""

    grafo = StateGraph(Estado)

    grafo.add_node("guardrail_entrada", no_guardrail_entrada)
    grafo.add_node("roteador", no_roteador)
    for nome, no in NOS_ESPECIALISTAS.items():
        grafo.add_node(nome, no)
    grafo.add_node("orquestrador", no_orquestrador)
    grafo.add_node("resposta_geral", no_resposta_geral)
    grafo.add_node("juiz", no_juiz)
    grafo.add_node("guardrail_saida", no_guardrail_saida)

    grafo.set_entry_point("guardrail_entrada")
    grafo.add_conditional_edges(
        "guardrail_entrada",
        decidir_pos_guardrail_entrada,
        {"roteador": "roteador", "fim": END},
    )
    grafo.add_conditional_edges(
        "roteador",
        decidir_pos_roteador,
        {
            **{nome: nome for nome in NOS_ESPECIALISTAS},
            "resposta_geral": "resposta_geral",
            "fim": END,
        },
    )
    for nome in NOS_ESPECIALISTAS:
        grafo.add_edge(nome, "orquestrador")

    grafo.add_edge("resposta_geral", "guardrail_saida")
    grafo.add_edge("orquestrador", "guardrail_saida")
    grafo.add_conditional_edges(
        "guardrail_saida",
        decidir_pos_guardrail_saida,
        {"juiz": "juiz", "fim": END},
    )
    grafo.add_edge("juiz", END)

    return grafo.compile(checkpointer=MemorySaver())


fluxo_agentes = construir_fluxo()


def executar_fluxo_acta(
    pergunta_usuario: str,
    session_id: str,
    id_ciclo: int | list[int] | None = None,
    ciclo_ativo: int | None = None,
    nome_usuario: str | None = None,
) -> str:
    return _executar_fluxo_acta_com_status(
        pergunta_usuario, session_id, id_ciclo, ciclo_ativo, nome_usuario
    )[0]


def _executar_fluxo_acta_com_status(
    pergunta_usuario: str,
    session_id: str,
    id_ciclo: int | list[int] | None = None,
    ciclo_ativo: int | None = None,
    nome_usuario: str | None = None,
) -> tuple[str, bool]:
    """Executa uma rodada do chatbot preservando o histórico pelo ``session_id``."""

    pergunta_original = pergunta_usuario.strip()
    if eh_pedido_criacao_skill(pergunta_original):
        return _criar_skill_pelo_chatbot(pergunta_original), False

    pergunta, skill_ativa = resolver_comando_skill(pergunta_original)
    sessao = session_id.strip()
    if not pergunta:
        raise ValueError("pergunta_usuario é obrigatória.")
    if not sessao:
        raise ValueError("session_id é obrigatório.")
    ids_ciclo = _normalizar_ids_ciclo(id_ciclo)
    if ciclo_ativo is not None and ciclo_ativo not in ids_ciclo:
        raise ValueError("ciclo_ativo deve estar presente em id_ciclo.")
    if ciclo_ativo is not None:
        ids_ciclo.remove(ciclo_ativo)
        ids_ciclo.insert(0, ciclo_ativo)

    estado_inicial = {
        "messages": [{"role": "human", "content": pergunta}],
        "rota": "",
        "especialistas": [],
        "respostas_especialistas": Overwrite([]),
        "evidencias_tools": [],
        "mapa_pii": {},
        "session_id": sessao,
        "id_ciclo": ids_ciclo,
        "ciclo_ativo": ciclo_ativo,
        "contexto_memoria": "",
        "resposta_final": "",
        "skill_ativa": skill_ativa,
        "nome_usuario": nome_usuario,
    }
    with mcp_tool_cache_context():
        estado_final = fluxo_agentes.invoke(
            estado_inicial,
            config={
                "configurable": {
                    "thread_id": f"{mcp_identity_scope()}:{sessao}",
                }
            },
        )

    resposta = _texto_resposta(estado_final.get("resposta_final", ""))
    if resposta:
        return resposta, bool(estado_final.get("entrada_bloqueada"))

    mensagens = estado_final.get("messages", [])
    if mensagens:
        return _texto_resposta(mensagens[-1].content), bool(
            estado_final.get("entrada_bloqueada")
        )
    return "Não foi possível gerar uma resposta.", bool(estado_final.get("entrada_bloqueada"))


def get_response(
    message: str,
    session_id: str,
    id_ciclo: int | list[int] | None = None,
    ciclo_ativo: int | None = None,
    nome_usuario: str | None = None,
) -> str:
    """Mantém o contrato utilizado pela API FastAPI."""

    return executar_fluxo_acta(
        message,
        session_id,
        id_ciclo=id_ciclo,
        ciclo_ativo=ciclo_ativo,
        nome_usuario=nome_usuario,
    )


def get_response_with_status(
    message: str,
    session_id: str,
    id_ciclo: int | list[int] | None = None,
    ciclo_ativo: int | None = None,
    nome_usuario: str | None = None,
) -> tuple[str, bool]:
    """Retorna a resposta e informa se a entrada foi bloqueada."""
    return _executar_fluxo_acta_com_status(
        message, session_id, id_ciclo, ciclo_ativo, nome_usuario
    )
