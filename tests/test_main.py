from contextlib import nullcontext
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import main
from clients.auth_api_client import AuthContext
from clients.skill_client import SkillClientError

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def use_test_auth_context():
    previous_override = main.app.dependency_overrides.get(main.require_auth_context)
    main.app.dependency_overrides[main.require_auth_context] = lambda: AuthContext(
        id_usuario=3,
        id_empresa=4,
        id_colaborador=5,
        tipo="ADMIN",
        permissao_gestor=True,
    )
    yield

    if previous_override is None:
        main.app.dependency_overrides.pop(main.require_auth_context, None)
    else:
        main.app.dependency_overrides[main.require_auth_context] = previous_override


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


def test_list_messages_endpoint_passes_identity_and_limit(monkeypatch) -> None:
    contexts = []
    calls = []

    def fake_context(**kwargs):
        contexts.append(kwargs)
        return nullcontext()

    monkeypatch.setattr(main, "mcp_request_context", fake_context)
    monkeypatch.setattr(
        main,
        "listar_mensagens",
        lambda session_id, limit: calls.append((session_id, limit))
        or [{"role": "usuario", "content": "Oi"}, {"role": "assistente", "content": "Olá"}],
    )

    response = client.get(
        "/chats/session-1/mensagens?usuario_id=3&empresa_id=4&limit=2"
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-1",
        "mensagens": [
            {"role": "usuario", "content": "Oi"},
            {"role": "assistente", "content": "Olá"},
        ],
    }
    assert calls == [("session-1", 2)]
    assert contexts == [{"usuario_id": 3, "empresa_id": 4}]


@pytest.mark.parametrize(
    "error, expected_status", [(main.NotFoundError("Sessão não encontrada."), 404), (main.AuthorizationError("Sem acesso."), 403)]
)
def test_list_messages_endpoint_maps_session_errors(monkeypatch, error, expected_status) -> None:
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(
        main,
        "listar_mensagens",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    response = client.get("/chats/session-1/mensagens?usuario_id=3&empresa_id=4")

    assert response.status_code == expected_status


def test_chat_uses_authenticated_identity_instead_of_body_ids(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(main, "get_response", lambda **kwargs: calls.append(kwargs) or "ok")

    response = client.post(
        "/chat",
        json={
            "message": "Olá",
            "session_id": "sessao-1",
            "usuario_id": 1,
        },
    )
    assert response.status_code == 200
    assert calls[0]["message"] == "Olá"


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
                "nome_usuario": None,
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


def test_chat_accepts_more_than_20_cycles(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(main, "mcp_request_context", lambda **_: nullcontext())
    monkeypatch.setattr(main, "get_response", lambda **kwargs: calls.append(kwargs) or "ok")

    response = client.post(
        "/chat",
        json={
            "message": "Compare os ciclos",
            "session_id": "sessao-sem-limite",
            "id_ciclo": list(range(1, 24)),
            "usuario_id": 3,
            "empresa_id": 4,
        },
    )

    assert response.status_code == 200
    assert calls[0]["id_ciclo"] == list(range(1, 24))


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


def test_old_separate_memory_routes_are_removed() -> None:
    assert client.get("/memoria?usuario_id=3&empresa_id=4").status_code == 404
    assert client.get("/memoria/consentimento?usuario_id=3&empresa_id=4").status_code == 404


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
