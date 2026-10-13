import os
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from agents.estado import executar_especialistas
from clients.mcp_acta_client import mcp_request_context


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").lower() in {"1", "true", "yes", "y", "on"}

SPECIALIST_CASES = [
    ("rag", "Explique objetivamente o que é o ACTA e como ele usa o PDCA."),
    ("ciclo", "Qual é a situação geral do ciclo 1? Use os dados disponíveis."),
    ("licoes", "O que aprendemos no ciclo 1?"),
    ("tarefas", "Quais tarefas estão atrasadas no ciclo 1?"),
    ("colaboradores", "Quem participa do ciclo 1 e como está a carga de trabalho?"),
    ("formularios", "Resuma as respostas dos formulários do ciclo 1 e destaque padrões."),
    ("indicadores", "A meta principal do ciclo 1 foi atingida? Compare base e alvo."),
    ("relatorios", "Gere um resumo executivo do ciclo 1 com riscos e próximos passos."),
]

EXPECTED_TERMS = {
    "rag": ("acta", "pdca"),
    "ciclo": ("ciclo", "fase", "status"),
    "licoes": ("liç", "evidên"),
    "tarefas": ("tarefa", "atras"),
    "colaboradores": ("colaborador", "participante", "equipe", "responsável"),
    "formularios": ("formulário", "resposta", "padrão", "sintoma"),
    "indicadores": ("meta", "indicador", "base", "alvo", "ating"),
    "relatorios": ("resumo", "ciclo", "risco", "executivo"),
}

pytestmark = pytest.mark.skipif(
    not _enabled("ACTA_RUN_SPECIALISTS_INTEGRATION"),
    reason="Defina ACTA_RUN_SPECIALISTS_INTEGRATION=1 com MCP, bancos e OPENAI_API_KEY ativos.",
)


@pytest.mark.parametrize(("specialist", "question"), SPECIALIST_CASES)
def test_specialist_returns_real_answer(specialist: str, question: str) -> None:
    state = {
        "messages": [HumanMessage(content=question)],
        "rota": "especialistas",
        "especialistas": [specialist],
        "respostas_especialistas": [],
        "mapa_pii": {},
        "session_id": f"integration::{specialist}::{uuid4()}",
        "id_ciclo": 1,
        "contexto_memoria": "",
        "resposta_final": "",
    }

    with mcp_request_context(usuario_id=1, empresa_id=1):
        responses = executar_especialistas(state)

    assert [item["especialista"] for item in responses] == [specialist]
    assert len(responses) == 1
    answer = responses[0]["resposta"].strip()
    assert len(answer) > 20
    assert "Não foi possível consultar este domínio no momento." not in answer
    assert "Não consegui consultar a base de conhecimento" not in answer
    assert "erro interno" not in answer.lower()
    assert responses[0]["evidencias"], f"{specialist} não executou nenhuma tool MCP."
    assert all(
        not (
            isinstance(item.get("resultado"), dict)
            and item["resultado"].get("status") == "error"
        )
        for item in responses[0]["evidencias"]
    )
    assert not any(
        marker in answer.lower()
        for marker in ("vou executar", "vou consultar", "chamando", "ciclo_visao_geral")
    )
    assert any(term in answer.lower() for term in EXPECTED_TERMS[specialist]), (
        f"Resposta de {specialist} fora do domínio esperado: {answer}"
    )


def test_multiple_specialists_return_real_answers() -> None:
    specialists = ["ciclo", "tarefas"]
    state = {
        "messages": [
            HumanMessage(content="Qual é a situação do ciclo 1 e quais tarefas estão atrasadas?")
        ],
        "rota": "especialistas",
        "especialistas": specialists,
        "respostas_especialistas": [],
        "mapa_pii": {},
        "session_id": f"integration::multiple::{uuid4()}",
        "id_ciclo": 1,
        "contexto_memoria": "",
        "resposta_final": "",
    }

    with mcp_request_context(usuario_id=1, empresa_id=1):
        responses = executar_especialistas(state)

    assert [item["especialista"] for item in responses] == specialists
    assert all(item["resposta"].strip() for item in responses)
    assert all(item["evidencias"] for item in responses)
    assert all(
        evidence.get("resultado", {}).get("status") != "error"
        for item in responses
        for evidence in item["evidencias"]
    )
