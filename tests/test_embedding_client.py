from types import SimpleNamespace

import pytest

from agents.helpers import embeddings


def test_embedding_requires_a_gemini_key(monkeypatch) -> None:
    monkeypatch.setattr(embeddings, "GEMINI_API_KEY", None)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        embeddings.gerar_embedding("consulta")


def test_embedding_helper_uses_query_api(monkeypatch) -> None:
    calls = []
    fake = SimpleNamespace(
        embed_query=lambda text, **kwargs: calls.append(("query", text, kwargs)) or [0.1, 0.2],
    )
    monkeypatch.setattr(embeddings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(embeddings, "_embeddings", lambda _key: fake)

    assert embeddings.gerar_embedding("consulta") == [0.1, 0.2]
    assert calls == [("query", "consulta", {"output_dimensionality": 768})]
