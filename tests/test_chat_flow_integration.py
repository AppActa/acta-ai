"""Conversas completas pela API com usuário/empresa/ciclo de teste 1."""

import json
import os
import subprocess
from uuid import uuid4

import httpx
import pytest
from pymongo import MongoClient

pytestmark = pytest.mark.skipif(
    os.getenv("ACTA_RUN_CHAT_FLOW_INTEGRATION") != "1"
    or not os.getenv("ACTA_FIREBASE_ID_TOKEN"),
    reason="Requer ACTA_FIREBASE_ID_TOKEN, API/MCP e fixtures locais do fluxo completo em Docker.",
)
API = "http://127.0.0.1:8201"
AUTH_HEADERS = {"Authorization": f"Bearer {os.getenv('ACTA_FIREBASE_ID_TOKEN', '')}"}


def chat(question, session=None):
    payload = {
        "message": question, "session_id": session or f"full-chat::{uuid4()}",
        "id_ciclo": [1], "ciclo_ativo": 1,
    }
    response = httpx.post(f"{API}/chat", headers=AUTH_HEADERS, json=payload, timeout=180)
    assert response.status_code == 200, response.text
    answer = response.json()["resposta"]
    print(f"\nSESSÃO: {payload['session_id']}\nPERGUNTA: {question}\nRESPOSTA: {answer}")
    assert answer.strip()
    assert not answer.startswith("[{'type':")
    return answer


def task_snapshot():
    result = subprocess.run([
        "docker", "exec", "acta-chat-flow-test-postgres-1", "psql", "-U", "acta", "-d", "acta", "-Atc",
        "SELECT COALESCE(json_agg(t ORDER BY t.id)::text, '[]') FROM pdca.tarefa t JOIN pdca.plano_acao p ON p.id = t.id_plano_acao WHERE p.id_ciclo = 1;",
    ], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def test_dialogue_requests_missing_data_then_creates_once_and_keeps_history():
    response = httpx.post(
        f"{API}/nova_conversa",
        headers=AUTH_HEADERS,
        json={},
        timeout=15,
    )
    assert response.status_code == 200
    session = response.json()["session_id"]
    title = f"Formulário conversa {uuid4().hex[:8]}"
    with MongoClient("mongodb://localhost:27018", serverSelectionTimeoutMS=5000) as mongo:
        forms = mongo.acta.formularios
        before = forms.count_documents({})
        answer = chat("Quero criar um formulário no ciclo ativo, mas ainda não informei título nem tipo. Pergunte esses dados antes de criar.", session)
        assert "?" in answer
        assert forms.count_documents({}) == before

        chat(f"O título é '{title}', tipo ANALISE_FENOMENO e descrição 'Teste de conversa completa'. Pode criar apenas o rascunho agora.", session)
        assert forms.count_documents({"titulo": title}) == 1
        answer = chat("Qual título eu acabei de pedir para esse formulário?", session)
        assert title.casefold() in answer.casefold()

    history = httpx.get(
        f"{API}/chats/{session}/mensagens",
        headers=AUTH_HEADERS,
        timeout=15,
    )
    assert history.status_code == 200
    messages = history.json()["mensagens"]
    assert len(messages) == 6
    assert sum(m["role"] == "assistente" for m in messages) == 3


def test_missing_task_and_deadline_requests_information_without_writing():
    before = task_snapshot()
    answer = chat("Preciso alterar o prazo de uma tarefa no ciclo ativo, mas ainda não informei qual tarefa nem a nova data. Pergunte o que falta e não altere nada.")
    assert "?" in answer
    assert task_snapshot() == before


def test_complete_task_status_analysis_uses_current_cycle_data():
    expected = len(json.loads(task_snapshot()))
    answer = chat("No ciclo ativo, informe o total de tarefas, separe por status e diga quais estão vencidas. Uma tarefa bloqueada necessariamente está atrasada? Explique usando os dados disponíveis.")
    assert str(expected) in answer or (expected == 4 and "quatro" in answer.casefold())
    assert "bloquead" in answer.casefold()
    assert "mapear processo" in answer.casefold()


def test_goal_target_is_not_reported_as_measured_result():
    answer = chat("No ciclo ativo, qual é a base e o alvo da meta principal? A redução já foi alcançada? Diferencie o alvo planejado de um resultado efetivamente medido.")
    assert "100" in answer and "80" in answer
    assert "não" in answer.casefold()
    assert any(term in answer.casefold() for term in ("medid", "medição", "medicao"))
