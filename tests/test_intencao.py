import pytest
from pydantic import ValidationError

from agents.intencao import AvaliacaoIntencao, Intention


def verdict(**changes):
    return {"decisao": "aprovada", "apoio": 0.9, "motivo": "Consulta solicitada.", "pergunta": None, **changes}


@pytest.mark.parametrize("apoio", [True, "0.9", float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_support(apoio):
    with pytest.raises(ValidationError):
        AvaliacaoIntencao.model_validate(verdict(apoio=apoio))


@pytest.mark.parametrize("changes", [
    {"decisao": "desconhecida"}, {"pergunta": "Qual ciclo?"},
    {"decisao": "pedir_esclarecimento"}, {"motivo": " "}, {"extra": True},
])
def test_invalid_or_contradictory_verdict(changes):
    with pytest.raises(ValidationError):
        AvaliacaoIntencao.model_validate(verdict(**changes))


@pytest.mark.parametrize("payload", [
    {"tool": "", "argumentos": {}}, {"tool": "x", "argumentos": []},
    {"tool": "x", "argumentos": {}, "execute": True},
])
def test_invalid_intention(payload):
    with pytest.raises(ValidationError):
        Intention.model_validate(payload)


def test_support_boundary_and_clarification():
    assert AvaliacaoIntencao.model_validate(verdict(apoio=0.7)).apoio == 0.7
    result = AvaliacaoIntencao.model_validate(verdict(decisao="pedir_esclarecimento", pergunta="Qual ciclo?"))
    assert result.pergunta == "Qual ciclo?"
