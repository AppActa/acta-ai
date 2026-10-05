from contextlib import nullcontext
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import main
from clients.skill_client import SkillClientError

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
        json={
            "message": "Olá",
            "session_id": "sessao-1",
            "usuario_id": 1,
        },
    )
    assert response.status_code == 422


def test_chat_normalizes_cycles_and_delegates_active_cycle(monkeypatch) -> None:
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
            "id_ciclo": [8, 4, 8],
            "ciclo_ativo": 4,
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
                "id_ciclo": [8, 4],
                "ciclo_ativo": 4,
                "empresa_id": 4,
            },
        ),
    ]


def test_chat_accepts_legacy_single_cycle_id(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "get_response", lambda **kwargs: calls.append(kwargs) or "ok")

    response = client.post(
        "/chat",
        json={
            "message": "Como está o ciclo?",
            "session_id": "sessao-legada",
            "id_ciclo": 7,
            "usuario_id": 3,
            "empresa_id": 4,
        },
    )

    assert response.status_code == 200
    assert calls[0]["id_ciclo"] == [7]


def test_chat_rejects_more_than_20_cycles(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "get_response", lambda **kwargs: calls.append(kwargs) or "ok")

    response = client.post(
        "/chat",
        json={
            "message": "Compare os ciclos",
            "session_id": "sessao-limite",
            "id_ciclo": list(range(1, 22)),
            "usuario_id": 3,
            "empresa_id": 4,
        },
    )

    assert response.status_code == 422


def test_chat_accepts_exactly_20_cycles(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "get_response", lambda **kwargs: calls.append(kwargs) or "ok")

    response = client.post(
        "/chat",
        json={
            "message": "Compare os ciclos",
            "session_id": "sessao-limite-valido",
            "id_ciclo": list(range(1, 21)),
            "usuario_id": 3,
            "empresa_id": 4,
        },
    )

    assert response.status_code == 200
    assert len(calls[0]["id_ciclo"]) == 20


@pytest.mark.parametrize(
    "cycles, active, expected_status, normalized",
    [
        ([], None, 200, []),
        ([8, 4, 8], None, 200, [8, 4]),
        ([8, 4], 4, 200, [8, 4]),
        ([8, 4], 9, 422, None),
        ([0], None, 422, None),
        ([-1], None, 422, None),
    ],
)
def test_chat_cycle_scope_validation(
    monkeypatch, cycles, active, expected_status, normalized
) -> None:
    calls = []
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "get_response", lambda **kwargs: calls.append(kwargs) or "ok")
    payload = {
        "message": "Pergunta",
        "session_id": "sessao",
        "id_ciclo": cycles,
        "usuario_id": 3,
        "empresa_id": 4,
    }
    if active is not None:
        payload["ciclo_ativo"] = active

    response = client.post("/chat", json=payload)

    assert response.status_code == expected_status
    if expected_status == 200:
        assert calls[0]["id_ciclo"] == normalized
    else:
        assert calls == []


def test_audio_chat_passes_normalized_cycle_scope(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "transcrever_audio", lambda *_args, **_kwargs: "Pergunta falada")
    monkeypatch.setattr(main, "get_response", lambda **kwargs: calls.append(kwargs) or "ok")

    response = client.post(
        "/chat/audio",
        data={
            "session_id": "sessao-audio",
            "usuario_id": "3",
            "empresa_id": "4",
            "id_ciclo": ["8", "4", "8"],
            "ciclo_ativo": "4",
        },
        files={"audio": ("audio.webm", b"audio", "audio/webm")},
    )

    assert response.status_code == 200
    assert calls[0]["id_ciclo"] == [8, 4]
    assert calls[0]["ciclo_ativo"] == 4


def test_audio_chat_accepts_legacy_single_cycle_id(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "transcrever_audio", lambda *_args, **_kwargs: "Pergunta falada")
    monkeypatch.setattr(main, "get_response", lambda **kwargs: calls.append(kwargs) or "ok")

    response = client.post(
        "/chat/audio",
        data={
            "session_id": "sessao-audio-legada",
            "usuario_id": "3",
            "empresa_id": "4",
            "id_ciclo": "7",
        },
        files={"audio": ("audio.webm", b"audio", "audio/webm")},
    )

    assert response.status_code == 200
    assert calls[0]["id_ciclo"] == [7]


def test_audio_chat_rejects_more_than_20_cycles(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "transcrever_audio", lambda *_args, **_kwargs: "Pergunta falada")
    monkeypatch.setattr(main, "get_response", lambda **kwargs: calls.append(kwargs) or "ok")

    response = client.post(
        "/chat/audio",
        data={
            "session_id": "sessao-audio-limite",
            "usuario_id": "3",
            "empresa_id": "4",
            "id_ciclo": [str(cycle_id) for cycle_id in range(1, 22)],
        },
        files={"audio": ("audio.webm", b"audio", "audio/webm")},
    )

    assert response.status_code == 422
    assert calls == []


def test_audio_chat_returns_bad_request_when_skill_is_invalid(monkeypatch) -> None:
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "transcrever_audio", lambda *_args, **_kwargs: "Use a skill inválida.")
    monkeypatch.setattr(
        main,
        "get_response",
        lambda **_: (_ for _ in ()).throw(SkillClientError("Skill inválida.")),
    )

    response = client.post(
        "/chat/audio",
        data={"session_id": "sessao-audio", "usuario_id": "3", "empresa_id": "4"},
        files={"audio": ("audio.webm", b"audio", "audio/webm")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Skill inválida."


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


def test_memory_search_endpoint_uses_request_identity(monkeypatch) -> None:
    contexts = []
    calls = []

    def fake_context(**kwargs):
        contexts.append(kwargs)
        return nullcontext()

    monkeypatch.setattr(main, "mcp_request_context", fake_context)
    monkeypatch.setattr(
        main,
        "buscar_memorias",
        lambda pergunta, limit: calls.append((pergunta, limit)) or [{"conteudo": "Evidência"}],
    )

    response = client.get(
        "/memoria/buscar?pergunta=prefer%C3%AAncia&usuario_id=3&empresa_id=4&limit=5"
    )

    assert response.status_code == 200
    assert response.json() == {"memorias": [{"conteudo": "Evidência"}]}
    assert calls == [("preferência", 5)]
    assert contexts == [{"usuario_id": 3, "empresa_id": 4}]


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
