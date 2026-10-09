"""Fachada das operações de memória pertencentes ao ACTA AI."""

from datetime import datetime
from typing import Any

from agents.helpers.runtime import get_memory_service
from clients.mcp_acta_client import current_mcp_request_context

_ROLE_MAP = {
    "human": "usuario",
    "user": "usuario",
    "ai": "assistente",
    "assistant": "assistente",
}


def garantir_sessao(session_id: str, metadata: dict[str, Any] | None = None) -> None:
    get_memory_service().garantir_sessao(
        current_mcp_request_context(), session_id=session_id, metadata=metadata
    )


def salvar_mensagem(
    *, session_id: str, role: str, content: str, agent: str, metadata: dict[str, Any] | None = None
) -> None:
    get_memory_service().salvar_mensagem(
        current_mcp_request_context(),
        session_id=session_id,
        role=_ROLE_MAP.get(role.lower(), role.lower()),
        content=content,
        agent=agent,
        metadata=metadata or {},
    )


def obter_contexto_detalhado(session_id: str, pergunta: str = "") -> dict[str, Any]:
    return get_memory_service().obter_contexto(
        current_mcp_request_context(), session_id=session_id, pergunta=pergunta
    )


def obter_contexto(session_id: str, pergunta: str) -> str:
    result = obter_contexto_detalhado(session_id, pergunta)
    return str(result.get("contexto", ""))


def obter_material_resumo(session_id: str, *, forcar: bool = False) -> dict[str, Any]:
    return get_memory_service().material_resumo(
        current_mcp_request_context(), session_id=session_id, forcar=forcar
    )


def encerrar_sessao(session_id: str) -> bool:
    return get_memory_service().encerrar_sessao(
        current_mcp_request_context(), session_id=session_id
    )


def listar_chats(limit: int = 50) -> list[dict[str, Any]]:
    return get_memory_service().listar_chats(current_mcp_request_context(), limit=limit)


def atualizar_resumo(session_id: str, resumo: str, resumido_ate: str | datetime) -> None:
    marker = datetime.fromisoformat(resumido_ate) if isinstance(resumido_ate, str) else resumido_ate
    get_memory_service().atualizar_resumo(
        current_mcp_request_context(),
        session_id=session_id,
        resumo=resumo,
        resumido_ate=marker,
    )


def registrar_memoria(
    *,
    tipo: str,
    conteudo: str,
    session_id: str,
    origem: str = "explicita",
    confianca: float = 1.0,
) -> bool:
    return get_memory_service().registrar(
        current_mcp_request_context(),
        tipo=tipo,
        conteudo=conteudo,
        origem=origem,
        confianca=confianca,
        session_id_origem=session_id,
    )


def buscar_memorias(pergunta: str, limit: int = 6) -> list[dict[str, Any]]:
    return get_memory_service().buscar(
        current_mcp_request_context(), pergunta=pergunta, limit=limit
    )


def listar_memorias(tipo: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return get_memory_service().listar(current_mcp_request_context(), tipo=tipo, limit=limit)


def excluir_memoria(id_memoria: str) -> None:
    get_memory_service().excluir(current_mcp_request_context(), id_memoria=id_memoria)


def obter_consentimento() -> dict[str, Any]:
    return get_memory_service().obter_consentimento(current_mcp_request_context())


def configurar_consentimento(modo: str, retencao_dias: int | None = None) -> dict[str, Any]:
    return get_memory_service().configurar_consentimento(
        current_mcp_request_context(), modo=modo, retencao_dias=retencao_dias
    )
