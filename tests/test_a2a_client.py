import json
from contextlib import contextmanager

from clients.a2a_client import enviar_pedido_licao


class _RespostaHTTP:
    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


def test_summary_request_uses_company_and_cycle_in_a2a_message(monkeypatch) -> None:
    sent = {}

    @contextmanager
    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["timeout"] = timeout
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

    response = enviar_pedido_licao(
        skill="resumir_licao",
        mensagem="Resuma as lições aprendidas.",
        empresa_id=4,
        id_ciclo=7,
    )

    assert response == "Resumo pronto."
    assert sent["url"] == "http://127.0.0.1:8100/"
    assert sent["timeout"] == 45.0
    payload = json.loads(sent["payload"]["params"]["message"]["parts"][0]["text"])
    assert payload == {"skill": "resumir_licao", "id_empresa": 4, "id_ciclo": 7}
