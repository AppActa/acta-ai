"""Requisições reais contra API/MCP e bancos locais de fixtures no Docker."""

import os
from uuid import uuid4

import httpx
import pytest
from pymongo import MongoClient

from clients.mcp_acta_client import call_acta_tool, mcp_request_context

pytestmark = pytest.mark.skipif(
    os.getenv("ACTA_RUN_INTENTION_INTEGRATION") != "1",
    reason="Requer API local :8201, MCP :8001 e fixtures Docker :27018.",
)


def chat(question, session=None):
    response = httpx.post("http://127.0.0.1:8201/chat", json={
        "message": question, "session_id": session or f"intention-test::{uuid4()}",
        "usuario_id": 1, "empresa_id": 1, "id_ciclo": [1], "ciclo_ativo": 1,
    }, timeout=180)
    assert response.status_code == 200, response.text
    answer = response.json()["resposta"]
    print(f"\nPERGUNTA: {question}\nRESPOSTA: {answer}")
    assert answer.strip()
    assert not answer.startswith("[{'type':"), answer
    return answer


def test_live_health_and_validation():
    assert httpx.get("http://127.0.0.1:8201/health").status_code == 200
    assert httpx.post("http://127.0.0.1:8201/chat", json={}).status_code == 422


@pytest.mark.parametrize("question,terms", [
    ("O que é o PDCA e quais são suas etapas?", ["plan", "check"]),
    ("Quais tarefas estão atrasadas no ciclo ativo?", ["mapear processo"]),
    ("Qual é a meta principal do ciclo ativo? Informe base e alvo.", ["100", "80"]),
    ("Resuma as respostas dos formulários do ciclo ativo.", ["retrabalho"]),
])
def test_live_read_questions(question, terms):
    answer = chat(question).casefold()
    assert all(term in answer for term in terms), answer


def test_live_write_creates_one_draft_in_fixture_database():
    title = f"Validação intenção {uuid4().hex[:10]}"
    with MongoClient("mongodb://localhost:27018", serverSelectionTimeoutMS=5000) as mongo:
        collection = mongo["acta"]["formularios"]
        assert collection.count_documents({"titulo": title}) == 0
        chat(f"Crie apenas um formulário em rascunho no ciclo ativo, com título '{title}', tipo ANALISE_FENOMENO e descrição 'Teste local de validação de intenção'.")
        assert collection.count_documents({"titulo": title}) == 1


def test_live_incomplete_write_requests_information_without_creating():
    with MongoClient("mongodb://localhost:27018", serverSelectionTimeoutMS=5000) as mongo:
        collection = mongo["acta"]["formularios"]
        before = collection.count_documents({})
        answer = chat("Crie um formulário no ciclo ativo. Ainda não defini título nem tipo; pergunte esses dados antes de criar.")
        assert "?" in answer, answer
        assert collection.count_documents({}) == before


def test_live_sql_task_creation_and_status_update(monkeypatch):
    monkeypatch.setenv("ACTA_MCP_URL", "http://127.0.0.1:8001/mcp")
    title = f"Tarefa intenção {uuid4().hex[:10]}"
    chat(f"Crie uma tarefa no ciclo ativo, no plano de ação Padronizar processo (ID 1), responsável Bruno Analista (ID 2), título '{title}', descrição 'Teste local de transação', prazo 31/12/2026, prioridade MEDIA.")
    with mcp_request_context(usuario_id=1, empresa_id=1):
        result = call_acta_tool("tarefas_consultar", {"id_ciclo": 1, "limit": 100})
    tasks = [task for task in result["tarefas"] if task["titulo"] == title]
    assert len(tasks) == 1, result
    task_id = tasks[0]["id"]
    chat(f"Atualize apenas o status da tarefa '{title}' (ID {task_id}) do ciclo ativo para EM_ANDAMENTO.")
    with mcp_request_context(usuario_id=1, empresa_id=1):
        updated = call_acta_tool("tarefas_detalhes", {"id_ciclo": 1, "id_tarefa": task_id})
    assert updated["tarefa"]["status"] == "EM_ANDAMENTO", updated
