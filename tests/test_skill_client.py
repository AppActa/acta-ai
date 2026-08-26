import pytest

import clients.skill_client as skill_client


def test_resolves_slash_command_and_removes_it_before_pipeline(monkeypatch) -> None:
    calls = []

    def fake_call(name, arguments):
        calls.append((name, arguments))
        return {
            "status": "ok",
            "skill": {
                "nome": "Resumo Executivo",
                "slug": "resumo-executivo",
                "objetivo": "Resumir.",
                "regras": "Usar tópicos.",
            },
        }

    monkeypatch.setattr(skill_client, "call_acta_tool", fake_call)

    question, skill = skill_client.resolver_comando_skill(
        "/resumo-executivo Mostre a situação do ciclo."
    )

    assert question == "Mostre a situação do ciclo."
    assert skill["slug"] == "resumo-executivo"
    assert calls == [("skills_obter", {"nome": "resumo-executivo"})]


def test_normal_message_does_not_access_skill_storage(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_client,
        "call_acta_tool",
        lambda *_: pytest.fail("MCP não deveria ser chamado"),
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
