import asyncio
import threading

import pytest
from langchain_core.messages import HumanMessage

import agents.guardrail as guardrail_module
import agents.helpers.estado as state_module
import clients.mcp_acta_client as mcp_client
from agents.helpers.estado import rotear_deterministicamente
from clients.mcp_acta_client import mcp_request_context


def _state(*specialists: str) -> dict:
    return {
        "messages": [HumanMessage(content="Pergunta de teste")],
        "agentes_chamados": [],
        "rota": "especialistas",
        "especialistas": list(specialists),
        "respostas_especialistas": [],
        "mapa_pii": {},
        "session_id": "optimization::test",
        "id_ciclo": 1,
        "contexto_memoria": "",
        "resposta_final": "",
        "latencias_ms": {},
    }


def test_specialists_run_in_parallel_and_keep_mcp_context(monkeypatch) -> None:
    monkeypatch.setenv("ACTA_ENFORCE_SPECIALIST_TOOL", "false")
    barrier = threading.Barrier(2, timeout=1)

    def executor(_estado: dict) -> str:
        context = mcp_client._current_context()
        barrier.wait()
        return f"{context.usuario_id}:{context.empresa_id}:{context.trace_id}"

    monkeypatch.setattr(
        state_module,
        "REGISTRO_ESPECIALISTAS",
        {"primeiro": executor, "segundo": executor},
    )

    with mcp_request_context(
        usuario_id=7,
        empresa_id=9,
        trace_id="trace-paralelo",
    ):
        responses, called = state_module.executar_especialistas(_state("primeiro", "segundo"))

    assert called == ["primeiro", "segundo"]
    assert [item["especialista"] for item in responses] == called
    assert {item["resposta"] for item in responses} == {"7:9:trace-paralelo"}


def test_specialist_without_tool_call_gets_verified_evidence(monkeypatch) -> None:
    class Formatter:
        def invoke(self, _prompt: str) -> HumanMessage:
            return HumanMessage(content="A meta está em andamento com dados confirmados.")

    monkeypatch.setenv("ACTA_ENFORCE_SPECIALIST_TOOL", "true")
    monkeypatch.setattr(
        state_module,
        "REGISTRO_ESPECIALISTAS",
        {"indicadores": lambda _estado: "Vou consultar os dados."},
    )
    monkeypatch.setattr(state_module, "llm_fast", Formatter())
    monkeypatch.setattr(
        mcp_client,
        "_run_async_in_sync_context",
        lambda tool_name, arguments: {
            "status": "ok",
            "tool_recebida": tool_name,
            "id_ciclo": arguments["id_ciclo"],
        },
    )

    with mcp_request_context(usuario_id=1, empresa_id=1):
        responses, called = state_module.executar_especialistas(_state("indicadores"))

    assert called == ["indicadores"]
    assert responses[0]["resposta"] == "A meta está em andamento com dados confirmados."
    assert responses[0]["evidencias"][0]["tool"] == "predicoes_atingimento_meta"


def test_indicators_are_formatted_from_confirmed_tool_evidence(monkeypatch) -> None:
    monkeypatch.setenv("ACTA_ENFORCE_SPECIALIST_TOOL", "true")

    def specialist(_estado: dict) -> str:
        state_module.call_acta_tool("predicoes_atingimento_meta", {"id_ciclo": 1})
        return "Meta 1 atingida, diferenca absoluta 5591 e variacao 8,02%."

    monkeypatch.setattr(
        state_module,
        "REGISTRO_ESPECIALISTAS",
        {"indicadores": specialist},
    )
    monkeypatch.setattr(
        mcp_client,
        "_run_async_in_sync_context",
        lambda _tool_name, _arguments: {
            "status": "ok",
            "id_ciclo": 1,
            "metas": [
                {
                    "id_meta": 1,
                    "objetivo": "Reduzir refugo",
                    "status_atual": "ATINGIDA",
                    "valor_base": 18.0,
                    "valor_alvo": 5.0,
                    "unidade": "%",
                }
            ],
        },
    )

    with mcp_request_context(usuario_id=1, empresa_id=1):
        responses, called = state_module.executar_especialistas(_state("indicadores"))

    assert called == ["indicadores"]
    assert "diferenca absoluta" not in responses[0]["resposta"].lower()
    assert "Meta 1: Reduzir refugo" in responses[0]["resposta"]
    assert responses[0]["evidencias"][0]["tool"] == "predicoes_atingimento_meta"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("O que é o ACTA?", ["rag"]),
        ("Como funciona o Ishikawa?", ["rag"]),
        ("Mostre o Ishikawa do ciclo 1", ["ciclo"]),
        ("Resuma as respostas dos formulários do ciclo 1", ["formularios"]),
        ("Quais padrões aparecem nas respostas dos colaboradores?", ["formularios"]),
        ("Quais causas foram mais citadas no Ishikawa?", ["formularios"]),
        ("Como funciona um formulário do ACTA?", ["rag"]),
        ("Como funciona um relatório do ACTA?", ["rag"]),
        ("Gere um resumo executivo do ciclo 1", ["relatorios"]),
        ("Mostre o relatório mais recente do ciclo 1", ["relatorios"]),
        ("Prepare um texto para PPTX do ciclo 1", ["relatorios"]),
        ("Qual a probabilidade de a tarefa 1 atrasar?", ["predicoes"]),
        ("Faça uma previsão de conclusão do ciclo 1", ["predicoes"]),
        ("Detecte respostas atípicas do formulário f-1", ["predicoes"]),
        ("Qual a chance de atingirmos a meta do ciclo 1?", ["predicoes"]),
        ("A meta principal foi atingida no ciclo 1?", ["indicadores"]),
        ("Qual foi a variação percentual do indicador principal?", ["indicadores"]),
        (
            "Crie um relatório da fase Check com foco nos indicadores.",
            ["relatorios", "indicadores"],
        ),
        (
            "Gere um relatório executivo com a previsão de atraso do ciclo 1",
            ["relatorios", "predicoes"],
        ),
        ("Como funciona uma previsão no ACTA?", ["rag"]),
        ("Quais tarefas estão atrasadas no ciclo 1?", ["tarefas"]),
        (
            "Quais tarefas estão atrasadas e quais colaboradores podem assumi-las?",
            ["tarefas", "colaboradores"],
        ),
        ("Qual é a situação do ciclo?", ["ciclo"]),
        ("Bom dia", []),
    ],
)
def test_deterministic_router(question: str, expected: list[str]) -> None:
    assert rotear_deterministicamente(question) == expected


def test_mcp_cache_is_limited_to_request_context(monkeypatch) -> None:
    calls = []

    def fake_call(tool_name: str, arguments: dict) -> dict:
        calls.append((tool_name, arguments))
        return {"status": "ok", "numero": len(calls)}

    monkeypatch.setattr(mcp_client, "_run_async_in_sync_context", fake_call)

    with mcp_request_context(usuario_id=1, empresa_id=1):
        first = mcp_client.call_acta_tool("tool_teste", {"b": 2, "a": 1})
        second = mcp_client.call_acta_tool("tool_teste", {"a": 1, "b": 2})

    with mcp_request_context(usuario_id=1, empresa_id=1):
        third = mcp_client.call_acta_tool("tool_teste", {"a": 1, "b": 2})

    assert first == second == {"status": "ok", "numero": 1}
    assert third == {"status": "ok", "numero": 2}
    assert len(calls) == 2


def test_mcp_records_real_and_cached_tool_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_run_async_in_sync_context",
        lambda tool_name, arguments: {
            "status": "ok",
            "tool_recebida": tool_name,
            "argumentos_recebidos": arguments,
        },
    )

    with (
        mcp_request_context(usuario_id=1, empresa_id=1),
        mcp_client.mcp_tool_evidence_context() as evidence,
    ):
        mcp_client.call_acta_tool("tool_teste", {"id_ciclo": 1})
        mcp_client.call_acta_tool("tool_teste", {"id_ciclo": 1})

    assert len(evidence) == 2
    assert evidence[0]["cache"] is False
    assert evidence[1]["cache"] is True
    assert evidence[0]["resultado"]["status"] == "ok"


def test_mcp_retries_only_transient_failures(monkeypatch) -> None:
    calls = 0

    async def temporary_failure(_tool_name: str, _arguments: dict) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("timeout")
        return {"status": "ok"}

    monkeypatch.setenv("ACTA_MCP_MAX_ATTEMPTS", "2")
    monkeypatch.setattr(mcp_client, "_call_tool_once", temporary_failure)

    assert asyncio.run(mcp_client._call_tool_async("tool_teste", {})) == {"status": "ok"}
    assert calls == 2


def test_mcp_detects_transient_failure_inside_exception_group() -> None:
    error = ExceptionGroup("task group", [TimeoutError("timeout")])

    assert mcp_client._is_transient_error(error) is True


def test_mcp_does_not_retry_non_transient_failures(monkeypatch) -> None:
    calls = 0

    async def permanent_failure(_tool_name: str, _arguments: dict) -> dict:
        nonlocal calls
        calls += 1
        raise ValueError("argumento inválido")

    monkeypatch.setenv("ACTA_MCP_MAX_ATTEMPTS", "3")
    monkeypatch.setattr(mcp_client, "_call_tool_once", permanent_failure)

    with pytest.raises(mcp_client.MCPActaError, match="argumento inválido"):
        asyncio.run(mcp_client._call_tool_async("tool_teste", {}))
    assert calls == 1


def test_output_guardrail_skips_optional_llm_review(monkeypatch) -> None:
    class UnexpectedLLM:
        def invoke(self, _prompt: str):
            raise AssertionError("A LLM de saída não deveria ser chamada")

    monkeypatch.setattr(guardrail_module, "LLM_OUTPUT_REVIEW", False)
    monkeypatch.setattr(guardrail_module, "llm", UnexpectedLLM())

    result = guardrail_module.guardrail_saida(
        "Contato: gestor@acta.com",
        {},
    )

    assert result["mensagem"] == "Contato: [EMAIL OMITIDO]"


def test_orchestrator_removes_task_reallocation_section_when_collaborator_exists() -> None:
    answer = (
        "### Tarefas atrasadas\nUma tarefa está atrasada.\n\n"
        "### Sobre a realocação\nQuem deve assumir é outra análise."
    )

    scoped = state_module._limitar_resposta_ao_dominio(
        "tarefas",
        answer,
        ["tarefas", "colaboradores"],
    )

    assert "Uma tarefa está atrasada" in scoped
    assert "realocação" not in scoped
