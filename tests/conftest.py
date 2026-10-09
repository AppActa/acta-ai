"""Configuração comum dos testes, sem credenciais externas."""

import os

os.environ.setdefault("OPENAI_API_KEY", "test-only-not-a-real-secret")
