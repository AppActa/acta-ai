import logging
from datetime import datetime
from typing import Any

from agents.helpers.memory.repository import MAX_CONTEXT_MESSAGES, MemoryRepository
from agents.helpers.memory.schemas import MessageInput, SessionInput
from clients.mcp_acta_client import MCPRequestContext as RequestContext

logger = logging.getLogger(__name__)


def _format_messages(messages: list[dict[str, Any]]) -> str:
    lines = []
    for message in messages:
        prefix = message.get("role", "desconhecido")
        if message.get("agent"):
            prefix += f" | agente={message['agent']}"
        lines.append(f"{prefix}: {message.get('content', '')}")
    return "\n".join(lines)


class MemoryService:
    def __init__(self, repository: MemoryRepository, *, recent_messages: int, summary_every_messages: int) -> None:
        self.repository = repository
        self.recent_messages = min(max(recent_messages, 1), MAX_CONTEXT_MESSAGES)
        self.summary_every_messages = summary_every_messages

    def ensure_indexes(self) -> None:
        self.repository.ensure_indexes()

    def garantir_sessao(self, context: RequestContext, *, session_id: str, metadata: dict[str, Any] | None = None) -> None:
        data = SessionInput(session_id=session_id, metadata=metadata or {})
        self.repository.ensure_session(context, data.session_id, data.metadata)

    def salvar_mensagem(self, context: RequestContext, **kwargs: Any) -> None:
        data = MessageInput(**kwargs)
        self.repository.add_message(
            context, session_id=data.session_id, role=data.role, content=data.content,
            agent=data.agent, metadata=data.metadata,
        )

    def obter_contexto(
        self, context: RequestContext, *, session_id: str, query: str = "", limit: int | None = None
    ) -> dict[str, Any]:
        data = SessionInput(session_id=session_id)
        message_limit = self.recent_messages if limit is None else min(max(limit, 1), MAX_CONTEXT_MESSAGES)
        session, messages = self.repository.session_context(context, data.session_id, message_limit)
        parts = []
        if session.get("resumo"):
            parts.append(f"Resumo anterior desta conversa:\n{session['resumo']}")
        if messages:
            parts.append("Últimas mensagens desta conversa:\n" + _format_messages(messages))
        try:
            memories = self.repository.search_relevant_memories(
                context, session_id=data.session_id, query=query
            )
        except Exception:  # noqa: BLE001 - falha na busca não deve impedir o atendimento
            logger.exception("Não foi possível buscar memórias de outras conversas.")
            memories = []
        if memories:
            memory_lines = []
            for memory in memories:
                title = memory.get("titulo") or "Conversa anterior"
                details = [f"{title}: {memory.get('role', 'desconhecido')}: {memory.get('content', '')}"]
                if memory.get("resumo"):
                    details.append(f"Resumo: {memory['resumo']}")
                memory_lines.append("\n".join(details))
            parts.append("Memórias relevantes de outras conversas:\n" + "\n\n".join(memory_lines))
        return {
            "contexto": "\n\n".join(parts), "resumo": session.get("resumo", ""),
            "preferencias": [], "memorias_relevantes": memories, "mensagens_recentes": messages,
        }

    def material_resumo(self, context: RequestContext, *, session_id: str, forcar: bool = False) -> dict[str, Any]:
        data = SessionInput(session_id=session_id)
        session, messages = self.repository.summary_material(context, data.session_id)
        last_created = messages[-1]["criada_em"] if messages else None
        return {
            "tem_mensagens": bool(messages),
            "deve_resumir": bool(messages) and (forcar or len(messages) >= self.summary_every_messages),
            "resumo_anterior": session.get("resumo", ""), "mensagens": messages,
            "conversa_formatada": _format_messages(messages), "resumido_ate": last_created,
        }

    def atualizar_resumo(self, context: RequestContext, *, session_id: str, resumo: str,
                         resumido_ate: datetime) -> None:
        data = SessionInput(session_id=session_id)
        if not resumo.strip():
            raise ValueError("resumo é obrigatório.")
        self.repository.update_summary(context, data.session_id, resumo, resumido_ate)

    def encerrar_sessao(self, context: RequestContext, *, session_id: str) -> bool:
        return self.repository.close_session_if_has_messages(context, SessionInput(session_id=session_id).session_id)

    def listar_chats(self, context: RequestContext, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.repository.list_chats(context, min(max(limit, 1), 100))

    def listar_mensagens(self, context: RequestContext, *, session_id: str, limit: int = 30) -> list[dict[str, Any]]:
        return self.repository.list_messages(context, session_id, min(max(limit, 1), 100))
