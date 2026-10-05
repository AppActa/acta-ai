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


class MemoryInput(BaseModel):
    tipo: Literal["preferencia", "ponto_relevante", "decisao", "objetivo"]
    conteudo: str = Field(min_length=1, max_length=2000)
    origem: Literal["explicita", "inferida"] = "explicita"
    confianca: float = Field(default=1.0, ge=0, le=1)
    session_id_origem: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConsentInput(BaseModel):
    modo: Literal["desativado", "somente_explicitas", "automatica"]
    retencao_dias: int | None = Field(default=None, ge=1, le=3650)
