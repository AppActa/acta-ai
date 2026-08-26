from __future__ import annotations

from io import BytesIO

from groq import Groq

from config import GROQ_API_KEY

MODEL = "whisper-large-v3-turbo"

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


def transcrever_audio(
    audio: bytes,
    filename: str,
    *,
    language: str = "pt",
) -> str:
    if client is None:
        raise RuntimeError("GROQ_API_KEY não foi configurada.")

    resultado = client.audio.transcriptions.create(
        file=(filename, BytesIO(audio)),
        model=MODEL,
        language=language,
        response_format="json",
        temperature=0.0,
    )

    return resultado.text.strip()