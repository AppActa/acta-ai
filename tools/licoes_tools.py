"""Tools A2A de lições aprendidas disponíveis ao especialista de ciclos."""

from typing import Any

from langchain_core.tools import tool

from clients.a2a_client import enviar_pedido_licao


@tool
def criar_licao_aprendida(contexto: str, expectativa: str) -> dict[str, Any]:
    """Cria uma lição com contexto e expectativa redigidos pelo agente de ciclos."""

    return enviar_pedido_licao(
        skill="criar_licao",
        payload={"contexto": contexto, "expectativa": expectativa},
    )


@tool
def resumir_licoes_aprendidas() -> dict[str, Any]:
    """Resume as lições aprendidas do ciclo ativo."""

    return enviar_pedido_licao(skill="resumir_licao", payload={})


@tool
def consultar_licoes_aprendidas(pergunta: str) -> dict[str, Any]:
    """Consulta lições aprendidas do ciclo ativo com uma pergunta redigida pelo agente."""

    return enviar_pedido_licao(skill="pergunta_licao", payload={"pergunta": pergunta})


TOOLS = [
    criar_licao_aprendida,
    resumir_licoes_aprendidas,
    consultar_licoes_aprendidas,
]
