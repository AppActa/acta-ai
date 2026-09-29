from clients.mcp_acta_client import mcp_request_context
from utils import runtime


def test_memory_and_skill_services_are_cached_and_initialized(monkeypatch) -> None:
    database = object()
    memory_repositories = []
    skill_repositories = []

    class MemoryRepository:
        def __init__(self, *args, **kwargs):
            self.args, self.kwargs = args, kwargs
            self.indexed = False
            memory_repositories.append(self)

        def ensure_indexes(self):
            self.indexed = True

    class SkillsRepository:
        def __init__(self, db):
            self.db = db
            self.indexed = False
            skill_repositories.append(self)

        def ensure_indexes(self):
            self.indexed = True

    monkeypatch.setattr(runtime, "_mongo_database", lambda: database)
    monkeypatch.setattr(runtime, "_qdrant_client", lambda: None)
    monkeypatch.setattr(runtime, "MemoryRepository", MemoryRepository)
    monkeypatch.setattr(runtime, "MemoryService", lambda repository, **kwargs: (repository, kwargs))
    monkeypatch.setattr(runtime, "SkillsRepository", SkillsRepository)
    class SkillsService:
        def __init__(self, repository):
            self.repository = repository

        def ensure_indexes(self):
            self.repository.ensure_indexes()

    monkeypatch.setattr(runtime, "SkillsService", SkillsService)
    runtime.get_memory_service.cache_clear()
    runtime.get_skills_service.cache_clear()

    try:
        memory_service = runtime.get_memory_service()
        skills_service = runtime.get_skills_service()

        assert runtime.get_memory_service() is memory_service
        assert runtime.get_skills_service() is skills_service
        assert memory_repositories[0].indexed is True
        assert memory_repositories[0].args[0] is database
        assert memory_repositories[0].args[1] is None
        assert skill_repositories[0].db is database
        assert skill_repositories[0].indexed is True
    finally:
        runtime.get_memory_service.cache_clear()
        runtime.get_skills_service.cache_clear()


def test_current_identity_reads_authenticated_request_context() -> None:
    with mcp_request_context(usuario_id=8, empresa_id=4, trace_id="runtime-test") as context:
        assert runtime.current_identity() is context
