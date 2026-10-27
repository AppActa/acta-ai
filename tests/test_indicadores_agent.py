from agents.agents import ESPECIALISTAS_VALIDOS, ciclo_agent
from agents.estado import REGISTRO_ESPECIALISTAS
from agents.prompts.prompt_ciclo import CICLO_PROMPT_COMPLETO
from tools.ciclo_tools import TOOLS


def test_cycle_agent_has_tools_for_indicator_questions() -> None:
    tool_names = {tool.name for tool in TOOLS}

    assert "ciclo_visao_geral" in tool_names
    assert "ciclo_riscos_pendencias" in tool_names


def test_indicator_agent_is_registered_as_specialist() -> None:
    assert "indicadores" in ESPECIALISTAS_VALIDOS
    assert "indicadores" in REGISTRO_ESPECIALISTAS


def test_indicator_route_uses_cycle_agent() -> None:
    assert REGISTRO_ESPECIALISTAS["indicadores"].args[0] is ciclo_agent


def test_cycle_prompt_does_not_confuse_target_with_observed_result() -> None:
    prompt = CICLO_PROMPT_COMPLETO.lower()
    assert "variação necessária" in prompt
    assert "não fornece uma série histórica numérica" in prompt
    assert "não trate status como medição realizada" in prompt
