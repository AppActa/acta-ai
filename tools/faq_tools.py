"""Tool LangChain para consulta do conhecimento autorizado do ACTA."""

from langchain_core.tools import tool

from tools.common import call_mcp_tool


@tool
def faq_retriever(question: str, limit: int = 3) -> str:
    """Busca trechos conceituais sobre ACTA, PDCA e ferramentas de qualidade."""

    response = call_mcp_tool("faq_retriever", question=question, limit=limit)
    if not isinstance(response, dict):
        return str(response)

    results = response.get("resultados", [])
    if not results:
        return ""

    excerpts = []
    for result in results:
        title = result.get("title") or result.get("section") or "Documentação ACTA"
        content = result.get("content", "")
        source = result.get("source", "")
        excerpts.append(f"Fonte: {source}\nTítulo: {title}\n{content}".strip())

    return "\n\n---\n\n".join(excerpts)


TOOLS = [faq_retriever]
