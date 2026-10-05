from types import SimpleNamespace

import pytest

from agents.helpers import embeddings


def test_embedding_requires_a_gemini_key(monkeypatch) -> None:
    monkeypatch.setattr(embeddings, "GEMINI_API_KEY", None)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        embeddings.gerar_embedding("consulta")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        embeddings.gerar_embeddings_batch(["mensagem"])


def test_embedding_helpers_use_query_and_batch_apis(monkeypatch) -> None:
    calls = []
    fake = SimpleNamespace(
        embed_query=lambda text, **kwargs: calls.append(("query", text, kwargs)) or [0.1, 0.2],
        embed_documents=lambda texts, **kwargs: calls.append(("batch", texts, kwargs))
        or [[0.3, 0.4]],
    )
    monkeypatch.setattr(embeddings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(embeddings, "_embeddings", lambda _key: fake)

    assert embeddings.gerar_embedding("consulta") == [0.1, 0.2]
    assert embeddings.gerar_embeddings_batch(["texto"]) == [[0.3, 0.4]]
    assert embeddings.gerar_embeddings_batch([]) == []
    assert calls == [
        ("query", "consulta", {"output_dimensionality": 768}),
        ("batch", ["texto"], {"output_dimensionality": 768}),
    ]
