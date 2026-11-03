"""Cliente para validar o Firebase ID Token e obter o contexto ACTA."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import ACTA_AUTH_API_TIMEOUT_SECONDS, ACTA_AUTH_API_URL


class AuthApiError(Exception):
    """Falha ao validar a identidade ou consultar o contexto ACTA."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AuthContext:
    id_usuario: int
    id_empresa: int
    id_colaborador: int | None
    tipo: str
    permissao_gestor: bool
    nome_usuario: str | None = None


def get_auth_context(firebase_id_token: str) -> AuthContext:
    """Valida o token na Auth API e retorna somente a identidade autorizada."""
    request = Request(
        f"{ACTA_AUTH_API_URL}/contexto",
        headers={"Authorization": f"Bearer {firebase_id_token}"},
        method="GET",
    )

    try:
        with urlopen(request, timeout=ACTA_AUTH_API_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise AuthApiError(exc.code, "A Auth API recusou a identidade.") from exc

        raise AuthApiError(503, "A Auth API não está disponível.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise AuthApiError(503, "A Auth API não está disponível.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuthApiError(502, "A Auth API retornou uma resposta inválida.") from exc

    try:
        return AuthContext(
            id_usuario=_positive_int(payload["idUsuario"]),
            id_empresa=_positive_int(payload["idEmpresa"]),
            id_colaborador=_optional_positive_int(payload["idColaborador"]),
            tipo=_non_empty_string(payload["tipo"]),
            permissao_gestor=_boolean(payload["permissaoGestor"]),
            nome_usuario=_optional_non_empty_string(payload.get("nome")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthApiError(502, "A Auth API retornou um contexto inválido.") from exc


def _positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("O identificador deve ser um inteiro positivo.")

    return value


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None

    return _positive_int(value)


def _optional_non_empty_string(value: object) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("O nome do usuário deve ser texto.")

    normalized = value.strip()
    return normalized or None


def _non_empty_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("O tipo de usuário deve ser uma string não vazia.")

    return value


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("A permissão de gestor deve ser booleana.")

    return value
