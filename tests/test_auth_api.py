import json
from contextlib import nullcontext
from urllib.request import Request

import pytest
from fastapi.testclient import TestClient

import main
from clients.auth_api_client import AuthApiError, AuthContext, get_auth_context


def test_auth_api_client_sends_bearer_token_and_parses_context(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "idUsuario": 17,
                    "idEmpresa": 23,
                    "idColaborador": 31,
                    "tipo": "ADMIN",
                    "permissaoGestor": True,
                    "nome": "Gabriel Pibbles",
                }
            ).encode()

    def fake_urlopen(request: Request, timeout: float):
        observed["url"] = request.full_url
        observed["authorization"] = request.get_header("Authorization")
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr("clients.auth_api_client.urlopen", fake_urlopen)

    context = get_auth_context("firebase-id-token")

    assert observed["url"].endswith("/api/v1/contexto")
    assert observed["authorization"] == "Bearer firebase-id-token"
    assert isinstance(observed["timeout"], float)
    assert context == AuthContext(
        id_usuario=17,
        id_empresa=23,
        id_colaborador=31,
        tipo="ADMIN",
        permissao_gestor=True,
        nome_usuario="Gabriel Pibbles",
    )


def test_auth_api_client_maps_auth_api_401(monkeypatch) -> None:
    from urllib.error import HTTPError

    def unauthorized(*_args, **_kwargs):
        raise HTTPError("https://auth/api/v1/contexto", 401, "invalid", {}, None)

    monkeypatch.setattr("clients.auth_api_client.urlopen", unauthorized)

    with pytest.raises(AuthApiError) as error:
        get_auth_context("expired-token")

    assert error.value.status_code == 401


def test_auth_api_client_accepts_context_without_name(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "idUsuario": 17,
                    "idEmpresa": 23,
                    "idColaborador": None,
                    "tipo": "ADMIN",
                    "permissaoGestor": True,
                }
            ).encode()

    monkeypatch.setattr("clients.auth_api_client.urlopen", lambda *_args, **_kwargs: Response())

    assert get_auth_context("firebase-id-token").nome_usuario is None


def test_protected_route_requires_bearer_token() -> None:
    response = TestClient(main.app).post(
        "/nova_conversa",
        json={"usuario_id": 3, "empresa_id": 4},
    )

    assert response.status_code == 401


def test_protected_route_uses_verified_context_instead_of_client_ids(monkeypatch) -> None:
    contexts = []

    def fake_auth(token: str) -> AuthContext:
        assert token == "valid-token"
        return AuthContext(
            id_usuario=17,
            id_empresa=23,
            id_colaborador=31,
            tipo="ADMIN",
            permissao_gestor=True,
        )

    def fake_mcp_context(**kwargs):
        contexts.append(kwargs)
        return nullcontext()

    monkeypatch.setattr(main, "get_auth_context", fake_auth)
    monkeypatch.setattr(main, "mcp_request_context", fake_mcp_context)

    response = TestClient(main.app).post(
        "/nova_conversa",
        headers={"Authorization": "Bearer valid-token"},
        json={"usuario_id": 3, "empresa_id": 4},
    )

    assert response.status_code == 200
    assert response.json()["usuario_id"] == 17
    assert response.json()["empresa_id"] == 23
    assert contexts == [{"usuario_id": 17, "empresa_id": 23}]


def test_auth_api_unavailable_fails_closed(monkeypatch) -> None:
    def unavailable(_token: str) -> AuthContext:
        raise AuthApiError(503, "Auth API indisponível.")

    monkeypatch.setattr(main, "get_auth_context", unavailable)
    response = TestClient(main.app).post(
        "/nova_conversa",
        headers={"Authorization": "Bearer any-token"},
        json={"usuario_id": 3, "empresa_id": 4},
    )

    assert response.status_code == 503


def test_chat_passes_verified_name_to_pipeline(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        main,
        "get_auth_context",
        lambda _token: AuthContext(
            id_usuario=17,
            id_empresa=23,
            id_colaborador=31,
            tipo="ADMIN",
            permissao_gestor=True,
            nome_usuario="Gabriel Vigna",
        ),
    )
    monkeypatch.setattr(main, "mcp_request_context", lambda **_kwargs: nullcontext())
    monkeypatch.setattr(
        main,
        "get_response",
        lambda **kwargs: calls.append(kwargs) or "ok",
    )

    response = TestClient(main.app).post(
        "/chat",
        headers={"Authorization": "Bearer valid-token"},
        json={"message": "Como me chamo?", "session_id": "sessao-nome"},
    )

    assert response.status_code == 200
    assert calls[0]["nome_usuario"] == "Gabriel Vigna"
