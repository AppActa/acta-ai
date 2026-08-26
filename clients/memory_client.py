"""Fachada do acta-ai para as operações de memória fornecidas pelo MCP."""

from datetime import datetime
from typing import Any

from clients.mcp_acta_client import MCPActaError, call_acta_tool


def _dict_result(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = call_acta_tool(tool_name, arguments)
    if not isinstance(result, dict):
        raise MCPActaError(f"A tool '{tool_name}' não retornou um objeto estruturado.")
    if result.get("status") != "ok":
        raise MCPActaError(str(result.get("message", f"Falha em {tool_name}.")))
    return result


def garantir_sessao(session_id: str, metadata: dict[str, Any] | None = None) -> None:
    _dict_result("memoria_garantir_sessao", {"session_id": session_id, "metadata": metadata})


def salvar_mensagem(
    *, session_id: str, role: str, content: str, agent: str, metadata: dict[str, Any] | None = None
) -> None:
    role_map = {
        "human": "usuario",
        "user": "usuario",
        "ai": "assistente",
        "assistant": "assistente",
    }
    _dict_result(
        "memoria_salvar_mensagem",
        {
            "session_id": session_id,
            "role": role_map.get(role.lower(), role.lower()),
            "content": content,
            "agent": agent,
            "metadata": metadata,
        },
    )


def obter_contexto_detalhado(session_id: str, pergunta: str = "") -> dict[str, Any]:
    return _dict_result("memoria_obter_contexto", {"session_id": session_id, "pergunta": pergunta})


def obter_contexto(session_id: str, pergunta: str) -> str:
    result = obter_contexto_detalhado(session_id, pergunta)
    return str(result.get("contexto", ""))


def obter_material_resumo(session_id: str) -> dict[str, Any]:
    return _dict_result("memoria_material_resumo", {"session_id": session_id})


def atualizar_resumo(session_id: str, resumo: str, resumido_ate: str | datetime) -> None:
    marker = resumido_ate.isoformat() if isinstance(resumido_ate, datetime) else resumido_ate
    _dict_result(
        "memoria_atualizar_resumo",
        {"session_id": session_id, "resumo": resumo, "resumido_ate": marker},
    )


def registrar_memoria(
    *,
    tipo: str,
    conteudo: str,
    session_id: str,
    origem: str = "explicita",
    confianca: float = 1.0,
) -> bool:
    result = _dict_result(
        "memoria_registrar",
        {
            "tipo": tipo,
            "conteudo": conteudo,
            "origem": origem,
            "confianca": confianca,
            "session_id_origem": session_id,
        },
    )
    return bool(result.get("salva"))


def listar_memorias(tipo: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    result = _dict_result("memoria_listar", {"tipo": tipo, "limit": limit})
    return list(result.get("memorias", []))


def excluir_memoria(id_memoria: str) -> None:
    _dict_result("memoria_excluir", {"id_memoria": id_memoria})


def obter_consentimento() -> dict[str, Any]:
    result = _dict_result("memoria_obter_consentimento", {})
    return dict(result.get("consentimento", {}))


def configurar_consentimento(modo: str, retencao_dias: int | None = None) -> dict[str, Any]:
    result = _dict_result(
        "memoria_configurar_consentimento",
        {"modo": modo, "retencao_dias": retencao_dias},
    )
    return dict(result.get("consentimento", {}))
