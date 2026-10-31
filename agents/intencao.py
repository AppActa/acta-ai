"""Contratos de proposta e decisão antes de qualquer ação de domínio."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

APOIO_MINIMO = 0.7
MAX_ACOES_ESPECIALISTA = 10
MENSAGEM_BLOQUEIO = "Não foi possível validar a ação solicitada com segurança. Nenhuma nova ação foi executada."


class Intention(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    tool: str = Field(min_length=1, pattern=r"^\S+$")
    argumentos: dict[str, Any]


class AvaliacaoIntencao(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    decisao: Literal["aprovada", "corrigir_proposta", "pedir_esclarecimento"]
    apoio: float = Field(ge=0, le=1, allow_inf_nan=False)
    motivo: str = Field(min_length=1, pattern=r"\S")
    pergunta: str | None

    @model_validator(mode="after")
    def validar_pergunta(self):
        if self.decisao == "pedir_esclarecimento":
            if not self.pergunta or not self.pergunta.strip():
                raise ValueError("Esclarecimento exige pergunta.")
        elif self.pergunta is not None:
            raise ValueError("Somente esclarecimento pode conter pergunta.")

        return self


class ExecucaoBloqueada(RuntimeError):
    """Interrompe a rodada sem executar novas ações."""


class EsclarecimentoNecessario(ExecucaoBloqueada):
    """Carrega a pergunta que deve ser entregue ao usuário."""
