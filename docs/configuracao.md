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
| `OPENAI_API_KEY` | Acesso aos modelos de chat e transcrição da OpenAI. |
| `ACTA_OPENAI_MODEL` | Modelo dos agentes; padrão `gpt-6-luna`. |
| `ACTA_OPENAI_TRANSCRIPTION_MODEL` | Modelo de transcrição; padrão `gpt-transcribe`. |
| `ACTA_OPENAI_REASONING_EFFORT` | Esforço de raciocínio do chat; padrão `none`, necessário para chamadas de tools no Chat Completions. |
| `ACTA_OPENAI_MAX_TOKENS` | Limite de saída do chat; padrão `2048`. |
| `ACTA_MCP_URL` | URL Streamable HTTP do MCP, normalmente `http://127.0.0.1:8000/mcp`. |
| `ACTA_MCP_API_KEY` | Credencial compartilhada entre os serviços. |
| `ACTA_MCP_TIMEOUT_SECONDS` | Tempo máximo de uma chamada MCP. |
| `ACTA_MCP_MAX_ATTEMPTS` | Número de tentativas para falhas transitórias. |
| `ACTA_MCP_USUARIO_ID` e `ACTA_MCP_EMPRESA_ID` | Identidade padrão apenas para uso fora das rotas HTTP. |
| `MONGODB_URI` e `ACTA_SYSTEM_FEATURES_DB_NAME` | MongoDB das conversas, memórias e skills pessoais. |
| `GEMINI_API_KEY` | Embeddings de memória e geração das lições aprendidas. |
| `QDRANT_CLUSTER_ENDPOINT` e `QDRANT_API_KEY` | Índice semântico opcional para memória. |

Os parâmetros de modelos, guardrails e especialistas estão
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
