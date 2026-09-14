from contextlib import nullcontext
from uuid import UUID

from fastapi.testclient import TestClient

import main
from clients.a2a_client import A2ALessonClientError

client = TestClient(main.app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"message": "API do ACTA AI está online!"}


def test_new_conversation_returns_unpersisted_session(monkeypatch) -> None:
    calls = []

    def fake_context(**kwargs):
        calls.append(("context", kwargs))
        return nullcontext()

    monkeypatch.setattr(main, "mcp_request_context", fake_context)
    response = client.post("/nova_conversa", json={"usuario_id": 3, "empresa_id": 4})
    assert response.status_code == 200
    body = response.json()
    UUID(body["session_id"])
    assert body["usuario_id"] == 3
    assert body["empresa_id"] == 4
    assert body["conversa_anterior_encerrada"] is False
    assert calls == [("context", {"usuario_id": 3, "empresa_id": 4})]


def test_new_conversation_keeps_previous_chat_open_when_summary_fails(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "consolidar_memoria", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(main, "encerrar_sessao", lambda session_id: calls.append(session_id) or True)

    response = client.post(
        "/nova_conversa",
        json={"usuario_id": 3, "empresa_id": 4, "session_id_atual": "session-previous"},
    )

    assert response.status_code == 200
    assert response.json()["conversa_anterior_encerrada"] is False
    assert calls == []


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
        (
            "pipeline",
            {
                "message": "Como está o ciclo?",
                "session_id": "sessao-2",
                "id_ciclo": 7,
                "empresa_id": 4,
            },
        ),
    ]


def test_chat_returns_service_unavailable_when_a2a_is_offline(monkeypatch) -> None:
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(
        main,
        "get_response",
        lambda **_: (_ for _ in ()).throw(A2ALessonClientError("A2A indisponível.")),
    )

    response = client.post(
        "/chat",
        json={
            "message": "Resuma as lições aprendidas.",
            "session_id": "sessao-a2a",
            "usuario_id": 3,
            "empresa_id": 4,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "A2A indisponível."


def test_audio_chat_returns_service_unavailable_when_a2a_is_offline(monkeypatch) -> None:
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "transcrever_audio", lambda *_args, **_kwargs: "Resuma as lições.")
    monkeypatch.setattr(
        main,
        "get_response",
        lambda **_: (_ for _ in ()).throw(A2ALessonClientError("A2A indisponível.")),
    )

    response = client.post(
        "/chat/audio",
        data={"session_id": "sessao-audio", "usuario_id": "3", "empresa_id": "4"},
        files={"audio": ("audio.webm", b"audio", "audio/webm")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "A2A indisponível."


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
