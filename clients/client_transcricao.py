from __future__ import annotations

from io import BytesIO

from openai import OpenAI

from config import ACTA_OPENAI_TRANSCRIPTION_MODEL, OPENAI_API_KEY

MODEL = ACTA_OPENAI_TRANSCRIPTION_MODEL

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def transcrever_audio(
    audio: bytes,
    filename: str,
    *,
    language: str = "pt",
) -> str:
    if client is None:
        raise RuntimeError("OPENAI_API_KEY não foi configurada.")

    resultado = client.audio.transcriptions.create(
        file=(filename, BytesIO(audio)),
        model=MODEL,
        language=language,
        response_format="json",
        temperature=0.0,
    )

    return resultado.text.strip()
