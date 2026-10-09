from types import SimpleNamespace

from agents import skill_builder


def test_skill_builder_removes_only_an_outer_markdown_fence(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_builder,
        "llm",
        SimpleNamespace(invoke=lambda _: SimpleNamespace(content="```markdown\n# Skill\n```")),
    )

    assert skill_builder.gerar_markdown_skill("descrição") == "# Skill"


def test_skill_builder_stringifies_non_text_model_output(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_builder,
        "llm",
        SimpleNamespace(invoke=lambda _: SimpleNamespace(content=[{"text": "# Skill"}])),
    )

    assert skill_builder.gerar_markdown_skill("descrição") == "[{'text': '# Skill'}]"
