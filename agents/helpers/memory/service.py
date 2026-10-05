from datetime import datetime
from typing import Any

from clients.mcp_acta_client import MCPRequestContext as RequestContext
from agents.helpers.errors import NotFoundError
from agents.helpers.memory.repository import MemoryRepository
from agents.helpers.memory.schemas import ConsentInput, MemoryInput, MessageInput, SessionInput


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
        if getattr(self.repository, "qdrant", object()) is None:
            return self.repository.list_memories(context, tipo=None, limit=limit)
        try:
            return self.repository.semantic_search(context, question, limit)
        except Exception:
            return self.repository.list_memories(context, tipo=None, limit=limit)

    def garantir_sessao(
        self, context: RequestContext, *, session_id: str, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = SessionInput(session_id=session_id, metadata=metadata or {})
        if self.repository.get_consent(context)["modo"] == "desativado":
            return {
                "status": "ok",
                "session_id": data.session_id,
                "persistencia_ativa": False,
            }
        session = self.repository.ensure_session(context, data.session_id, data.metadata)
        return {
            "status": "ok",
            "session_id": session["session_id"],
            "persistencia_ativa": True,
        }

    def salvar_mensagem(self, context: RequestContext, **kwargs: Any) -> dict[str, Any]:
        data = MessageInput(**kwargs)
        if self.repository.get_consent(context)["modo"] == "desativado":
            return {"status": "ok", "salva": False, "motivo": "Memória desativada."}
        message = self.repository.add_message(
            context,
            session_id=data.session_id,
            role=data.role,
            content=data.content,
            agent=data.agent,
            metadata=data.metadata,
        )
        return {"status": "ok", "salva": True, "id_mensagem": message["_id"]}

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
                "status": "ok",
                "contexto": "",
                "resumo": "",
                "preferencias": [],
                "memorias_relevantes": [],
                "mensagens_recentes": [],
            }
        session, messages = self.repository.session_context(
            context, data.session_id, limit or self.recent_messages
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
            "status": "ok",
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
                "status": "ok",
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
            "status": "ok",
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
    ) -> dict[str, Any]:
        data = SessionInput(session_id=session_id)
        if not resumo.strip():
            raise ValueError("resumo é obrigatório.")
        self.repository.update_summary(context, data.session_id, resumo, resumido_ate)
        return {"status": "ok", "session_id": data.session_id}

    def encerrar_sessao(self, context: RequestContext, *, session_id: str) -> dict[str, Any]:
        data = SessionInput(session_id=session_id)
        closed = self.repository.close_session_if_has_messages(context, data.session_id)
        return {"status": "ok", "encerrada": closed, "tem_mensagens": closed}

    def listar_chats(self, context: RequestContext, *, limit: int = 50) -> dict[str, Any]:
        chats = self.repository.list_chats(context, min(max(limit, 1), 100))
        return {"status": "ok", "count": len(chats), "chats": chats}

    def registrar(self, context: RequestContext, **kwargs: Any) -> dict[str, Any]:
        data = MemoryInput(**kwargs)
        memory = self.repository.store_memory(context, data.model_dump())
        if memory is None:
            return {
                "status": "ok",
                "salva": False,
                "motivo": "O consentimento atual não permite esta memória.",
            }
        return {"status": "ok", "salva": True, "memoria": memory}

    def buscar(self, context: RequestContext, *, pergunta: str, limit: int = 6) -> dict[str, Any]:
        if not pergunta.strip():
            raise ValueError("pergunta é obrigatória.")
        memories = self._search_memories(context, pergunta.strip(), min(max(limit, 1), 20))
        return {"status": "ok", "count": len(memories), "memorias": memories}

    def listar(
        self, context: RequestContext, *, tipo: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        if tipo is not None and tipo not in {
            "preferencia",
            "ponto_relevante",
            "decisao",
            "objetivo",
        }:
            raise ValueError("tipo de memória inválido.")
        memories = self.repository.list_memories(context, tipo=tipo, limit=min(max(limit, 1), 100))
        return {"status": "ok", "count": len(memories), "memorias": memories}

    def excluir(self, context: RequestContext, *, id_memoria: str) -> dict[str, Any]:
        if not self.repository.delete_memory(context, id_memoria.strip()):
            raise NotFoundError("Memória não encontrada.")
        return {"status": "ok", "id_memoria": id_memoria, "excluida": True}

    def obter_consentimento(self, context: RequestContext) -> dict[str, Any]:
        return {"status": "ok", "consentimento": self.repository.get_consent(context)}

    def configurar_consentimento(
        self, context: RequestContext, *, modo: str, retencao_dias: int | None = None
    ) -> dict[str, Any]:
        data = ConsentInput(modo=modo, retencao_dias=retencao_dias)
        consent = self.repository.set_consent(context, data.modo, data.retencao_dias)
        return {"status": "ok", "consentimento": consent}
