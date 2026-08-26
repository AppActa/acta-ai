"""Instâncias compartilhadas dos modelos utilizados pelos agentes ACTA."""

from langchain_groq import ChatGroq
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from config import (
    ACTA_GROQ_FAST_MODEL,
    ACTA_GROQ_MAX_RETRIES,
    ACTA_GROQ_PRIMARY_MODEL,
    ACTA_GROQ_REASONING_EFFORT,
    ACTA_GROQ_TIMEOUT_SECONDS,
    ACTA_LLM_FAST_FALLBACK_MODEL,
    ACTA_LLM_FAST_MAX_TOKENS,
    ACTA_LLM_FAST_MODEL,
    ACTA_LLM_FAST_REASONING_BUDGET,
    ACTA_LLM_PRIMARY_FALLBACK_MODEL,
    ACTA_LLM_PRIMARY_MAX_TOKENS,
    ACTA_LLM_PRIMARY_MODEL,
    GROQ_API_KEY,
    NVIDIA_API_KEY,
)


def _build_nvidia_llm(*, model, **kwargs):
    """Create an NVIDIA model with thinking disabled in the API payload."""
    model_kwargs = dict(kwargs.pop("model_kwargs", {}))
    chat_template_kwargs = dict(model_kwargs.get("chat_template_kwargs", {}))
    thinking_key = "thinking" if model.startswith("deepseek-ai/") else "enable_thinking"
    chat_template_kwargs[thinking_key] = False
    model_kwargs["chat_template_kwargs"] = chat_template_kwargs

    return ChatNVIDIA(
        model=model,
        api_key=NVIDIA_API_KEY,
        model_kwargs=model_kwargs,
        **kwargs,
    )


llm_primary = _build_nvidia_llm(
    model=ACTA_LLM_PRIMARY_MODEL,
    temperature=0.7,
    top_p=0.9,
    max_completion_tokens=ACTA_LLM_PRIMARY_MAX_TOKENS,
)

llm_primary_fallback = _build_nvidia_llm(
    model=ACTA_LLM_PRIMARY_FALLBACK_MODEL,
    temperature=0.7,
    top_p=0.9,
    max_completion_tokens=ACTA_LLM_PRIMARY_MAX_TOKENS,
)

llm_fast_primary = _build_nvidia_llm(
    model=ACTA_LLM_FAST_MODEL,
    temperature=0.0,
    top_p=0.4,
    max_completion_tokens=ACTA_LLM_FAST_MAX_TOKENS,
    model_kwargs={"reasoning_budget": ACTA_LLM_FAST_REASONING_BUDGET},
)

llm_fast_fallback = _build_nvidia_llm(
    model=ACTA_LLM_FAST_FALLBACK_MODEL,
    temperature=0.0,
    top_p=0.4,
    max_completion_tokens=ACTA_LLM_FAST_MAX_TOKENS,
)

if GROQ_API_KEY:
    llm_groq_primary = ChatGroq(
        model=ACTA_GROQ_PRIMARY_MODEL,
        api_key=GROQ_API_KEY,
        temperature=0.2,
        max_tokens=ACTA_LLM_PRIMARY_MAX_TOKENS,
        timeout=ACTA_GROQ_TIMEOUT_SECONDS,
        max_retries=ACTA_GROQ_MAX_RETRIES,
        reasoning_effort=ACTA_GROQ_REASONING_EFFORT,
        reasoning_format="hidden",
    )
    llm_groq_fast = ChatGroq(
        model=ACTA_GROQ_FAST_MODEL,
        api_key=GROQ_API_KEY,
        temperature=0.0,
        max_tokens=ACTA_LLM_FAST_MAX_TOKENS,
        timeout=ACTA_GROQ_TIMEOUT_SECONDS,
        max_retries=ACTA_GROQ_MAX_RETRIES,
        reasoning_effort=ACTA_GROQ_REASONING_EFFORT,
        reasoning_format="hidden",
    )
    # Agentes com tools tentam Groq primeiro e usam NVIDIA NIM antes do fallback
    # deterministico da pipeline.
    llm_tool_agents = llm_groq_primary.with_fallbacks([llm_primary, llm_primary_fallback])
    llm_tool_fast_agents = llm_groq_fast.with_fallbacks(
        [llm_fast_primary, llm_fast_fallback]
    )
    # Roteador, juiz, orquestrador e formatadores podem usar NIM como fallback,
    # pois essas etapas não fazem chamadas de tools.
    llm_text_agents = llm_groq_fast.with_fallbacks([llm_fast_primary, llm_fast_fallback])
else:
    llm_tool_agents = llm_primary
    llm_tool_fast_agents = llm_fast_primary
    llm_text_agents = llm_fast_primary.with_fallbacks([llm_fast_fallback])

# Aliases de compatibilidade para integracoes existentes.
llm_agents = llm_tool_agents
llm_fast_agents = llm_tool_fast_agents
llm_fast = llm_text_agents
