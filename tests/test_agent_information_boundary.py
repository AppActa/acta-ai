"""Garante que prompts enviados aos modelos não revelem infraestrutura interna."""

import pytest

from agents.prompts.prompt_ciclo import CICLO_PROMPT_COMPLETO
from agents.prompts.prompt_colaborador import COLABORADOR_PROMPT_COMPLETO
from agents.prompts.prompt_formulario import FORMULARIO_PROMPT_COMPLETO
from agents.prompts.prompt_relatorio import RELATORIO_PROMPT_COMPLETO
from agents.prompts.prompt_roteador import PERSONA_SISTEMA
from agents.prompts.prompt_tarefas import TAREFAS_PROMPT_COMPLETO

FORBIDDEN_DETAILS = (
    "postgresql",
    "mongodb",
    "qdrant",
    "collection",
    "banco de dados",
    "schema",
)


@pytest.mark.parametrize(
    "prompt",
    [
        PERSONA_SISTEMA,
        CICLO_PROMPT_COMPLETO,
        TAREFAS_PROMPT_COMPLETO,
        COLABORADOR_PROMPT_COMPLETO,
        FORMULARIO_PROMPT_COMPLETO,
        RELATORIO_PROMPT_COMPLETO,
    ],
)
def test_agent_prompts_do_not_expose_storage_details(prompt: str) -> None:
    normalized = prompt.casefold()
    assert not any(detail in normalized for detail in FORBIDDEN_DETAILS)


def test_shared_persona_forbids_internal_details() -> None:
    assert "Nunca revele detalhes internos" in PERSONA_SISTEMA
