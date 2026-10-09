# ACTA AI

API FastAPI do assistente gerencial do ACTA. Este repositório recebe a mensagem do
usuário, executa o fluxo LangGraph, aplica as proteções de entrada e saída e usa o
`mcp-acta-ai` para operações dos domínios ACTA e mantém capacidades próprias do
chatbot — memória e skills pessoais — no ACTA AI.

## Visão rápida

```text
Cliente HTTP → ACTA AI → LangGraph → tools de domínio MCP
                            ↘ memória / skills → MongoDB / Qdrant
```

A identidade da requisição (`usuario_id` e `empresa_id`) limita operações do ACTA AI
e é propagada ao MCP por cabeçalhos internos para consultas e escritas de domínio.
As credenciais de MongoDB/Qdrant da memória ficam na configuração do ACTA AI e nunca
são expostas ao modelo. O FAQ usa a tool `faq_retriever` publicada pelo MCP.

## Documentação

- [Arquitetura e fluxo da conversa](docs/arquitetura.md)
- [Referência da API HTTP](docs/api.md)
- [Memória entre conversas](docs/memoria.md)
- [Configuração, execução e testes](docs/configuracao.md)

## Execução local

O MCP deve estar disponível antes de iniciar esta API. Consulte a documentação do
repositório `mcp-acta-ai` para subir os serviços de dados.

```powershell
Copy-Item .env.example .env
uv sync --extra dev
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8200
```

Endpoints locais:

- API: `http://127.0.0.1:8200`
- Saúde: `GET /health`
- OpenAPI: `http://127.0.0.1:8200/docs`

## Configuração mínima

```env
OPENAI_API_KEY=sua_chave
ACTA_MCP_URL=http://127.0.0.1:8000/mcp
ACTA_MCP_API_KEY=mesmo_segredo_do_mcp
```

O chat usa `gpt-6-luna` e a transcrição de áudio usa `gpt-transcribe`. Os nomes podem
ser ajustados por `ACTA_OPENAI_MODEL` e `ACTA_OPENAI_TRANSCRIPTION_MODEL`.

Para chamadas feitas fora de uma rota HTTP, defina também
`ACTA_MCP_USUARIO_ID` e `ACTA_MCP_EMPRESA_ID`. As rotas da API recebem esses
identificadores no corpo ou na query e os propagam durante a execução.

## Testes e qualidade

```powershell
uv run pytest
uv run ruff check .
```

## Docker

```powershell
docker build -t acta-ai .
docker run --env-file .env -p 8200:8200 acta-ai
```

O container precisa conseguir alcançar o endpoint configurado em `ACTA_MCP_URL`.
