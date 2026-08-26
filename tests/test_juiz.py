from langchain_core.messages import AIMessage

import agents.juiz as judge_module


class FakeJudge:
    def __init__(self, content: str | Exception) -> None:
        self.content = content
        self.calls = []

    def invoke(self, payload: dict) -> dict:
        self.calls.append(payload)
        if isinstance(self.content, Exception):
            raise self.content
        return {"messages": [AIMessage(content=self.content)]}


def _evaluate(monkeypatch, judge_response: str | Exception, orchestrator: str) -> dict:
    monkeypatch.setenv("ACTA_JUDGE_LLM", "true")
    fake = FakeJudge(judge_response)
    monkeypatch.setattr(judge_module, "juiz", fake)
    return judge_module.avaliar_resposta(
        pergunta="Quantas tarefas estão atrasadas?",
        respostas_especialistas=[
            {"especialista": "tarefas", "resposta": "Existem 10 tarefas atrasadas."}
        ],
        evidencias_tools=[
            {
                "tool": "tarefas_consultar",
                "argumentos": {"id_ciclo": 1},
                "resultado": {"status": "ok", "tarefas_atrasadas": 10},
                "cache": False,
            }
        ],
        resposta_orquestrador=orchestrator,
    )


def test_judge_approves_grounded_answer(monkeypatch) -> None:
    result = _evaluate(
        monkeypatch,
        '{"status":"APROVADO","problemas":[],"resposta_corrigida":""}',
        "Existem 10 tarefas atrasadas.",
    )

    assert result == {
        "status": "APROVADO",
        "problemas": [],
        "resposta": "Existem 10 tarefas atrasadas.",
    }


def test_judge_corrects_unsupported_number(monkeypatch) -> None:
    result = _evaluate(
        monkeypatch,
        (
            '{"status":"CORRIGIDO","problemas":["quantidade incorreta"],'
            '"resposta_corrigida":"Existem 10 tarefas atrasadas."}'
        ),
        "Existem 20 tarefas atrasadas.",
    )

    assert result["status"] == "CORRIGIDO"
    assert result["resposta"] == "Existem 10 tarefas atrasadas."
    assert any("20" in problem for problem in result["problemas"])


def test_judge_rejects_correction_that_is_still_unsupported(monkeypatch) -> None:
    result = _evaluate(
        monkeypatch,
        (
            '{"status":"CORRIGIDO","problemas":[],'
            '"resposta_corrigida":"Existem 30 tarefas atrasadas."}'
        ),
        "Existem 20 tarefas atrasadas.",
    )

    assert result["status"] == "SUBSTITUIDO"
    assert "10 tarefas atrasadas" in result["resposta"]


def test_judge_failure_uses_specialist_answer(monkeypatch) -> None:
    result = _evaluate(
        monkeypatch,
        RuntimeError("modelo indisponível"),
        "Existem 10 tarefas atrasadas.",
    )

    assert result["status"] == "SUBSTITUIDO"
    assert "10 tarefas atrasadas" in result["resposta"]
    assert any("não pôde concluir" in problem for problem in result["problemas"])


def test_deterministic_mode_blocks_internal_details(monkeypatch) -> None:
    monkeypatch.setenv("ACTA_JUDGE_LLM", "false")

    result = judge_module.avaliar_resposta(
        pergunta="Qual é o resultado?",
        respostas_especialistas=[
            {"especialista": "ciclo", "resposta": "O ciclo está em andamento."}
        ],
        evidencias_tools=[
            {
                "tool": "ciclo_visao_geral",
                "argumentos": {"id_ciclo": 1},
                "resultado": {"status": "ok", "situacao": "em andamento"},
                "cache": False,
            }
        ],
        resposta_orquestrador="O agente consultou uma tool e o ciclo está em andamento.",
    )

    assert result["status"] == "SUBSTITUIDO"
    assert result["resposta"] == "O ciclo está em andamento."


def test_fallback_never_returns_a_narrated_tool_call(monkeypatch) -> None:
    monkeypatch.setenv("ACTA_JUDGE_LLM", "false")

    result = judge_module.avaliar_resposta(
        pergunta="A meta foi atingida no ciclo 1?",
        respostas_especialistas=[
            {
                "especialista": "indicadores",
                "resposta": "Vou executar a ferramenta ciclo_visao_geral para verificar.",
            }
        ],
        evidencias_tools=[],
        resposta_orquestrador="Chamando ciclo_visao_geral agora.",
    )

    assert result["status"] == "SUBSTITUIDO"
    assert result["resposta"] == (
        "Não foi possível validar a resposta com segurança usando os dados disponíveis."
    )
    assert "ciclo_visao_geral" not in result["resposta"]


def test_percentage_unit_from_evidence_is_supported(monkeypatch) -> None:
    monkeypatch.setenv("ACTA_JUDGE_LLM", "false")

    result = judge_module.avaliar_resposta(
        pergunta="Qual é o valor base?",
        respostas_especialistas=[
            {"especialista": "indicadores", "resposta": "O valor base é 18%."}
        ],
        evidencias_tools=[
            {
                "tool": "predicoes_atingimento_meta",
                "argumentos": {"id_ciclo": 1},
                "resultado": {"valor_base": 18.0, "unidade": "%"},
                "cache": False,
            }
        ],
        resposta_orquestrador="O valor base é 18%.",
    )

    assert result["status"] == "APROVADO"
    assert result["resposta"] == "O valor base é 18%."


def test_generated_timestamp_is_removed_without_rejecting_grounded_answer(monkeypatch) -> None:
    monkeypatch.setenv("ACTA_JUDGE_LLM", "false")

    result = judge_module.avaliar_resposta(
        pergunta="Quantas tarefas estão atrasadas?",
        respostas_especialistas=[
            {"especialista": "tarefas", "resposta": "Existem 3 tarefas atrasadas."}
        ],
        evidencias_tools=[
            {
                "tool": "tarefas_atrasadas",
                "argumentos": {"id_ciclo": 1},
                "resultado": {
                    "status": "ok",
                    "id_ciclo": 1,
                    "count": 3,
                    "tarefas": [],
                },
                "cache": False,
            }
        ],
        resposta_orquestrador=(
            "Existem 3 tarefas atrasadas. Atualizado em 22/08/2026 às 14:33."
        ),
    )

    assert result["status"] == "APROVADO"
    assert "14:33" not in result["resposta"]


def test_fallback_is_generic_without_structured_evidence(monkeypatch) -> None:
    monkeypatch.setenv("ACTA_JUDGE_LLM", "false")

    result = judge_module.avaliar_resposta(
        pergunta="Quantas tarefas estão atrasadas?",
        respostas_especialistas=[],
        evidencias_tools=[
            {
                "tool": "tarefas_atrasadas",
                "argumentos": {"id_ciclo": 1},
                "resultado": {
                    "status": "ok",
                    "id_ciclo": 1,
                    "count": 3,
                    "tarefas": [],
                },
                "cache": False,
            }
        ],
        resposta_orquestrador="Existem 20 tarefas atrasadas.",
    )

    assert result["status"] == "SUBSTITUIDO"
    assert result["resposta"] == (
        "Não foi possível validar a resposta com segurança usando os dados disponíveis."
    )
