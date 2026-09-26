from types import SimpleNamespace

import pytest

from clients import client_transcricao


def test_transcription_requires_groq_client(monkeypatch) -> None:
    monkeypatch.setattr(client_transcricao, "client", None)

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        client_transcricao.transcrever_audio(b"audio", "fala.webm")


def test_transcription_returns_trimmed_provider_text(monkeypatch) -> None:
    calls = []
    fake_client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(
                create=lambda **kwargs: calls.append(kwargs) or SimpleNamespace(text="  texto transcrito  ")
            )
        )
    )
    monkeypatch.setattr(client_transcricao, "client", fake_client)

    assert client_transcricao.transcrever_audio(b"audio", "fala.webm", language="en") == (
        "texto transcrito"
    )
    assert calls[0]["language"] == "en"
