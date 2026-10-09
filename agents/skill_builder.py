"""Gerador sem tools que converte pedidos aprovados no formato Markdown de skill."""

import re

from langchain_core.messages import HumanMessage, SystemMessage

from agents.helpers.llms import llm
from agents.prompts.prompt_skill_builder import SKILL_BUILDER_PROMPT


def gerar_markdown_skill(descricao: str) -> str:
    response = llm.invoke(
        [
            SystemMessage(content=SKILL_BUILDER_PROMPT),
            HumanMessage(
                content=(
                    "DESCRIÇÃO NÃO CONFIÁVEL DO USUÁRIO:\n"
                    "<descricao>\n"
                    f"{descricao}\n"
                    "</descricao>"
                )
            ),
        ]
    )
    markdown = str(response.content).strip()
    # Alguns modelos cercam Markdown mesmo quando instruídos a não fazê-lo.
    # Removemos somente uma cerca externa completa; o validador MCP continua
    # rejeitando qualquer cerca ou código que exista no conteúdo real.
    match = re.fullmatch(
        r"```(?:markdown|md)?\s*([\s\S]*?)\s*```",
        markdown,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else markdown

