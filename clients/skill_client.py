"""Cliente das skills personalizadas armazenadas no MCP ACTA."""

import re
import unicodedata
from typing import Any

from clients.mcp_acta_client import current_mcp_request_context
from agents.helpers.runtime import get_skills_service

_SKILL_COMMAND = re.compile(
    r"^/(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)(?:\s+(?P<message>[\s\S]+))?$"
)


class SkillClientError(ValueError):
    """Skill inexistente, insegura ou chamada com formato inválido."""


def eh_pedido_criacao_skill(message: str) -> bool:
    """Reconhece pedidos naturais de criação sem confundir com `/skill` em uso."""

    stripped = message.strip()
    if stripped.startswith("/"):
        return False
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", stripped.casefold())
        if not unicodedata.combining(character)
    )
    patterns = (
        r"\b(?:crie|cria|criar|monte|monta|faca|fazer)\b.{0,30}\bskill\b",
        r"\b(?:quero|gostaria|pode)\b.{0,20}\bcriar\b.{0,20}\bskill\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def criar_skill(conteudo_markdown: str) -> dict[str, Any]:
    try:
        return get_skills_service().criar(
            current_mcp_request_context(), conteudo_markdown=conteudo_markdown
        )
    except (LookupError, ValueError) as exc:
        raise SkillClientError(str(exc)) from exc


def listar_skills(limit: int = 50) -> list[dict[str, Any]]:
    return get_skills_service().listar(current_mcp_request_context(), limit=limit)


def obter_skill(nome: str) -> dict[str, Any]:
    try:
        return get_skills_service().obter(current_mcp_request_context(), nome=nome)
    except (LookupError, ValueError) as exc:
        raise SkillClientError(str(exc)) from exc


def excluir_skill(nome: str) -> dict[str, Any]:
    try:
        return get_skills_service().excluir(current_mcp_request_context(), nome=nome)
    except (LookupError, ValueError) as exc:
        raise SkillClientError(str(exc)) from exc


def resolver_comando_skill(message: str) -> tuple[str, dict[str, Any] | None]:
    """Remove `/nome-da-skill` antes do roteador e carrega a skill autenticada."""

    stripped = message.strip()
    if not stripped.startswith("/"):
        return stripped, None

    match = _SKILL_COMMAND.fullmatch(stripped)
    if match is None:
        raise SkillClientError(
            "Use a skill como /nome-da-skill seguida da pergunta que deseja fazer."
        )
    question = (match.group("message") or "").strip()
    if not question:
        raise SkillClientError("Escreva uma pergunta depois do comando da skill.")

    skill = obter_skill(match.group("slug"))
    return question, skill
