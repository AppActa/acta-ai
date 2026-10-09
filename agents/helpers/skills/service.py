from typing import Any

from agents.helpers.errors import NotFoundError
from agents.helpers.skills.compiler import normalize_skill_command, parse_skill_markdown
from agents.helpers.skills.repository import SkillsRepository
from clients.mcp_acta_client import MCPRequestContext as RequestContext


class SkillsService:
    def __init__(self, repository: SkillsRepository) -> None:
        self.repository = repository

    def ensure_indexes(self) -> None:
        self.repository.ensure_indexes()

    @staticmethod
    def _safe_output(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": document.get("_id"),
            "nome": document["nome"],
            "slug": document["slug"],
            "comando": f"/{document['slug']}",
            "objetivo": document["objetivo"],
            "regras": document["regras"],
            "markdown": document["markdown"],
            "criada_em": document.get("criada_em"),
            "atualizada_em": document.get("atualizada_em"),
        }

    def criar(self, context: RequestContext, *, conteudo_markdown: str) -> dict[str, Any]:
        definition = parse_skill_markdown(conteudo_markdown)
        stored = self.repository.upsert(context, definition)
        return self._safe_output(stored)

    def obter(self, context: RequestContext, *, nome: str) -> dict[str, Any]:
        slug = normalize_skill_command(nome)
        document = self.repository.get(context, slug)
        if document is None:
            raise NotFoundError(f"A skill /{slug} não foi encontrada.")

        # Revalida no uso. Assim, alteração direta ou corrupção no Mongo não vira prompt.
        definition = parse_skill_markdown(document.get("markdown", ""))
        if definition.slug != slug:
            raise ValueError("A skill armazenada falhou na validação de integridade.")
        validated = {**document, **definition.model_dump()}
        return self._safe_output(validated)

    def listar(self, context: RequestContext, *, limit: int = 50) -> list[dict[str, Any]]:
        documents = self.repository.list(context, min(max(limit, 1), 100))
        skills = [
            {
                "nome": item["nome"],
                "slug": item["slug"],
                "comando": f"/{item['slug']}",
                "atualizada_em": item.get("atualizada_em"),
            }
            for item in documents
        ]
        return skills

    def excluir(self, context: RequestContext, *, nome: str) -> dict[str, Any]:
        slug = normalize_skill_command(nome)
        if not self.repository.delete(context, slug):
            raise NotFoundError(f"A skill /{slug} não foi encontrada.")
        return {"comando": f"/{slug}", "excluida": True}
