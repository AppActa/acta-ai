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
    requisicao = Request(
        f"{ACTA_AUTH_API_URL}/contexto",
        headers={"Authorization": f"Bearer {firebase_id_token}"},
        method="GET",
    )

    try:
        with urlopen(requisicao, timeout=ACTA_AUTH_API_TIMEOUT_SECONDS) as resposta_http:
            dados = json.loads(resposta_http.read())
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
            id_usuario=_inteiro_positivo(dados["idUsuario"]),
            id_empresa=_inteiro_positivo(dados["idEmpresa"]),
            id_colaborador=_inteiro_positivo_opcional(dados["idColaborador"]),
            tipo=_texto_nao_vazio(dados["tipo"]),
            permissao_gestor=_booleano(dados["permissaoGestor"]),
            nome_usuario=_texto_nao_vazio_opcional(dados.get("nome")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthApiError(502, "A Auth API retornou um contexto inválido.") from exc


def _inteiro_positivo(valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError("O identificador deve ser um inteiro positivo.")

    return valor


def _inteiro_positivo_opcional(valor: object) -> int | None:
    if valor is None:
        return None

    return _inteiro_positivo(valor)


def _texto_nao_vazio_opcional(valor: object) -> str | None:
    if valor is None:
        return None

    if not isinstance(valor, str):
        raise ValueError("O nome do usuário deve ser texto.")

    texto = valor.strip()
    return texto or None


def _texto_nao_vazio(valor: object) -> str:
    if not isinstance(valor, str) or not valor:
        raise ValueError("O tipo de usuário deve ser uma string não vazia.")

    return valor


def _booleano(valor: object) -> bool:
    if not isinstance(valor, bool):
        raise ValueError("A permissão de gestor deve ser booleana.")

    return valor
