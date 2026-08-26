"""Compatibilidade temporária para o antigo módulo de memória local.

O armazenamento foi movido para o MCP. Código novo deve importar
``clients.memory_client`` diretamente. Estas funções não abrem conexão MongoDB.
"""

from typing import Any

from clients.memory_client import (
    garantir_sessao as _garantir_sessao,
)
from clients.memory_client import (
    obter_contexto_detalhado,
)
from clients.memory_client import (
    salvar_mensagem as _salvar_mensagem,
)


def iniciar_sessao(
    session_id: str,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    del user_id  # A identidade vem do contexto autenticado, nunca deste argumento.
    _garantir_sessao(session_id, metadata)
    return session_id


def garantir_sessao(session_id: str, user_id: str | None = None) -> str:
    return iniciar_sessao(session_id, user_id=user_id)


def salvar_mensagem(
    session_id: str,
    role: str,
    content: str,
    agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    _salvar_mensagem(
        session_id=session_id,
        role=role,
        content=content,
        agent=agent or "desconhecido",
        metadata=metadata,
    )


def buscar_sessao(session_id: str) -> dict[str, Any]:
    result = obter_contexto_detalhado(session_id)
    return {
        "session_id": session_id,
        "resumo": result.get("resumo", ""),
        "mensagens": result.get("mensagens_recentes", []),
    }


def listar_mensagens(session_id: str, limite: int = 20) -> list[dict[str, Any]]:
    result = obter_contexto_detalhado(session_id)
    return list(result.get("mensagens_recentes", []))[-limite:]


def obter_contexto_memoria(session_id: str, limite: int = 10) -> str:
    del limite  # O limite central é aplicado pelo MCP.
    return str(obter_contexto_detalhado(session_id).get("contexto", ""))
