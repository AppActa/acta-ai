from types import SimpleNamespace

from clients.mcp_acta_client import MCPRequestContext as RequestContext
from agents.helpers.skills.compiler import parse_skill_markdown
from agents.helpers.skills.repository import SkillsRepository


class Cursor:
    def __init__(self, values):
        self.values = values

    def sort(self, *_args):
        return self

    def limit(self, limit):
        self.values = self.values[:limit]
        return self

    def __iter__(self):
        return iter(self.values)


class Collection:
    def __init__(self):
        self.indexes = []
        self.find_one_and_update_result = {"slug": "resumo", "status": "ativa"}
        self.find_one_result = {"slug": "resumo", "status": "ativa"}
        self.find_result = [{"slug": "resumo"}]
        self.update_result = SimpleNamespace(matched_count=1)

    def create_index(self, *args, **kwargs):
        self.indexes.append((args, kwargs))

    def find_one_and_update(self, *args, **kwargs):
        self.update_call = (args, kwargs)
        return self.find_one_and_update_result

    def find_one(self, query):
        self.get_query = query
        return self.find_one_result

    def find(self, query):
        self.list_query = query
        return Cursor(self.find_result)

    def update_one(self, *args, **kwargs):
        self.delete_call = (args, kwargs)
        return self.update_result


def test_skill_repository_scopes_reads_writes_and_soft_deletes() -> None:
    collection = Collection()
    repository = SkillsRepository({"skills_usuario": collection})
    context = RequestContext(usuario_id=7, empresa_id=3, trace_id="skills-repository")
    definition = parse_skill_markdown(
        "# Resumo\n\n# objetivo\n\nResumir dados.\n\n# regras\n\n- Ser claro."
    )

    repository.ensure_indexes()
    created = repository.upsert(context, definition)
    fetched = repository.get(context, "resumo")
    listed = repository.list(context, 5)
    deleted = repository.delete(context, "resumo")

    assert len(collection.indexes) == 2
    assert collection.update_call[0][0] == {
        "usuario_id": 7,
        "empresa_id": 3,
        "slug": "resumo",
    }
    assert created["status"] == "ativa"
    assert fetched["slug"] == "resumo"
    assert collection.get_query["usuario_id"] == 7
    assert listed == [{"slug": "resumo"}]
    assert collection.list_query["empresa_id"] == 3
    assert deleted is True
    assert collection.delete_call[0][0]["status"] == "ativa"


def test_skill_repository_returns_missing_values_without_error() -> None:
    collection = Collection()
    collection.find_one_result = None
    collection.update_result = SimpleNamespace(matched_count=0)
    repository = SkillsRepository({"skills_usuario": collection})
    context = RequestContext(usuario_id=7, empresa_id=3, trace_id="skills-missing")

    assert repository.get(context, "inexistente") is None
    assert repository.delete(context, "inexistente") is False
