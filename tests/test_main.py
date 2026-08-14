from contextlib import nullcontext
from uuid import UUID

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_health_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "API do ACTA AI está online!"}


def test_new_session_persists_authenticated_owner(monkeypatch) -> None:
    calls = []

    def fake_context(**kwargs):
        calls.append(("context", kwargs))
        return nullcontext()

    monkeypatch.setattr(main, "mcp_request_context", fake_context)
    monkeypatch.setattr(
        main, "garantir_sessao", lambda session_id: calls.append(("session", session_id))
    )

    response = client.post("/nova_sessao", json={"usuario_id": 3, "empresa_id": 4})
    assert response.status_code == 200
    body = response.json()
    UUID(body["session_id"])
    assert body["usuario_id"] == 3
    assert body["empresa_id"] == 4
    assert calls == [
        ("context", {"usuario_id": 3, "empresa_id": 4}),
        ("session", body["session_id"]),
    ]


def test_chat_requires_authenticated_identity() -> None:
    response = client.post(
        "/chat",
        json={"message": "Olá", "session_id": "sessao-1", "usuario_id": 1},
    )
    assert response.status_code == 422


def test_chat_delegates_cycle_and_authenticated_context(monkeypatch) -> None:
    calls = []

    def fake_context(**kwargs):
        calls.append(("context", kwargs))
        return nullcontext()

    def fake_response(**kwargs):
        calls.append(("pipeline", kwargs))
        return "Resposta final"

    monkeypatch.setattr(main, "mcp_request_context", fake_context)
    monkeypatch.setattr(main, "get_response", fake_response)
    response = client.post(
        "/chat",
        json={
            "message": "Como está o ciclo?",
            "session_id": "sessao-2",
            "id_ciclo": 7,
            "usuario_id": 3,
            "empresa_id": 4,
        },
    )
    assert response.status_code == 200
    assert response.json()["resposta"] == "Resposta final"
    assert calls == [
        ("context", {"usuario_id": 3, "empresa_id": 4}),
        ("pipeline", {"message": "Como está o ciclo?", "session_id": "sessao-2", "id_ciclo": 7}),
    ]


def test_memory_consent_and_deletion_endpoints(monkeypatch) -> None:
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(
        main,
        "configurar_consentimento",
        lambda modo, retencao: {"modo": modo, "retencao_dias": retencao},
    )
    monkeypatch.setattr(main, "excluir_memoria", lambda _: None)

    consent = client.put(
        "/memoria/consentimento",
        json={"usuario_id": 3, "empresa_id": 4, "modo": "automatica", "retencao_dias": 60},
    )
    assert consent.status_code == 200
    assert consent.json()["modo"] == "automatica"

    deleted = client.delete("/memoria/abc?usuario_id=3&empresa_id=4")
    assert deleted.status_code == 200
    assert deleted.json() == {"id_memoria": "abc", "excluida": True}


def test_skill_creation_list_and_deletion_endpoints(monkeypatch) -> None:
    contexts = []

    def fake_context(**kwargs):
        contexts.append(kwargs)
        return nullcontext()

    monkeypatch.setattr(main, "mcp_request_context", fake_context)
    monkeypatch.setattr(
        main,
        "criar_skill",
        lambda markdown: {"nome": "Resumo Executivo", "comando": "/resumo-executivo"},
    )
    monkeypatch.setattr(
        main,
        "listar_skills",
        lambda limit=50: [{"nome": "Resumo Executivo", "comando": "/resumo-executivo"}],
    )
    monkeypatch.setattr(
        main,
        "excluir_skill",
        lambda nome: {"status": "ok", "comando": f"/{nome}", "excluida": True},
    )

    markdown = "# Resumo Executivo\n# objetivo\nResumir resultados.\n# regras\nUsar tópicos."
    created = client.post(
        "/skills",
        json={
            "usuario_id": 3,
            "empresa_id": 4,
            "conteudo_markdown": markdown,
        },
    )
    listed = client.get("/skills?usuario_id=3&empresa_id=4")
    deleted = client.delete("/skills/resumo-executivo?usuario_id=3&empresa_id=4")

    assert created.status_code == 200
    assert created.json()["skill"]["comando"] == "/resumo-executivo"
    assert listed.json()["skills"][0]["nome"] == "Resumo Executivo"
    assert deleted.json()["excluida"] is True
    assert contexts == [
        {"usuario_id": 3, "empresa_id": 4},
        {"usuario_id": 3, "empresa_id": 4},
        {"usuario_id": 3, "empresa_id": 4},
    ]
