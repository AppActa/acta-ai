"""Configuração centralizada do ACTA AI.

Este módulo é o único ponto da aplicação que carrega `.env` e lê variáveis de
ambiente. Módulos de runtime devem importar constantes ou helpers daqui.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
JEV_API_KEY = os.getenv("JEV_API_KEY")

ACTA_INTENTION_MAX_RETRIES = int(os.getenv("ACTA_INTENTION_MAX_RETRIES", "2"))
if ACTA_INTENTION_MAX_RETRIES < 0:
    raise ValueError("ACTA_INTENTION_MAX_RETRIES deve ser >= 0.")

ACTA_RESPONSE_MAX_RETRIES = int(os.getenv("ACTA_RESPONSE_MAX_RETRIES", "2"))
if ACTA_RESPONSE_MAX_RETRIES < 0:
    raise ValueError("ACTA_RESPONSE_MAX_RETRIES deve ser >= 0.")

ACTA_OPENAI_MODEL = os.getenv("ACTA_OPENAI_MODEL", "gpt-6-luna")
ACTA_OPENAI_TRANSCRIPTION_MODEL = os.getenv(
    "ACTA_OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe"
)
ACTA_OPENAI_REASONING_EFFORT = os.getenv("ACTA_OPENAI_REASONING_EFFORT", "none")
ACTA_OPENAI_MAX_TOKENS = int(os.getenv("ACTA_OPENAI_MAX_TOKENS", "2048"))

ACTA_MCP_URL = os.getenv("ACTA_MCP_URL", "http://127.0.0.1:8000/mcp")
ACTA_MCP_API_KEY = os.getenv("ACTA_MCP_API_KEY")
ACTA_MCP_TIMEOUT_SECONDS = float(os.getenv("ACTA_MCP_TIMEOUT_SECONDS", "20.0"))
ACTA_MCP_MAX_ATTEMPTS = max(1, int(os.getenv("ACTA_MCP_MAX_ATTEMPTS", "2")))
ACTA_MCP_USUARIO_ID = int(os.getenv("ACTA_MCP_USUARIO_ID", "0"))
ACTA_MCP_EMPRESA_ID = int(os.getenv("ACTA_MCP_EMPRESA_ID", "0"))

ACTA_AUTH_API_URL = os.getenv(
    "ACTA_AUTH_API_URL",
    "https://acta-auth-api.34-232-250-240.sslip.io/api/v1",
).rstrip("/")
ACTA_AUTH_API_TIMEOUT_SECONDS = float(os.getenv("ACTA_AUTH_API_TIMEOUT_SECONDS", "10"))

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27018")
MONGODB_SESSIONS_COLLECTION = "memoria_sessoes"
MONGODB_MESSAGES_COLLECTION = "memoria_mensagens"
ACTA_SYSTEM_FEATURES_DB_NAME = os.getenv("ACTA_SYSTEM_FEATURES_DB_NAME", "acta")
QDRANT_CLUSTER_ENDPOINT = os.getenv("QDRANT_CLUSTER_ENDPOINT")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_MEMORY_MESSAGES_COLLECTION_NAME = os.getenv(
    "QDRANT_MEMORY_MESSAGES_COLLECTION_NAME", "memoria_mensagens"
)
QDRANT_MEMORY_VECTOR_SIZE = int(os.getenv("QDRANT_MEMORY_VECTOR_SIZE", "768"))
QDRANT_TIMEOUT_SECONDS = float(os.getenv("QDRANT_TIMEOUT_SECONDS", "10"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ACTA_MEMORY_RECENT_MESSAGES = int(os.getenv("ACTA_MEMORY_RECENT_MESSAGES", "30"))
ACTA_MEMORY_SUMMARY_EVERY_MESSAGES = int(os.getenv("ACTA_MEMORY_SUMMARY_EVERY_MESSAGES", "12"))
