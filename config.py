"""Configuração centralizada do ACTA AI.

Este módulo é o único ponto da aplicação que carrega `.env` e lê variáveis de
ambiente. Módulos de runtime devem importar constantes ou helpers daqui.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def env_str(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser um inteiro.") from exc


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser um número.") from exc


def required_positive_int(name: str) -> int:
    raw = os.getenv(name)
    if raw is None:
        raise RuntimeError(f"{name} não foi configurado.")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} deve ser um inteiro positivo.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} deve ser um inteiro positivo.")
    return value


NVIDIA_API_KEY = env_str("NVIDIA_API_KEY")
GROQ_API_KEY = env_str("GROQ_API_KEY") or env_str("GROK_API_KEY")

ACTA_GROQ_PRIMARY_MODEL = env_str("ACTA_GROQ_PRIMARY_MODEL", "openai/gpt-oss-20b")
ACTA_GROQ_FAST_MODEL = env_str("ACTA_GROQ_FAST_MODEL", "openai/gpt-oss-20b")
ACTA_GROQ_TIMEOUT_SECONDS = env_float("ACTA_GROQ_TIMEOUT_SECONDS", 8.0)
ACTA_GROQ_MAX_RETRIES = env_int("ACTA_GROQ_MAX_RETRIES", 0)
ACTA_GROQ_REASONING_EFFORT = env_str("ACTA_GROQ_REASONING_EFFORT", "low")

ACTA_LLM_PRIMARY_MODEL = env_str(
    "ACTA_LLM_PRIMARY_MODEL",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
)
ACTA_LLM_PRIMARY_FALLBACK_MODEL = env_str(
    "ACTA_LLM_PRIMARY_FALLBACK_MODEL",
    "deepseek-ai/deepseek-v4-flash-0731",
)
ACTA_LLM_FAST_MODEL = env_str(
    "ACTA_LLM_FAST_MODEL",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
)
ACTA_LLM_FAST_FALLBACK_MODEL = env_str(
    "ACTA_LLM_FAST_FALLBACK_MODEL",
    "deepseek-ai/deepseek-v4-flash-0731",
)
ACTA_LLM_PRIMARY_MAX_TOKENS = env_int("ACTA_LLM_PRIMARY_MAX_TOKENS", 768)
ACTA_LLM_FAST_MAX_TOKENS = env_int("ACTA_LLM_FAST_MAX_TOKENS", 384)
ACTA_LLM_FAST_REASONING_BUDGET = env_int("ACTA_LLM_FAST_REASONING_BUDGET", 0)

MONGODB_URI = env_str("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = env_str("MONGODB_DB_NAME", "acta_ai")
MONGODB_SESSIONS_COLLECTION = env_str("MONGODB_SESSIONS_COLLECTION", "chat_sessoes")

ACTA_MCP_DEFAULT_URL = "http://127.0.0.1:8000/mcp"
ACTA_MCP_DEFAULT_TIMEOUT_SECONDS = 30.0
ACTA_MCP_DEFAULT_MAX_ATTEMPTS = 2


def acta_mcp_url() -> str:
    return str(env_str("ACTA_MCP_URL", ACTA_MCP_DEFAULT_URL))


def acta_mcp_api_key() -> str | None:
    return env_str("ACTA_MCP_API_KEY")


def acta_mcp_timeout_seconds() -> float:
    return env_float("ACTA_MCP_TIMEOUT_SECONDS", ACTA_MCP_DEFAULT_TIMEOUT_SECONDS)


def acta_mcp_max_attempts() -> int:
    return max(1, env_int("ACTA_MCP_MAX_ATTEMPTS", ACTA_MCP_DEFAULT_MAX_ATTEMPTS))


def acta_mcp_usuario_id() -> int:
    return required_positive_int("ACTA_MCP_USUARIO_ID")


def acta_mcp_empresa_id() -> int:
    return required_positive_int("ACTA_MCP_EMPRESA_ID")


def router_llm_always() -> bool:
    return env_bool("ACTA_ROUTER_LLM_ALWAYS", False)


def enforce_specialist_tool() -> bool:
    return env_bool("ACTA_ENFORCE_SPECIALIST_TOOL", True)


def orchestrator_llm_enabled() -> bool:
    return env_bool("ACTA_ORCHESTRATOR_LLM", False)


def judge_llm_enabled() -> bool:
    return env_bool("ACTA_JUDGE_LLM", False)


def guardrail_llm_output_review_enabled() -> bool:
    return env_bool("ACTA_GUARDRAIL_LLM_OUTPUT", False)


def observability_enabled_in_tests() -> bool:
    return env_bool("ACTA_OBSERVABILITY_IN_TESTS", False)


def observability_enabled() -> bool:
    return env_bool("ACTA_OBSERVABILITY_ENABLED", True)


def otel_service_name(default: str) -> str:
    return str(env_str("OTEL_SERVICE_NAME", default))


def acta_environment() -> str:
    return str(env_str("ACTA_ENV", "development"))


def has_any_otel_endpoint() -> bool:
    return any(
        env_str(name)
        for name in (
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        )
    )


def set_default_env(name: str, value: str) -> None:
    os.environ.setdefault(name, value)
