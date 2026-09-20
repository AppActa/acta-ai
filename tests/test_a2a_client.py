import json
from contextlib import contextmanager

import pytest

from clients import a2a_client
from clients.a2a_client import A2ALessonClientError, enviar_pedido_licao
from clients.mcp_acta_client import mcp_request_context


class _RespostaHTTP:
    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


def test_summary_request_uses_trusted_company_and_cycle_in_a2a_message(
    monkeypatch,
) -> None:
    sent = {}

    @contextmanager
    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["timeout"] = timeout
        sent["authorization"] = request.headers.get("Authorization")
        sent["payload"] = json.loads(request.data)
        yield _RespostaHTTP(
            {
                "jsonrpc": "2.0",
                "id": "request-1",
                "result": {
                    "artifacts": [
                        {"parts": [{"data": {"status": "ok", "resumo": "Resumo pronto."}}]}
                    ]
                },
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("ACTA_A2A_API_KEY", "chave-de-teste")

    with mcp_request_context(usuario_id=3, empresa_id=4), a2a_client.a2a_lesson_context(
        id_ciclo=7
    ):
        response = enviar_pedido_licao(skill="resumir_licao", payload={})

    assert response == {"status": "ok", "resumo": "Resumo pronto."}
    assert sent["url"] == "http://127.0.0.1:8100/"
    assert sent["timeout"] == 45.0
    assert sent["authorization"] == "Bearer chave-de-teste"
    payload = json.loads(sent["payload"]["params"]["message"]["parts"][0]["text"])
    assert payload == {"skill": "resumir_licao", "id_empresa": 4, "id_ciclo": 7}


def test_create_request_preserves_agent_authored_text_and_trusted_identity(
    monkeypatch,
) -> None:
    captured = {}

    def fake_post(request):
        captured["request"] = request
        return {
            "jsonrpc": "2.0",
            "id": "request-1",
            "result": {
                "artifacts": [
                    {"parts": [{"data": {"status": "ok", "mensagem": "Criada."}}]}
                ]
            },
        }

    monkeypatch.setattr(a2a_client, "_post_jsonrpc", fake_post, raising=False)

    with mcp_request_context(usuario_id=3, empresa_id=4), a2a_client.a2a_lesson_context(
        id_ciclo=7
    ):
        result = enviar_pedido_licao(
            skill="criar_licao",
            payload={
                "contexto": "Falha na inspeção final identificada pelo agente.",
                "expectativa": "Registrar uma prevenção para a próxima inspeção.",
            },
        )

    body = json.loads(captured["request"]["params"]["message"]["parts"][0]["text"])
    assert body == {
        "skill": "criar_licao",
        "id_empresa": 4,
        "id_ciclo": 7,
        "contexto": "Falha na inspeção final identificada pelo agente.",
        "expectativa": "Registrar uma prevenção para a próxima inspeção.",
    }
    assert result == {"status": "ok", "mensagem": "Criada."}


def test_create_request_requires_an_active_cycle_context() -> None:
    with mcp_request_context(usuario_id=3, empresa_id=4), pytest.raises(
        A2ALessonClientError, match="ciclo ativo"
    ):
        enviar_pedido_licao(
            skill="criar_licao",
            payload={"contexto": "Contexto", "expectativa": "Expectativa"},
        )
