"""Tools locais para o agente descobrir e consultar skills do usuário autenticado."""

from typing import Any

from langchain_core.tools import tool

from clients.skill_client import listar_skills, obter_skill


@tool
def listar_skills_disponiveis(limit: int = 20) -> list[dict[str, str]]:
    """Lista as skills do usuário atual com nome, objetivo curto e comando."""
    skills = listar_skills(limit=min(max(limit, 1), 20))
    return [
        {
            "nome": skill["nome"],
            "slug": skill["slug"],
            "comando": skill["comando"],
            "objetivo": skill["objetivo"][:300],
        }
        for skill in skills
    ]


@tool
def consultar_skill(slug_ou_comando: str) -> dict[str, Any]:
    """Carrega as regras de uma skill do usuário atual pelo slug ou comando."""
    skill = obter_skill(slug_ou_comando)
    return {
        "nome": skill["nome"],
        "objetivo": skill["objetivo"],
        "regras": skill["regras"],
    }


TOOLS = [listar_skills_disponiveis, consultar_skill]
