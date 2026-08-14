from agents.helpers.estado import REGISTRO_ESPECIALISTAS
from agents.prompts.prompt_indicadores import INDICADORES_PROMPT_COMPLETO
from agents.router import ESPECIALISTAS_VALIDOS
from tools.indicador_tools import TOOLS


def test_indicator_agent_uses_only_required_read_tools() -> None:
    assert [tool.name for tool in TOOLS] == [
        "ciclo_visao_geral",
        "ciclo_riscos_pendencias",
        "predicoes_atingimento_meta",
    ]


def test_indicator_agent_is_registered_as_specialist() -> None:
    assert "indicadores" in ESPECIALISTAS_VALIDOS
    assert "indicadores" in REGISTRO_ESPECIALISTAS


def test_indicator_prompt_does_not_confuse_target_with_observed_result() -> None:
    prompt = INDICADORES_PROMPT_COMPLETO.lower()
    assert "variação necessária" in prompt
    assert "não fornece uma série histórica numérica" in prompt
    assert "não trate status ou previsão como medição realizada" in prompt
