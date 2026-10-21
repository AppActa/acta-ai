from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SessionInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("session_id")
    @classmethod
    def clean_session_id(_cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("session_id é obrigatório.")
        return value


class MessageInput(SessionInput):
    role: Literal["usuario", "assistente", "sistema", "ferramenta"]
    content: str = Field(min_length=1, max_length=8000)
    agent: str | None = Field(default=None, max_length=100)


