"""Instâncias compartilhadas dos modelos utilizados pelos agentes ACTA."""

import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

nvidia_api_key = os.getenv("NVIDIA_API_KEY")
groq_api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")

# Os IDs podem ser trocados pelo ambiente quando o catálogo hospedado mudar.
PRIMARY_MODEL = os.getenv("ACTA_LLM_PRIMARY_MODEL", "deepseek-ai/deepseek-v4-pro")
PRIMARY_FALLBACK_MODEL = os.getenv(
    "ACTA_LLM_PRIMARY_FALLBACK_MODEL",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
)
FAST_MODEL = os.getenv("ACTA_LLM_FAST_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
FAST_FALLBACK_MODEL = os.getenv(
    "ACTA_LLM_FAST_FALLBACK_MODEL",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
)
PRIMARY_MAX_TOKENS = int(os.getenv("ACTA_LLM_PRIMARY_MAX_TOKENS", "2048"))
FAST_MAX_TOKENS = int(os.getenv("ACTA_LLM_FAST_MAX_TOKENS", "1024"))
FAST_REASONING_BUDGET = int(os.getenv("ACTA_LLM_FAST_REASONING_BUDGET", "0"))
GROQ_PRIMARY_MODEL = os.getenv("ACTA_GROQ_PRIMARY_MODEL", "openai/gpt-oss-120b")
GROQ_FAST_MODEL = os.getenv("ACTA_GROQ_FAST_MODEL", "openai/gpt-oss-20b")
GROQ_TIMEOUT_SECONDS = float(os.getenv("ACTA_GROQ_TIMEOUT_SECONDS", "15"))
GROQ_MAX_RETRIES = int(os.getenv("ACTA_GROQ_MAX_RETRIES", "0"))
GROQ_REASONING_EFFORT = os.getenv("ACTA_GROQ_REASONING_EFFORT", "low")


llm_primary = ChatNVIDIA(
    model=PRIMARY_MODEL,
    temperature=0.7,
    top_p=0.9,
    max_completion_tokens=PRIMARY_MAX_TOKENS,
    api_key=nvidia_api_key,
)

llm_primary_fallback = ChatNVIDIA(
    model=PRIMARY_FALLBACK_MODEL,
    api_key=nvidia_api_key,
    temperature=0.7,
    top_p=0.9,
    max_completion_tokens=PRIMARY_MAX_TOKENS,
)

# Mantido como uma alternativa independente para usos futuros e diagnósticos.
llm_tool_fallback = ChatNVIDIA(
    model="nvidia/nemotron-3-super-120b-a12b",
    api_key=nvidia_api_key,
    temperature=0.7,
    top_p=0.9,
    max_completion_tokens=PRIMARY_MAX_TOKENS,
)

llm_fast_primary = ChatNVIDIA(
    model=FAST_MODEL,
    api_key=nvidia_api_key,
    temperature=0.0,
    top_p=0.4,
    max_completion_tokens=FAST_MAX_TOKENS,
    model_kwargs={"reasoning_budget": FAST_REASONING_BUDGET},
)

llm_fast_fallback = ChatNVIDIA(
    model=FAST_FALLBACK_MODEL,
    api_key=nvidia_api_key,
    temperature=0.0,
    top_p=0.4,
    max_completion_tokens=FAST_MAX_TOKENS,
)

if groq_api_key:
    llm_groq_primary = ChatGroq(
        model=GROQ_PRIMARY_MODEL,
        api_key=groq_api_key,
        temperature=0.2,
        max_tokens=PRIMARY_MAX_TOKENS,
        timeout=GROQ_TIMEOUT_SECONDS,
        max_retries=GROQ_MAX_RETRIES,
        reasoning_effort=GROQ_REASONING_EFFORT,
        reasoning_format="hidden",
    )
    llm_groq_fast = ChatGroq(
        model=GROQ_FAST_MODEL,
        api_key=groq_api_key,
        temperature=0.0,
        max_tokens=FAST_MAX_TOKENS,
        timeout=GROQ_TIMEOUT_SECONDS,
        max_retries=GROQ_MAX_RETRIES,
        reasoning_effort=GROQ_REASONING_EFFORT,
        reasoning_format="hidden",
    )
    llm_agents = llm_groq_primary.with_fallbacks(
        [llm_primary, llm_primary_fallback, llm_tool_fallback]
    )
    llm_fast_agents = llm_groq_fast.with_fallbacks([llm_fast_primary, llm_fast_fallback])
else:
    llm_agents = llm_primary.with_fallbacks([llm_primary_fallback, llm_tool_fallback])
    llm_fast_agents = llm_fast_primary.with_fallbacks([llm_fast_fallback])

llm_fast = llm_fast_agents
