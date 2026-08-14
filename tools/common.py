"""Infraestrutura compartilhada pelas tools do ACTA."""

from typing import Any

from clients.mcp_acta_client import call_acta_tool


def call_mcp_tool(name: str, **arguments: Any) -> dict | str:
    """Encaminha uma chamada tipada e preserva a resposta estruturada."""

    return call_acta_tool(name, arguments)
