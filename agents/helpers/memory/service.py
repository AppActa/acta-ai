from datetime import datetime
from typing import Any

from agents.helpers.errors import NotFoundError
from agents.helpers.memory.repository import MemoryRepository
from agents.helpers.memory.schemas import ConsentInput, MemoryInput, MessageInput, SessionInput
from clients.mcp_acta_client import MCPRequestContext as RequestContext


def _format_messages(messages: list[dict[str, Any]]) -> str:
    lines = []
    for message in messages:
        prefix = message.get("role", "desconhecido")
        if message.get("agent"):
            prefix += f" | agente={message['agent']}"
        lines.append(f"{prefix}: {message.get('content', '')}")
    return "\n".join(lines)


class MemoryService:
    def __init__(
        self,
        repository: MemoryRepository,
        *,
        recent_messages: int,
        summary_every_messages: int,
    ) -> None:
        self.repository = repository
        self.recent_messages = recent_messages
        self.summary_every_messages = summary_every_messages

    def ensure_indexes(self) -> None:
        self.repository.ensure_indexes()

    def _search_memories(
        self, context: RequestContext, question: str, limit: int
    ) -> list[dict[str, Any]]:
        if self.repository.qdrant is None:
            return self.repository.list_memories(context, tipo=None, limit=limit)
        try:
            return self.repository.semantic_search(context, question, limit)
        except Exception:
            return self.repository.list_memories(context, tipo=None, limit=limit)

    def garantir_sessao(
        self, context: RequestContext, *, session_id: str, metadata: dict[str, Any] | None = None
    ) -> None:
        data = SessionInput(session_id=session_id, metadata=metadata or {})
        if self.repository.get_consent(context)["modo"] == "desativado":
            return
        self.repository.ensure_session(context, data.session_id, data.metadata)

    def salvar_mensagem(self, context: RequestContext, **kwargs: Any) -> None:
        data = MessageInput(**kwargs)
        if self.repository.get_consent(context)["modo"] == "desativado":
            return
        self.repository.add_message(
            context,
            session_id=data.session_id,
            role=data.role,
            content=data.content,
            agent=data.agent,
            metadata=data.metadata,
        )

    def obter_contexto(
        self,
        context: RequestContext,
        *,
        session_id: str,
        pergunta: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        data = SessionInput(session_id=session_id)
        if self.repository.get_consent(context)["modo"] == "desativado":
            return {
                "contexto": "",
                "resumo": "",
                "preferencias": [],
                "memorias_relevantes": [],
                "mensagens_recentes": [],
            }
        session, messages = self.repository.session_context(
            context, data.session_id, self.recent_messages if limit is None else limit
        )
        memories = (
            self._search_memories(context, pergunta.strip(), 6)
            if pergunta and pergunta.strip()
            else self.repository.list_memories(context, tipo=None, limit=6)
        )
        preferences = self.repository.list_memories(context, tipo="preferencia", limit=20)
        preference_ids = {item["_id"] for item in preferences}
        memories = [item for item in memories if item.get("_id") not in preference_ids]
        parts = []
        if session.get("resumo"):
            parts.append(f"Resumo anterior desta conversa:\n{session['resumo']}")
        if preferences:
            parts.append(
                "Preferências confirmadas pelo usuário:\n"
                + "\n".join(f"- {item['conteudo']}" for item in preferences)
            )
        if memories:
            parts.append(
                "Memórias relevantes de conversas anteriores:\n"
                + "\n".join(f"- [{item['tipo']}] {item['conteudo']}" for item in memories)
            )
        if messages:
            parts.append("Últimas mensagens desta conversa:\n" + _format_messages(messages))
        return {
            "contexto": "\n\n".join(parts),
            "resumo": session.get("resumo", ""),
            "preferencias": [item["conteudo"] for item in preferences],
            "memorias_relevantes": memories,
            "mensagens_recentes": messages,
        }

    def material_resumo(
        self, context: RequestContext, *, session_id: str, forcar: bool = False
    ) -> dict[str, Any]:
        data = SessionInput(session_id=session_id)
        if self.repository.get_consent(context)["modo"] == "desativado":
            return {
                "tem_mensagens": False,
                "deve_resumir": False,
                "resumo_anterior": "",
                "mensagens": [],
                "conversa_formatada": "",
                "resumido_ate": None,
            }
        session, messages = self.repository.summary_material(context, data.session_id)
        last_created = messages[-1]["criada_em"] if messages else None
        return {
            "tem_mensagens": bool(messages),
            "deve_resumir": bool(messages)
            and (forcar or len(messages) >= self.summary_every_messages),
            "resumo_anterior": session.get("resumo", ""),
            "mensagens": messages,
            "conversa_formatada": _format_messages(messages),
            "resumido_ate": last_created,
        }

    def atualizar_resumo(
        self,
        context: RequestContext,
        *,
        session_id: str,
        resumo: str,
        resumido_ate: datetime,
    ) -> None:
        data = SessionInput(session_id=session_id)
        if not resumo.strip():
            raise ValueError("resumo é obrigatório.")
        self.repository.update_summary(context, data.session_id, resumo, resumido_ate)

    def encerrar_sessao(self, context: RequestContext, *, session_id: str) -> bool:
        data = SessionInput(session_id=session_id)
        return self.repository.close_session_if_has_messages(context, data.session_id)

    def listar_chats(self, context: RequestContext, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.repository.list_chats(context, min(max(limit, 1), 100))

    def registrar(self, context: RequestContext, **kwargs: Any) -> bool:
        data = MemoryInput(**kwargs)
        memory = self.repository.store_memory(context, data.model_dump())
        return memory is not None

    def buscar(self, context: RequestContext, *, pergunta: str, limit: int = 6) -> list[dict[str, Any]]:
        if not pergunta.strip():
            raise ValueError("pergunta é obrigatória.")
        return self._search_memories(context, pergunta.strip(), min(max(limit, 1), 20))

    def listar(
        self, context: RequestContext, *, tipo: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        if tipo is not None and tipo not in {
            "preferencia",
            "ponto_relevante",
            "decisao",
            "objetivo",
        }:
            raise ValueError("tipo de memória inválido.")
        return self.repository.list_memories(
            context, tipo=tipo, limit=min(max(limit, 1), 100)
        )

    def excluir(self, context: RequestContext, *, id_memoria: str) -> None:
        if not self.repository.delete_memory(context, id_memoria.strip()):
            raise NotFoundError("Memória não encontrada.")

    def obter_consentimento(self, context: RequestContext) -> dict[str, Any]:
        return self.repository.get_consent(context)

    def configurar_consentimento(
        self, context: RequestContext, *, modo: str, retencao_dias: int | None = None
    ) -> dict[str, Any]:
        data = ConsentInput(modo=modo, retencao_dias=retencao_dias)
        consent = self.repository.set_consent(context, data.modo, data.retencao_dias)
        return consent
