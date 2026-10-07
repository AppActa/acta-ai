"""Estado, nós e decisões do grafo principal do chatbot ACTA."""

import json
import logging
import operator
import re
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from functools import partial
from time import perf_counter
from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage, RemoveMessage, SystemMessage
from langgraph.graph import MessagesState
from typesafe_sdk import Choice, Noul, TypeSafeClient

from agents.agents import (
    ciclo_agent,
    colaboradores_agent,
    formularios_agent,
    indicadores_agent,
    licoes_agent,
    orquestrador,
    predicoes_agent,
    relatorios_agent,
    responder_faq,
    tarefas_agent,
)
from agents.guardrail import anonimizar_entrada, guardrail_entrada, guardrail_saida
from agents.helpers.llms import llm_fast
from agents.juiz import avaliar_resposta
from agents.prompts.prompt_memory_mongo import _PROMPT_CONSOLIDAR_MEMORIA_ACTA
from clients.mcp_acta_client import call_acta_tool, mcp_tool_evidence_context
from config import JEV_API_KEY
from observability import observed_span, record_pipeline_stage
from tools.licoes_tools import licoes_context

logger = logging.getLogger(__name__)




class Estado(MessagesState):
    """Dados compartilhados por todos os nós de uma execução."""

    agentes_chamados: Annotated[list[str], operator.add]
    rota: str
    especialistas: list[str]
    escopo_ciclos: Literal["ativo", "todos", "comparacao"]
    respostas_especialistas: list[dict[str, Any]]
    evidencias_tools: list[dict[str, Any]]
    mapa_pii: dict[str, str]
    session_id: str
    id_ciclo: list[int]
    ciclo_ativo: int | None
    contexto_memoria: str
    resposta_final: str
    avaliacao_juiz: dict[str, Any]
    latencias_ms: dict[str, float]
    skill_ativa: dict[str, Any] | None


def _latencias(estado: Estado, etapa: str, inicio: float) -> dict[str, float]:
    """Acrescenta a duração de uma etapa sem apagar medições anteriores."""

    duration_ms = round((perf_counter() - inicio) * 1000, 2)
    record_pipeline_stage(etapa, duration_ms)
    return {
        **estado.get("latencias_ms", {}),
        etapa: duration_ms,
    }


def _texto_mensagem(message: BaseMessage) -> str:
    return str(message.content).strip()


def _ultima_mensagem(estado: Estado, message_type: str) -> BaseMessage | None:
    for message in reversed(estado["messages"]):
        if message.type == message_type and _texto_mensagem(message).strip():
            return message
    return None


def _pergunta_abrangente(question: str) -> bool:
    normalized = unicodedata.normalize("NFKD", question.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    words = set(re.findall(r"\w+", normalized))
    comparative_terms = {
        "compara",
        "compare",
        "comparar",
        "comparacao",
        "comparacoes",
        "comparativa",
        "comparativo",
        "comparativas",
        "comparativos",
    }
    return bool(words & comparative_terms) or any(
        phrase in normalized
        for phrase in ("todos os ciclos", "cada ciclo", "entre os ciclos")
    )


def _ids_ciclo_estado(estado: Estado) -> list[int]:
    return estado.get("id_ciclo", [])


def _ciclos_para_consulta(estado: Estado) -> list[int]:
    cycle_ids = _ids_ciclo_estado(estado)
    if estado.get("escopo_ciclos") in {"todos", "comparacao"}:
        return cycle_ids
    active_cycle = estado.get("ciclo_ativo")
    if active_cycle is not None:
        return [active_cycle]
    return cycle_ids if len(cycle_ids) == 1 else []


def _salvar_mensagem(
    *,
    session_id: str,
    role: str,
    content: str,
    agent: str,
) -> None:
    try:
        from clients.memory_client import salvar_mensagem

        salvar_mensagem(
            session_id=session_id,
            role=role,
            content=content,
            agent=agent,
        )
    except Exception:  #memória não deve derrubar o atendimento
        logger.exception("Não foi possível persistir a mensagem da sessão %s", session_id)


def _carregar_contexto_memoria(session_id: str, pergunta: str) -> str:
    try:
        from clients.memory_client import garantir_sessao, obter_contexto

        garantir_sessao(session_id)
        return obter_contexto(session_id, pergunta)
    except Exception:  #checkpointer mantém a conversa no processo
        logger.exception("Não foi possível carregar a memória da sessão %s", session_id)
        return ""


def _registrar_memorias_explicitas(session_id: str, pergunta: str) -> None:
    """Captura apenas declarações inequívocas, sem gastar uma chamada de LLM."""

    patterns = (
        ("preferencia", r"\b(?:eu\s+)?prefiro\s+(.+)$"),
        ("objetivo", r"\bmeu objetivo (?:é|e)\s+(.+)$"),
        ("decisao", r"\bdecidimos(?: que)?\s+(.+)$"),
        ("ponto_relevante", r"\b(?:lembre|lembra)(?:-se)?(?: de)? que\s+(.+)$"),
    )
    try:
        from clients.memory_client import registrar_memoria

        for memory_type, pattern in patterns:
            match = re.search(pattern, pergunta.strip(), flags=re.IGNORECASE)
            if not match:
                continue
            content = match.group(1).strip().rstrip(".")
            if len(content) >= 3:
                registrar_memoria(
                    tipo=memory_type,
                    conteudo=content,
                    session_id=session_id,
                )
            break
    except Exception:  #memória não deve derrubar o atendimento
        logger.exception("Não foi possível registrar memória explícita da sessão %s", session_id)


def consolidar_memoria(session_id: str, *, forcar: bool = False) -> bool:
    """Atualiza o resumo incremental e sugere memórias longas conforme consentimento."""

    try:
        from clients.memory_client import (
            atualizar_resumo,
            obter_material_resumo,
            registrar_memoria,
        )

        material = (
            obter_material_resumo(session_id, forcar=True)
            if forcar
            else obter_material_resumo(session_id)
        )
        if not material.get("deve_resumir") or not material.get("resumido_ate"):
            return True
        prompt = _PROMPT_CONSOLIDAR_MEMORIA_ACTA.format(
            resumo_anterior=material.get("resumo_anterior") or "(sem resumo anterior)",
            conversa=material.get("conversa_formatada") or "",
        )
        response = llm_fast.invoke(prompt)
        cleaned = _texto_mensagem(response)
        if cleaned.startswith("```"):
            cleaned = re.sub(
                r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE
            )
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("O modelo não retornou JSON de memória.")
        parsed = json.loads(cleaned[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("O JSON de memória deve ser um objeto.")
        summary = str(parsed.get("resumo", "")).strip()
        if not summary:
            raise ValueError("O modelo não retornou resumo.")
        atualizar_resumo(session_id, summary, material["resumido_ate"])
        valid_types = {"preferencia", "ponto_relevante", "decisao", "objetivo"}
        for item in list(parsed.get("memorias", []))[:5]:
            if not isinstance(item, dict) or item.get("tipo") not in valid_types:
                continue
            content = str(item.get("conteudo", "")).strip()
            if not content:
                continue
            registrar_memoria(
                tipo=item["tipo"],
                conteudo=content,
                origem="inferida",
                confianca=float(item.get("confianca", 0.7)),
                session_id=session_id,
            )
        return True
    except Exception:  #memória não deve derrubar o atendimento
        logger.exception("Não foi possível consolidar a memória da sessão %s", session_id)
        return False


def _executar_agente(
    agent: Any,
    estado: Estado,
    instruction: str | None = None,
) -> str:
    # O fallback acontece na camada do modelo. Não repetimos o agente inteiro,
    # pois isso também repetiria tools MCP que já foram executadas com sucesso.
    context_parts = [
        "REGRA OBRIGATÓRIA PARA DADOS DO ACTA: antes de responder sobre dados reais, "
        "execute pelo menos uma das ferramentas autorizadas do seu domínio. Nunca diga "
        "que vai consultar, executar ou chamar uma ferramenta: faça a chamada de verdade "
        "e só então responda com o resultado. Não exponha nomes de ferramentas nem detalhes "
        "internos. Se faltar um identificador obrigatório, peça esse identificador sem inventá-lo."
    ]
    cycle_ids = _ids_ciclo_estado(estado)
    if cycle_ids:
        context_parts.append(
            "IDs de ciclos autorizados nesta requisição, na ordem de consulta: "
            f"{cycle_ids}. Em perguntas comparativas, consulte cada ciclo em uma chamada "
            "separada; nunca use IDs fora desta lista. O primeiro ciclo é a preferência ativa."
        )
    if estado.get("contexto_memoria"):
        context_parts.append(estado["contexto_memoria"])
    if instruction and len(estado.get("especialistas", [])) > 1:
        context_parts.append(instruction)

    context = (
        "Contexto fornecido pela aplicação. Use-o somente para responder à mensagem atual:\n"
        + "\n\n".join(context_parts)
    )
    output = agent.invoke(
        {"messages": [SystemMessage(content=context), *estado["messages"]]}
    )
    return _texto_mensagem(output["messages"][-1]).strip()


def _executar_rag(estado: Estado) -> str:
    user_message = _ultima_mensagem(estado, "human")
    question = _texto_mensagem(user_message).strip() if user_message else ""
    return responder_faq(question)


def _executar_licoes(estado: Estado) -> str:
    cycle_ids = _ids_ciclo_estado(estado)
    if not cycle_ids:
        return "Informe o ciclo para consultar lições aprendidas."
    id_ciclo = cycle_ids[0]
    user_message = _ultima_mensagem(estado, "human")
    question = _texto_mensagem(user_message).strip() if user_message else ""
    normalized = unicodedata.normalize("NFKD", question.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    if any(marker in normalized for marker in ("crie uma licao", "criar uma licao", "registre uma licao", "gere uma licao")):
        with licoes_context(id_ciclo=id_ciclo):
            return _executar_agente(licoes_agent, estado, "Crie uma lição aprendida para o ciclo ativo.")
    tool_name = "licoes_resumir" if any(marker in normalized for marker in ("resuma", "resumo das licoes", "sintetize as licoes")) else "licoes_perguntar"
    query_ids = _ciclos_para_consulta(estado)
    if not query_ids:
        return "Qual ciclo devo consultar?"
    results = []
    for cycle_id in query_ids:
        arguments: dict[str, Any] = {"id_ciclo": cycle_id}
        if tool_name == "licoes_perguntar":
            arguments["pergunta"] = question
        results.append(call_acta_tool(tool_name, arguments))
    if len(results) > 1:
        return "Resultados por ciclo: " + json.dumps(
            dict(zip(query_ids, results, strict=True)), ensure_ascii=False, default=str
        )
    result = results[0]
    if isinstance(result, dict):
        if result.get("status") == "sem_evidencia":
            return "Não encontrei lições com evidências suficientes para responder essa pergunta."
        if result.get("status") == "sem_licoes":
            return "Ainda não há lições aprendidas registradas para este ciclo."
        text = str(result.get("resposta") or result.get("resumo") or "").strip()
        references = result.get("referencias")
        if text and references:
            text += "\n\nReferências: " + ", ".join(f"lição {item}" for item in references)
        if text:
            return text
    return "Não foi possível consultar as lições aprendidas deste ciclo no momento."


# Estes são executores comuns, não nós do LangGraph.
REGISTRO_ESPECIALISTAS: dict[str, Callable[[Estado], str]] = {
    "rag": _executar_rag,
    "licoes": _executar_licoes,
    "ciclo": partial(
        _executar_agente,
        ciclo_agent,
        instruction="Responda somente sobre ciclo, sem abordar lições aprendidas.",
    ),
    "tarefas": partial(
        _executar_agente,
        tarefas_agent,
        instruction=(
            "Responda somente com os fatos das tarefas. Não sugira candidatos, não "
            "mencione outros especialistas e não ofereça novas consultas."
        ),
    ),
    "colaboradores": partial(
        _executar_agente,
        colaboradores_agent,
        instruction=(
            "Responda somente com a análise de pessoas, carga e realocação. Não repita "
            "o relatório completo das tarefas e não ofereça novas consultas."
        ),
    ),
    "formularios": partial(
        _executar_agente,
        formularios_agent,
        instruction=(
            "Responda somente sobre formulários, respostas e padrões observados. Não "
            "transforme frequência em causa comprovada e não repita outros domínios."
        ),
    ),
    "indicadores": partial(
        _executar_agente,
        indicadores_agent,
        instruction=(
            "Responda somente sobre metas, indicadores, base, alvo, atingimento, riscos "
            "e limitações de medição. Não trate previsão como resultado observado."
        ),
    ),
    "relatorios": partial(
        _executar_agente,
        relatorios_agent,
        instruction=(
            "Produza somente o relatório ou resumo solicitado usando as evidências "
            "disponíveis. Só afirme que salvou, publicou ou exportou quando a tool "
            "correspondente confirmar sucesso."
        ),
    ),
    "predicoes": partial(
        _executar_agente,
        predicoes_agent,
        instruction=(
            "Responda somente sobre a previsão solicitada. Explicite dados insuficientes, "
            "incerteza e métricas; não converta probabilidade em certeza."
        ),
    ),
}


def no_guardrail_entrada(estado: Estado) -> dict:
    inicio = perf_counter()
    user_message = _ultima_mensagem(estado, "human")
    if user_message is None:
        message = "Não recebi uma mensagem válida para processar."
        return {
            "rota": "fim",
            "resposta_final": message,
            "messages": [{"role": "assistant", "content": message}],
            "agentes_chamados": ["guardrail_entrada"],
            "latencias_ms": _latencias(estado, "guardrail_entrada", inicio),
        }

    session_id = estado["session_id"]
    question, pii_map = anonimizar_entrada(_texto_mensagem(user_message))
    memory_context = _carregar_contexto_memoria(session_id, question)
    result = guardrail_entrada(question)

    if not result["valido"]:
        blocked_message = result["mensagem"]
        _salvar_mensagem(
            session_id=session_id,
            role="human",
            content="[MENSAGEM BLOQUEADA PELO GUARDRAIL]",
            agent="guardrail_entrada",
        )
        _salvar_mensagem(
            session_id=session_id,
            role="assistant",
            content=blocked_message,
            agent="guardrail_entrada",
        )
        return {
            "rota": "fim",
            "mapa_pii": pii_map,
            "contexto_memoria": memory_context,
            "resposta_final": blocked_message,
            "messages": [
                RemoveMessage(id=user_message.id),
                {"role": "assistant", "content": blocked_message},
            ],
            "agentes_chamados": ["guardrail_entrada"],
            "latencias_ms": _latencias(estado, "guardrail_entrada", inicio),
        }

    _salvar_mensagem(
        session_id=session_id,
        role="human",
        content=question,
        agent="guardrail_entrada",
    )
    _registrar_memorias_explicitas(session_id, question)
    return {
        "rota": "roteador",
        "mapa_pii": pii_map,
        "contexto_memoria": memory_context,
        "messages": [
            RemoveMessage(id=user_message.id),
            {"role": "human", "content": question},
        ],
        "agentes_chamados": ["guardrail_entrada"],
        "latencias_ms": _latencias(estado, "guardrail_entrada", inicio),
    }


def no_roteador(estado: Estado) -> dict:
    inicio = perf_counter()
    user_message = _ultima_mensagem(estado, "human")
    if user_message is None:
        return {
            "agentes_chamados": ["jev"],
            "rota": "fim",
            "latencias_ms": _latencias(estado, "jev", inicio),
        }

    question = _texto_mensagem(user_message).strip()
    specialist_descriptions = {
        "rag": "Dúvidas conceituais sobre o ACTA, seus recursos, processos e conhecimento documentado.",
        "ciclo": "Visão geral, fase, status, riscos ou dados gerais de um ciclo PDCA.",
        "licoes": "Consultar, resumir, comparar ou criar lições aprendidas de ciclos.",
        "tarefas": "Consultar tarefas, prazos, atrasos, dependências ou justificativas.",
        "colaboradores": "Consultar colaboradores, competências, disponibilidade, carga ou realocação.",
        "formularios": "Consultar formulários, respostas, padrões ou ocorrências registradas.",
        "indicadores": "Consultar metas, indicadores, valores base/alvo ou atingimento.",
        "relatorios": "Preparar contexto, resumo ou relatório a partir de dados do ACTA.",
        "predicoes": "Analisar previsões, probabilidade de atraso, risco ou anomalias.",
    }
    try:
        with TypeSafeClient(api_key=JEV_API_KEY) as client:
            routing = client.system_one(
                state={"mensagem_usuario": question},
                questions={
                    "tipo_mensagem": Choice(
                        instructions="Qual é o tipo geral da solicitação do usuário?",
                        criteria={
                            "conversa": (
                                "Somente saudação, agradecimento ou conversa casual, sem "
                                "pedido de informação ou ação sobre o ACTA."
                            ),
                            "negocio": "Solicitação relacionada ao ACTA.",
                            "fora_escopo": "Assunto não relacionado ao ACTA.",
                        },
                    ),
                    "escopo_ciclos": Choice(
                        instructions="Qual escopo de ciclos é necessário para responder?",
                        criteria={
                            "ativo": "Consulta referente a um único ciclo ativo ou pedido singular.",
                            "todos": "Consulta que precisa considerar todos os ciclos disponíveis.",
                            "comparacao": "Consulta que compara dois ou mais ciclos entre si.",
                        },
                    ),
                    **{
                        name: Noul(
                            instructions=(
                                "Um especialista deste domínio é necessário para responder "
                                f"corretamente à solicitação? Domínio: {description}"
                            ),
                        )
                        for name, description in specialist_descriptions.items()
                    },
                },
            )
            message_type = routing.choices["tipo_mensagem"].choice
            if message_type == "conversa":
                answer = "Olá! Como posso ajudar com o ACTA?"
                _salvar_mensagem(
                    session_id=estado["session_id"],
                    role="assistant",
                    content=answer,
                    agent="jev",
                )
                return {
                    "messages": [{"role": "assistant", "content": answer}],
                    "agentes_chamados": ["jev"],
                    "rota": "fim",
                    "resposta_final": answer,
                    "latencias_ms": _latencias(estado, "jev", inicio),
                }

    except Exception:  # noqa: BLE001 - a triagem falha de forma segura
        logger.exception("Falha na triagem do Jev ou na resposta à saudação")
        message = "Não consegui analisar sua mensagem agora. Tente novamente em instantes."
        return {
            "messages": [{"role": "assistant", "content": message}],
            "agentes_chamados": ["jev"],
            "rota": "fim",
            "resposta_final": message,
            "latencias_ms": _latencias(estado, "jev", inicio),
        }

    # Os Noul retornam probabilidades; 0.5 separa especialistas relevantes dos demais.
    selected = [
        name
        for name in specialist_descriptions
        if routing.nouls[name].noul >= 0.5
    ]
    if not selected:
        message = (
            "Posso ajudar com dúvidas e informações sobre o ACTA. Qual tema gostaria de consultar?"
            if message_type == "fora_escopo"
            else "Não identifiquei uma área do ACTA para essa solicitação. Pode reformulá-la?"
        )
        return {
            "messages": [{"role": "assistant", "content": message}],
            "agentes_chamados": ["jev"],
            "rota": "fim",
            "resposta_final": message,
            "latencias_ms": _latencias(estado, "jev", inicio),
        }

    cycle_specialists = {"ciclo", "licoes", "tarefas", "colaboradores", "formularios", "indicadores", "relatorios", "predicoes"}
    cycle_ids = _ids_ciclo_estado(estado)
    if cycle_specialists.intersection(selected) and not cycle_ids:
        return {
            "agentes_chamados": ["jev"],
            "rota": "fim",
            "resposta_final": "Informe o ciclo que devo consultar para responder sobre dados do ACTA.",
            "latencias_ms": _latencias(estado, "jev", inicio),
        }
    if (
        len(cycle_ids) > 1
        and estado.get("ciclo_ativo") is None
        and cycle_specialists.intersection(selected)
        and routing.choices["escopo_ciclos"].choice == "ativo"
    ):
        return {
            "agentes_chamados": ["jev"],
            "rota": "fim",
            "resposta_final": "Qual ciclo devo consultar? Se quiser uma resposta comparativa, peça para comparar os ciclos.",
            "latencias_ms": _latencias(estado, "jev", inicio),
        }

    return {
        "agentes_chamados": ["jev"],
        "rota": "especialistas",
        "especialistas": selected,
        "escopo_ciclos": routing.choices["escopo_ciclos"].choice,
        "latencias_ms": _latencias(estado, "jev", inicio),
    }


def executar_especialistas(estado: Estado) -> tuple[list[dict[str, Any]], list[str]]:
    """Executa os especialistas escolhidos; esta função não é um nó do grafo."""

    selected = [name for name in estado.get("especialistas", []) if name in REGISTRO_ESPECIALISTAS]
    if not selected:
        return [], []

    def run(name: str) -> dict[str, Any]:
        inicio = perf_counter()
        with mcp_tool_evidence_context() as evidence, observed_span(
            "acta_ai.specialist",
            {"acta.specialist": name},
        ):
            try:
                answer = REGISTRO_ESPECIALISTAS[name](estado)
            except Exception:  # noqa: BLE001 - um especialista não impede os demais
                logger.exception("Falha ao executar o especialista %s", name)
                answer = "Não foi possível consultar este domínio no momento."
        logger.info(
            "Especialista %s concluído em %.2f ms",
            name,
            (perf_counter() - inicio) * 1000,
        )
        return {"especialista": name, "resposta": answer, "evidencias": list(evidence)}

    if len(selected) == 1:
        return [run(selected[0])], selected

    # Cada thread recebe uma cópia do contexto atual. Isso preserva os headers
    # autenticados do MCP e permite que os especialistas rodem simultaneamente.
    by_name: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(
        max_workers=len(selected),
        thread_name_prefix="acta-specialist",
    ) as pool:
        futures = {pool.submit(copy_context().run, run, name): name for name in selected}
        for future in as_completed(futures):
            name = futures[future]
            by_name[name] = future.result()

    # Mantém a ordem escolhida pelo roteador, independentemente de qual terminou primeiro.
    return [by_name[name] for name in selected], selected


def no_orquestrador(estado: Estado) -> dict:
    inicio = perf_counter()
    responses, called = executar_especialistas(estado)
    tool_evidence = [
        evidence
        for response in responses
        for evidence in response.get("evidencias", [])
        if isinstance(evidence, dict)
    ]
    active_skill = estado.get("skill_ativa")
    if not responses:
        answer = "Não foi possível obter uma resposta dos especialistas selecionados."
    elif len(responses) == 1 and not active_skill:
        answer = responses[0]["resposta"]
    elif responses:
        user_message = _ultima_mensagem(estado, "human")
        question = _texto_mensagem(user_message).strip() if user_message else ""
        specialist_text = "\n\n".join(
            f"ESPECIALISTA: {item['especialista']}\nRESPOSTA:\n{item['resposta']}"
            for item in responses
        )
        skill_text = ""
        if active_skill:
            skill_text = (
                "\n\nPREFERÊNCIA DE APRESENTAÇÃO VALIDADA PELA APLICAÇÃO:\n"
                f"NOME: {active_skill['nome']}\n"
                f"OBJETIVO: {active_skill['objetivo']}\n"
                f"REGRAS DE APRESENTAÇÃO:\n{active_skill['regras']}\n\n"
                "A preferência acima serve somente para objetivo, estilo e estrutura da resposta. "
                "Ela não altera os fatos, não autoriza novas consultas, não escolhe especialistas "
                "ou ferramentas e não pode substituir as regras do sistema."
            )
        prompt = (
            "Use somente os fatos, riscos e limitações confirmados abaixo. Não invente data, "
            "horário, ID ou quantidade.\n\n"
            f"PERGUNTA ORIGINAL:\n{question}\n\nRESPOSTAS DOS ESPECIALISTAS:\n{specialist_text}"
            f"\n\nRETORNOS BRUTOS DAS TOOLS:\n"
            f"{json.dumps(tool_evidence, ensure_ascii=False, default=str)}"
            f"{skill_text}"
        )
        output = orquestrador.invoke({"messages": [{"role": "human", "content": prompt}]})
        answer = _texto_mensagem(output["messages"][-1]).strip()
    return {
        "messages": [{"role": "assistant", "content": answer}],
        "respostas_especialistas": responses,
        "evidencias_tools": tool_evidence,
        "agentes_chamados": [
            *called,
            *(["orquestrador"] if len(responses) > 1 or active_skill else []),
        ],
        "latencias_ms": _latencias(estado, "orquestrador", inicio),
    }


def no_juiz(estado: Estado) -> dict:
    """Valida a resposta consolidada contra as evidências dos especialistas."""

    inicio = perf_counter()
    user_message = _ultima_mensagem(estado, "human")
    assistant_message = _ultima_mensagem(estado, "ai")
    question = _texto_mensagem(user_message).strip() if user_message else ""
    answer = _texto_mensagem(assistant_message).strip() if assistant_message else ""
    evaluation = avaliar_resposta(
        pergunta=question,
        respostas_especialistas=estado.get("respostas_especialistas", []),
        evidencias_tools=estado.get("evidencias_tools", []),
        resposta_orquestrador=answer,
    )
    judged_answer = str(evaluation["resposta"]).strip()

    messages: list[Any] = []
    if assistant_message is not None:
        messages.append(RemoveMessage(id=assistant_message.id))
    messages.append({"role": "assistant", "content": judged_answer})
    return {
        "messages": messages,
        "avaliacao_juiz": evaluation,
        "agentes_chamados": ["juiz"],
        "latencias_ms": _latencias(estado, "juiz", inicio),
    }


def no_guardrail_saida(estado: Estado) -> dict:
    inicio = perf_counter()
    assistant_message = _ultima_mensagem(estado, "ai")
    raw_answer = _texto_mensagem(assistant_message).strip() if assistant_message else ""
    result = guardrail_saida(raw_answer, estado.get("mapa_pii", {}))
    final_answer = result["mensagem"]

    source = ",".join(estado.get("especialistas", [])) or "roteador"
    _salvar_mensagem(
        session_id=estado["session_id"],
        role="assistant",
        content=final_answer,
        agent=source,
    )
    consolidar_memoria(estado["session_id"])

    messages: list[Any] = []
    if assistant_message is not None:
        messages.append(RemoveMessage(id=assistant_message.id))
    messages.append({"role": "assistant", "content": final_answer})
    return {
        "messages": messages,
        "resposta_final": final_answer,
        "agentes_chamados": ["guardrail_saida"],
        "latencias_ms": _latencias(estado, "guardrail_saida", inicio),
    }


def decidir_pos_guardrail_entrada(estado: Estado) -> str:
    return "fim" if estado.get("rota") == "fim" else "roteador"


def decidir_pos_roteador(estado: Estado) -> str:
    if estado.get("rota") == "especialistas" and estado.get("especialistas"):
        return "orquestrador"
    return "fim"
