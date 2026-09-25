# Configuração, execução e testes

## Pré-requisitos

- Python compatível com o `pyproject.toml` e `uv`;
- um servidor `mcp-acta-ai` acessível;
- credenciais de LLM configuradas para os modelos usados;
- `ACTA_MCP_API_KEY` igual à chave configurada no MCP quando a autenticação por chave
  estiver ativa.

## Variáveis principais

| Variável | Uso |
| --- | --- |
| `NVIDIA_API_KEY` | Acesso aos modelos NVIDIA configurados. |
| `GROQ_API_KEY` | Acesso opcional aos modelos Groq. |
| `ACTA_MCP_URL` | URL Streamable HTTP do MCP, normalmente `http://127.0.0.1:8000/mcp`. |
| `ACTA_MCP_API_KEY` | Credencial compartilhada entre os serviços. |
| `ACTA_MCP_TIMEOUT_SECONDS` | Tempo máximo de uma chamada MCP. |
| `ACTA_MCP_MAX_ATTEMPTS` | Número de tentativas para falhas transitórias. |
| `ACTA_MCP_USUARIO_ID` e `ACTA_MCP_EMPRESA_ID` | Identidade padrão apenas para uso fora das rotas HTTP. |
| `MONGODB_URI` e `ACTA_SYSTEM_FEATURES_DB_NAME` | MongoDB das conversas, memórias e skills pessoais. |
| `GEMINI_API_KEY` | Embeddings de memória e geração das lições aprendidas. |
| `QDRANT_CLUSTER_ENDPOINT` e `QDRANT_API_KEY` | Índice semântico opcional para memória. |

Os parâmetros de modelos, guardrails, especialistas e observabilidade estão
documentados no `.env.example`. Nunca versione o `.env` real.

## Desenvolvimento

```powershell
Copy-Item .env.example .env
uv sync --extra dev
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8200
```

## Testes

```powershell
uv run pytest
uv run ruff check .
```

Alguns testes de integração e especialistas dependem de variáveis e serviços
opcionais; a suíte informa explicitamente os testes ignorados.
