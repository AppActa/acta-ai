"""Cliente do agente A2A responsável pelas lições aprendidas."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal
from uuid import uuid4

from clients.mcp_acta_client import MCPActaError, current_mcp_request_context
from config import acta_a2a_api_key, acta_a2a_timeout_seconds, acta_a2a_url

_INVALID_RESPONSE = "O agente de lições aprendidas retornou uma resposta inválida."


class A2ALessonClientError(RuntimeError):
    """Falha de comunicação ou resposta inválida do agente A2A."""


_active_cycle_id: ContextVar[int | None] = ContextVar(
    "acta_ai_a2a_lesson_cycle_id",
    default=None,
)


@contextmanager
def a2a_lesson_context(*, id_ciclo: int) -> Iterator[None]:
    """Define o ciclo autorizado durante uma execução do especialista."""

    if id_ciclo <= 0:
        raise A2ALessonClientError("O ciclo ativo deve ser um inteiro positivo.")
    token = _active_cycle_id.set(id_ciclo)
    try:
        yield
    finally:
        _active_cycle_id.reset(token)


def enviar_pedido_licao(
    *,
    skill: Literal["criar_licao", "resumir_licao", "pergunta_licao"],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Envia um payload já produzido pelo especialista ao agente A2A."""

    conteudo = _payload_with_identity(skill, payload)
    requisicao = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": json.dumps(conteudo)}],
            }
        },
    }
    resposta = _post_jsonrpc(requisicao)
    return _extrair_resposta(resposta)


def _post_jsonrpc(requisicao: dict[str, Any]) -> Any:
    headers = {"Content-Type": "application/json"}
    api_key = acta_a2a_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        acta_a2a_url(),
        data=json.dumps(requisicao).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=acta_a2a_timeout_seconds()) as response:
            return json.loads(response.read().decode())
    except (OSError, json.JSONDecodeError) as exc:
        raise A2ALessonClientError(
            "O agente de lições aprendidas está indisponível no momento."
        ) from exc


def _payload_with_identity(skill: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        identity = current_mcp_request_context()
    except MCPActaError as exc:
        raise A2ALessonClientError(str(exc)) from exc

    conteudo = {"skill": skill, "id_empresa": identity.empresa_id, **payload}
    if skill in {"criar_licao", "pergunta_licao"}:
        conteudo["id_ciclo"] = _active_lesson_cycle_id()
        _require_nonblank_fields(conteudo, "contexto", "expectativa") if skill == "criar_licao" else _require_nonblank_fields(conteudo, "pergunta")
    elif skill == "resumir_licao":
        id_ciclo = _active_cycle_id.get()
        if id_ciclo is not None:
            conteudo["id_ciclo"] = id_ciclo
    else:
        raise A2ALessonClientError("Tipo de solicitação de lição aprendida inválido.")
    return conteudo


def _active_lesson_cycle_id() -> int:
    id_ciclo = _active_cycle_id.get()
    if id_ciclo is None:
        raise A2ALessonClientError("Não há ciclo ativo para a solicitação de lição.")
    return id_ciclo


def _require_nonblank_fields(payload: dict[str, Any], *fields: str) -> None:
    if any(not isinstance(payload.get(field), str) or not payload[field].strip() for field in fields):
        raise A2ALessonClientError("A solicitação de lição contém campos obrigatórios vazios.")


def _extrair_resposta(resposta: Any) -> dict[str, Any]:
    if not isinstance(resposta, dict):
        raise A2ALessonClientError(_INVALID_RESPONSE)
    if resposta.get("error"):
        raise A2ALessonClientError("O agente de lições aprendidas não conseguiu atender a solicitação.")
    try:
        dados = resposta["result"]["artifacts"][0]["parts"][0]["data"]
    except (KeyError, IndexError, TypeError) as exc:
        raise A2ALessonClientError(_INVALID_RESPONSE) from exc
    if not isinstance(dados, dict):
        raise A2ALessonClientError(_INVALID_RESPONSE)
    if not dados:
        raise A2ALessonClientError("O agente de lições aprendidas não retornou conteúdo.")
    return dados
