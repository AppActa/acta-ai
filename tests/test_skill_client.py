import pytest

import clients.skill_client as skill_client


def test_resolves_slash_command_and_removes_it_before_pipeline(monkeypatch) -> None:
    calls = []

    class SkillsService:
        def obter(self, context, *, nome):
            calls.append((context.usuario_id, context.empresa_id, nome))
            return {
                "nome": "Resumo Executivo",
                "slug": "resumo-executivo",
                "objetivo": "Resumir.",
                "regras": "Usar tópicos.",
            }

    monkeypatch.setattr(skill_client, "get_skills_service", lambda: SkillsService())
    from clients.mcp_acta_client import mcp_request_context

    with mcp_request_context(usuario_id=7, empresa_id=3):
        question, skill = skill_client.resolver_comando_skill(
            "/resumo-executivo Mostre a situação do ciclo."
        )

    assert question == "Mostre a situação do ciclo."
    assert skill["slug"] == "resumo-executivo"
    assert calls == [(7, 3, "resumo-executivo")]


def test_normal_message_does_not_access_skill_storage(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_client,
        "get_skills_service",
        lambda: pytest.fail("armazenamento não deveria ser acessado"),
    )

    assert skill_client.resolver_comando_skill("Como está o ciclo?") == (
        "Como está o ciclo?",
        None,
    )


@pytest.mark.parametrize("message", ["/", "/nome_sem_hifen pergunta", "/skill"])
def test_rejects_invalid_or_empty_skill_command(message: str) -> None:
    with pytest.raises(skill_client.SkillClientError):
        skill_client.resolver_comando_skill(message)


@pytest.mark.parametrize(
    "message",
    [
        "Cria uma skill pra mim que faça um relatório executivo.",
        "Quero criar uma skill com respostas em tópicos.",
        "Pode criar uma skill para resumos do ciclo?",
    ],
)
def test_detects_natural_skill_creation_requests(message: str) -> None:
    assert skill_client.eh_pedido_criacao_skill(message) is True


def test_activation_is_not_mistaken_for_creation() -> None:
    assert skill_client.eh_pedido_criacao_skill(
        "/resumo-executivo Crie uma análise do ciclo."
    ) is False
