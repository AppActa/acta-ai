"""Instâncias compartilhadas do modelo OpenAI usado pelos agentes ACTA."""

from langchain_openai import ChatOpenAI

from config import (
    ACTA_OPENAI_MAX_TOKENS,
    ACTA_OPENAI_MODEL,
    ACTA_OPENAI_REASONING_EFFORT,
    OPENAI_API_KEY,
)

llm = ChatOpenAI(
    model=ACTA_OPENAI_MODEL,
    api_key=OPENAI_API_KEY,
    max_tokens=ACTA_OPENAI_MAX_TOKENS,
    reasoning_effort=ACTA_OPENAI_REASONING_EFFORT,
)
