"""Validação de transações no ponto comum anterior ao envio ao MCP."""

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from langchain.agents.middleware import after_model

from agents.intencao import (
    APOIO_MINIMO,
    MAX_ACOES_ESPECIALISTA,
    MENSAGEM_BLOQUEIO,
    AvaliacaoIntencao,
    EsclarecimentoNecessario,
    ExecucaoBloqueada,
    Intention,
)
from agents.juiz import avaliar_intencao
from config import ACTA_INTENTION_MAX_RETRIES

logger = logging.getLogger(__name__)

# Lista fechada: operações novas/desconhecidas não são tratadas como leitura.
TOOLS_LEITURA = frozenset({
    "faq_retriever", "ciclos_buscar_por_descricao", "ciclo_visao_geral",
    "ciclo_problema_principal", "ciclo_causas_raiz", "ciclo_ishikawa",
    "ciclo_riscos_pendencias", "ciclo_treinamentos", "ciclo_participantes",
    "ciclo_relatorio_completo", "tarefas_consultar", "tarefas_atrasadas",
    "tarefas_concluidas", "tarefas_detalhes", "tarefas_por_responsavel",
    "tarefas_alertas_prazo", "tarefas_relatorio_completo", "colaboradores_consultar",
    "colaborador_detalhes", "colaboradores_participantes_ciclo", "colaboradores_por_area",
    "colaboradores_carga_trabalho", "colaboradores_sugestao_realocacao",
    "colaboradores_relatorio_completo", "formularios_listar", "formularios_detalhes",
    "formularios_respostas", "formularios_resumo_respostas", "relatorios_contexto_ciclo",
    "licoes_resumir", "licoes_perguntar",
})


@dataclass
class ContextoTransacoes:
    pergunta: str
    contexto: dict[str, Any]
    registros: list[dict[str, Any]] = field(default_factory=list)
    correcoes: int = 0
    aprovadas: int = 0


_contexto: ContextVar[ContextoTransacoes | None] = ContextVar("acta_transacoes", default=None)
_revisao_resposta: ContextVar[bool] = ContextVar("acta_revisao_resposta", default=False)


@contextmanager
def revisao_resposta_context():
    """Uma revisão pode consultar dados, mas nunca repetir ou iniciar escritas."""
    token = _revisao_resposta.set(True)
    try:
        yield
    finally:
        _revisao_resposta.reset(token)


@after_model
def bloquear_lote_de_escrita(state, runtime):
    """Uma proposta de escrita por vez, antes de o agente despachar suas tools."""
    calls = getattr(state["messages"][-1], "tool_calls", [])
    read_names = TOOLS_LEITURA | {"resumir_licoes_aprendidas", "consultar_licoes_aprendidas"}
    if len(calls) > 1 and any(call["name"] not in read_names for call in calls):
        raise ExecucaoBloqueada(MENSAGEM_BLOQUEIO)


@contextmanager
def transacoes_context(pergunta: str, contexto: dict[str, Any]):
    """Limites e registros isolados por especialista e rodada."""
    state = ContextoTransacoes(pergunta, contexto)
    token = _contexto.set(state)
    try:
        yield state.registros
    finally:
        _contexto.reset(token)


def _schema_transacao(tool_name: str):
    # Importação tardia evita o ciclo tools -> cliente MCP -> validação -> tools.
    from tools.ciclo_tools import TOOLS as ciclo
    from tools.formulario_tools import TOOLS as formulario
    from tools.licoes_tools import criar_licao_aprendida
    from tools.tarefas_tools import TOOLS as tarefas

    tools = [*ciclo, *formulario, *tarefas, criar_licao_aprendida]
    selected = next((tool for tool in tools if tool.name == tool_name), None)

    if selected is None or tool_name in TOOLS_LEITURA:
        raise ExecucaoBloqueada(MENSAGEM_BLOQUEIO)

    return selected.args_schema


def avaliar_transacao(tool_name: str, arguments: dict) -> tuple[Intention, AvaliacaoIntencao]:
    """Não executa; devolve somente uma intenção normalizada e sua decisão válida."""
    if _revisao_resposta.get():
        raise ExecucaoBloqueada("A revisão da resposta não pode executar alterações nos dados.")

    state = _contexto.get()

    if state is None or state.aprovadas >= MAX_ACOES_ESPECIALISTA:
        raise ExecucaoBloqueada(MENSAGEM_BLOQUEIO)

    if tool_name not in state.contexto.get("tools_autorizadas", []):
        raise ExecucaoBloqueada(MENSAGEM_BLOQUEIO)

    try:
        schema = _schema_transacao(tool_name)
        parsed = schema.model_validate_json(
            json.dumps(arguments, default=str), strict=True, extra="forbid"
        )
        intention = Intention(tool=tool_name, argumentos=parsed.model_dump(mode="json", exclude_none=True))
        context = {**state.contexto, "schema_ferramenta": schema.model_json_schema()}
        evaluation = avaliar_intencao(pergunta=state.pergunta, intencao=intention, contexto=context)
        evaluation = AvaliacaoIntencao.model_validate(
            evaluation.model_dump() if isinstance(evaluation, AvaliacaoIntencao) else evaluation
        )
    except ExecucaoBloqueada:
        raise
    except Exception as exc:
        logger.exception("Transação bloqueada: intenção ou julgamento inválido em %s", tool_name)
        raise ExecucaoBloqueada(MENSAGEM_BLOQUEIO) from exc

    state.registros.append({"intencao": intention.model_dump(), "avaliacao": evaluation.model_dump()})
    logger.info("Intenção %s: decisao=%s apoio=%.2f correcoes=%s", tool_name, evaluation.decisao, evaluation.apoio, state.correcoes)

    if evaluation.decisao == "pedir_esclarecimento":
        raise EsclarecimentoNecessario(evaluation.pergunta)

    if evaluation.decisao == "corrigir_proposta":
        if state.correcoes >= ACTA_INTENTION_MAX_RETRIES:
            raise ExecucaoBloqueada(MENSAGEM_BLOQUEIO)
        state.correcoes += 1

        return intention, evaluation

    if evaluation.apoio < APOIO_MINIMO:
        raise ExecucaoBloqueada(MENSAGEM_BLOQUEIO)

    state.correcoes = 0
    state.aprovadas += 1

    return intention, evaluation
