"""Cliente do agente A2A responsável pelas lições aprendidas."""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from typing import Any
from uuid import uuid4

from config import acta_a2a_api_key, acta_a2a_timeout_seconds, acta_a2a_url

_INVALID_RESPONSE = "O agente de lições aprendidas retornou uma resposta inválida."


class A2ALessonClientError(RuntimeError):
    """Falha de comunicação ou resposta inválida do agente A2A."""


def identificar_pedido_licao(mensagem: str) -> str | None:
    """Identifica intenções de negócio encaminhadas ao agente de lições."""

    normalizada = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", mensagem.casefold())
        if not unicodedata.combining(caractere)
    )
    if "licao aprendida" not in normalizada and "licoes aprendidas" not in normalizada:
        return None
    if re.search(r"\b(?:crie|criar|gere|gerar|registre|registrar)\b", normalizada):
        return "criar_licao"
    if re.search(r"\b(?:resuma|resumir|resumo)\b", normalizada):
        return "resumir_licao"
    return "pergunta_licao"


def enviar_pedido_licao(
    *,
    skill: str,
    mensagem: str,
    empresa_id: int,
    id_ciclo: int | None,
) -> str:
    """Envia uma intenção ao agente A2A e devolve sua resposta textual."""

    conteudo = _conteudo_por_skill(skill, mensagem, empresa_id, id_ciclo)
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
            resposta = json.loads(response.read().decode())
    except (OSError, json.JSONDecodeError) as exc:
        raise A2ALessonClientError(
            "O agente de lições aprendidas está indisponível no momento."
        ) from exc
    return _extrair_resposta(resposta)


def _conteudo_por_skill(
    skill: str,
    mensagem: str,
    empresa_id: int,
    id_ciclo: int | None,
) -> dict[str, Any]:
    conteudo: dict[str, Any] = {"skill": skill, "id_empresa": empresa_id}
    if id_ciclo is not None:
        conteudo["id_ciclo"] = id_ciclo
    if skill == "criar_licao":
        if id_ciclo is None:
            raise A2ALessonClientError("Selecione um ciclo para criar uma lição aprendida.")
        conteudo["contexto"] = mensagem
        conteudo["expectativa"] = mensagem
    elif skill == "pergunta_licao":
        conteudo["pergunta"] = mensagem
    elif skill != "resumir_licao":
        raise A2ALessonClientError("Tipo de solicitação de lição aprendida inválido.")
    return conteudo


def _extrair_resposta(resposta: Any) -> str:
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
    for campo in ("resposta", "resumo", "mensagem"):
        valor = dados.get(campo)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    if dados.get("url"):
        return f"Lição aprendida criada com sucesso. PDF: {dados['url']}"
    raise A2ALessonClientError("O agente de lições aprendidas não retornou conteúdo.")
