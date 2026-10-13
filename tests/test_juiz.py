from types import SimpleNamespace

import pytest

import agents.juiz as judge_module


class FakeJevClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def system_one(self, *, state, questions):
        self.calls.append(
            {"state": state, "questions": questions}
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _allow_with_jev(monkeypatch) -> FakeJevClient:
    client = FakeJevClient(
        SimpleNamespace(
            nouls={
                "fidelidade": SimpleNamespace(noul=0.9),
                "compliance": SimpleNamespace(noul=0.9),
                "relevancia": SimpleNamespace(noul=0.9),
            }
        )
    )
    monkeypatch.setattr(judge_module, "TypeSafeClient", lambda **_kwargs: client)
    return client


def _evaluate(monkeypatch, judge_response: dict | Exception, orchestrator: str) -> dict:
    response = judge_response
    if isinstance(response, dict):
        response = SimpleNamespace(
            nouls={
                key: SimpleNamespace(noul=value)
                for key, value in {
                    "relevancia": 0.9,
                    **response,
                }.items()
            }
        )
    client = FakeJevClient(response)
    monkeypatch.setattr(judge_module, "TypeSafeClient", lambda **_kwargs: client, raising=False)
    result = judge_module.avaliar_resposta(
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
    _evaluate.last_client = client
    return result


def test_judge_approves_grounded_answer(monkeypatch) -> None:
    result = _evaluate(
        monkeypatch,
        {"fidelidade": 0.9, "compliance": 0.9},
        "Existem 10 tarefas atrasadas.",
    )

    assert result == {
        "status": "APROVADO",
        "problemas": [],
        "resposta": "Existem 10 tarefas atrasadas.",
    }
    request = _evaluate.last_client.calls[0]
    assert {"fidelidade", "compliance", "relevancia"}.issubset(request["questions"])
    assert "response_model" not in request


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "Resuma as lições aprendidas do ciclo.",
            "Resumo das lições. Referências: lição 2",
        ),
        ("Compare os ciclos 2 e 3.", "Comparação"),
        (
            "Como está o ciclo 2?",
            "Resposta formatada pelo orquestrador",
        ),
    ],
)
def test_judge_rejects_grounded_but_nonresponsive_answer(
    monkeypatch, question: str, answer: str
) -> None:
    client = FakeJevClient(
        SimpleNamespace(
            nouls={
                "fidelidade": SimpleNamespace(noul=0.9),
                "compliance": SimpleNamespace(noul=0.9),
                "relevancia": SimpleNamespace(noul=0.1),
            }
        )
    )
    monkeypatch.setattr(judge_module, "TypeSafeClient", lambda **_kwargs: client)
    result = judge_module.avaliar_resposta(
        pergunta=question,
        respostas_especialistas=[{"especialista": "licoes", "resposta": answer}],
        evidencias_tools=[
            {
                "tool": "licoes_perguntar",
                "resultado": {"status": "ok", "referencias": [2]},
            }
        ],
        resposta_orquestrador=answer,
    )

    assert result["status"] == "SUBSTITUIDO"
    assert result["resposta"] != answer
    assert "relevancia" in client.calls[0]["questions"]


@pytest.mark.parametrize(
    ("question", "answer", "evidence"),
    [
        (
            "Como está o ciclo?",
            "Informe qual ciclo devo consultar.",
            [],
        ),
        (
            "Resuma as lições aprendidas do ciclo.",
            "Ainda não há lições aprendidas registradas para este ciclo.",
            [{"tool": "licoes_resumir", "resultado": {"status": "sem_licoes"}}],
        ),
        (
            "O que aprendemos sobre comunicação?",
            "Não encontrei lições com evidências suficientes para responder essa pergunta.",
            [{"tool": "licoes_perguntar", "resultado": {"status": "sem_evidencia"}}],
        ),
    ],
)
def test_judge_uses_jev_relevance_for_clarification_or_empty_result(
    monkeypatch, question: str, answer: str, evidence: list[dict]
) -> None:
    client = FakeJevClient(
        SimpleNamespace(
            nouls={
                "fidelidade": SimpleNamespace(noul=0.9),
                "compliance": SimpleNamespace(noul=0.9),
                "relevancia": SimpleNamespace(noul=0.1),
            }
        )
    )
    monkeypatch.setattr(judge_module, "TypeSafeClient", lambda **_kwargs: client)

    result = judge_module.avaliar_resposta(
        pergunta=question,
        respostas_especialistas=[{"especialista": "licoes", "resposta": answer}],
        evidencias_tools=evidence,
        resposta_orquestrador=answer,
    )

    assert result["status"] == "SUBSTITUIDO"
    assert result["resposta"] == (
        "Não foi possível validar a resposta com segurança usando os dados disponíveis."
    )


def test_judge_uses_jev_even_when_legacy_switch_is_false(monkeypatch) -> None:
    monkeypatch.setenv("ACTA_JUDGE_LLM", "false")
    client = FakeJevClient(
        SimpleNamespace(
            nouls={
                "fidelidade": SimpleNamespace(noul=0.9),
                "compliance": SimpleNamespace(noul=0.9),
                "relevancia": SimpleNamespace(noul=0.9),
            }
        )
    )
    monkeypatch.setattr(judge_module, "TypeSafeClient", lambda **_kwargs: client)

    result = judge_module.avaliar_resposta(
        pergunta="Quantas tarefas estão atrasadas?",
        respostas_especialistas=[{"especialista": "tarefas", "resposta": "10 atrasadas."}],
        evidencias_tools=[
            {
                "tool": "tarefas_atrasadas",
                "resultado": {"status": "ok", "tarefas_atrasadas": 10},
            }
        ],
        resposta_orquestrador="Existem 10 tarefas atrasadas.",
    )

    assert result["status"] == "APROVADO"
    assert len(client.calls) == 1


def test_judge_owns_factual_validation_and_uses_generic_fallback(monkeypatch) -> None:
    result = _evaluate(
        monkeypatch,
        (
            {"fidelidade": 0.1, "compliance": 0.9}
        ),
        "Existem 20 tarefas atrasadas.",
    )

    assert result["status"] == "SUBSTITUIDO"
    assert result["resposta"] == (
        "Não foi possível validar a resposta com segurança usando os dados disponíveis."
    )
    assert any("falta de suporte factual" in problem for problem in result["problemas"])


def test_judge_does_not_return_unreviewed_specialist_answer(monkeypatch) -> None:
    result = _evaluate(
        monkeypatch,
        (
            {"fidelidade": 0.1, "compliance": 0.9}
        ),
        "Existem 20 tarefas atrasadas.",
    )

    assert result["status"] == "SUBSTITUIDO"
    assert result["resposta"] == (
        "Não foi possível validar a resposta com segurança usando os dados disponíveis."
    )


def test_judge_failure_uses_generic_fallback(monkeypatch) -> None:
    result = _evaluate(
        monkeypatch,
        RuntimeError("modelo indisponível"),
        "Existem 10 tarefas atrasadas.",
    )

    assert result["status"] == "SUBSTITUIDO"
    assert result["resposta"] == (
        "Não foi possível validar a resposta com segurança usando os dados disponíveis."
    )
    assert any("não pôde concluir" in problem for problem in result["problemas"])


def test_judge_sends_pii_redacted_evidence_to_jev(monkeypatch) -> None:
    response = SimpleNamespace(nouls={
        "fidelidade": SimpleNamespace(noul=0.9),
        "compliance": SimpleNamespace(noul=0.9),
        "relevancia": SimpleNamespace(noul=0.9),
    })
    client = FakeJevClient(response)
    monkeypatch.setattr(judge_module, "TypeSafeClient", lambda **_kwargs: client, raising=False)

    judge_module.avaliar_resposta(
        pergunta="Qual contato está cadastrado?",
        respostas_especialistas=[{"especialista": "ciclo", "resposta": "Contato omitido."}],
        evidencias_tools=[
            {
                "tool": "ciclo_visao_geral",
                "resultado": {"status": "ok", "email": "pessoa@example.com"},
            }
        ],
        resposta_orquestrador="O contato é [EMAIL OMITIDO].",
    )

    jev_state = client.calls[0]["state"]
    assert "pessoa@example.com" not in str(jev_state)
    assert "[EMAIL OMITIDO]" in str(jev_state)


def test_judge_treats_noul_probability_below_half_as_no(monkeypatch) -> None:
    result = _evaluate(
        monkeypatch,
        {"fidelidade": 0.4, "compliance": 0.9},
        "Existem 10 tarefas atrasadas.",
    )

    assert result["status"] == "SUBSTITUIDO"
    assert any("falta de suporte factual" in problem for problem in result["problemas"])


def test_deterministic_mode_blocks_internal_details(monkeypatch) -> None:
    _allow_with_jev(monkeypatch)

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
    assert result["resposta"] == (
        "Não foi possível validar a resposta com segurança usando os dados disponíveis."
    )


def test_rejected_answer_uses_generic_fallback(monkeypatch) -> None:
    _allow_with_jev(monkeypatch)

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


def test_judge_logs_non_sensitive_reasons_when_substituting_answer(monkeypatch, caplog) -> None:
    import logging

    client = _allow_with_jev(monkeypatch)
    client.response = SimpleNamespace(
        nouls={
            "fidelidade": SimpleNamespace(noul=0.1),
            "compliance": SimpleNamespace(noul=0.9),
            "relevancia": SimpleNamespace(noul=0.9),
        }
    )

    with caplog.at_level(logging.WARNING, logger="agents.juiz"):
        result = judge_module.avaliar_resposta(
            pergunta="Quais são as etapas do PDCA?",
            respostas_especialistas=[
                {"especialista": "rag", "resposta": "Planejar, Fazer, Checar e Agir."}
            ],
            evidencias_tools=[],
            resposta_orquestrador="Planejar, Fazer, Checar e Agir.",
        )

    assert result["status"] == "SUBSTITUIDO"
    assert "fidelidade=0.10" in caplog.text
    assert "evidencias_sucesso=False" in caplog.text
    assert "possível falta de suporte factual" in caplog.text


def test_factual_validation_is_delegated_to_jev(monkeypatch) -> None:
    _allow_with_jev(monkeypatch)

    answer = (
        "As quatro etapas do PDCA são:\n\n"
        "1. Plan (Planejar)\n2. Do (Fazer)\n3. Check (Checar)\n4. Act (Agir)"
    )
    result = judge_module.avaliar_resposta(
        pergunta="Quais são as quatro etapas do PDCA?",
        respostas_especialistas=[{"especialista": "rag", "resposta": answer}],
        evidencias_tools=[
            {
                "tool": "faq_retriever",
                "argumentos": {"question": "Quais são as quatro etapas do PDCA?"},
                "resultado": {
                    "status": "ok",
                    "resultados": [
                        {
                            "title": "Ciclo PDCA",
                            "content": "Plan (Planejar), Do (Fazer), Check (Checar), Act (Agir).",
                        }
                    ],
                },
                "cache": False,
            }
        ],
        resposta_orquestrador=answer,
    )

    assert result["status"] == "APROVADO"
    assert result["resposta"] == answer


def test_ordinal_answer_is_delegated_to_jev(monkeypatch) -> None:
    _allow_with_jev(monkeypatch)

    answer = "1ª etapa: Plan (Planejar)\n2ª etapa: Do (Fazer)\n3ª etapa: Check (Checar)\n4ª etapa: Act (Agir)"
    result = judge_module.avaliar_resposta(
        pergunta="Quais são as quatro etapas do PDCA?",
        respostas_especialistas=[{"especialista": "rag", "resposta": answer}],
        evidencias_tools=[
            {
                "tool": "faq_retriever",
                "resultado": {
                    "status": "ok",
                    "resultados": [
                        {"content": "Plan (Planejar), Do (Fazer), Check (Checar), Act (Agir)."}
                    ],
                },
            }
        ],
        resposta_orquestrador=answer,
    )

    assert result["status"] == "APROVADO"


def test_answer_is_not_rewritten_to_remove_timestamp(monkeypatch) -> None:
    _allow_with_jev(monkeypatch)

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
    assert "14:33" in result["resposta"]


def test_jev_can_accept_answer_without_numeric_precheck(monkeypatch) -> None:
    _allow_with_jev(monkeypatch)

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

    assert result["status"] == "APROVADO"
    assert result["resposta"] == "Existem 20 tarefas atrasadas."
