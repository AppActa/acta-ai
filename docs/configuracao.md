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
| `ACTA_MCP_MAX_ATTEMPTS` | Tentativas de transporte de consultas; padrão `2`. Escritas usam uma única tentativa. |
| `ACTA_INTENTION_MAX_RETRIES` | Correções da proposta de escrita; padrão `2` (inicial + duas correções). Inteiro >= 0. |
| `ACTA_RESPONSE_MAX_RETRIES` | Correções da resposta final; padrão `2` (avaliação inicial + até duas correções). Revisões permitem somente consultas. Inteiro >= 0. |
| `ACTA_MCP_USUARIO_ID` e `ACTA_MCP_EMPRESA_ID` | Identidade padrão apenas para uso fora das rotas HTTP; padrão `0`. |
| `MONGODB_URI` e `ACTA_SYSTEM_FEATURES_DB_NAME` | MongoDB das conversas, memórias e skills pessoais; banco padrão `acta`. |
| `ACTA_MEMORY_RECENT_MESSAGES` | Mensagens recentes incluídas no contexto; padrão `30`. |
| `ACTA_MEMORY_SUMMARY_EVERY_MESSAGES` | Limiar para resumir a conversa; padrão `12`. |
| `GEMINI_API_KEY` | Embeddings de memória e geração das lições aprendidas. |
| `QDRANT_CLUSTER_ENDPOINT` e `QDRANT_API_KEY` | Índice semântico opcional para memória. |
| `QDRANT_MEMORY_MESSAGES_COLLECTION_NAME` | Collection vetorial de mensagens; padrão `memoria_mensagens`. |
| `QDRANT_MEMORY_VECTOR_SIZE` e `QDRANT_TIMEOUT_SECONDS` | Dimensão dos embeddings (padrão `768`) e timeout do Qdrant (padrão `10` segundos). |

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

### Integração local de transações

`tests/test_intention_integration.py` usa a API local `http://127.0.0.1:8201`,
o MCP local `http://127.0.0.1:8001/mcp` e o MongoDB de fixtures `localhost:27018`.
Ative com `ACTA_RUN_INTENTION_INTEGRATION=1` após iniciar as fixtures PostgreSQL/MongoDB
do repositório MCP em um projeto Docker Compose separado. Configure a API/MCP com
esses bancos locais, sem apontar para dados externos.

```powershell
$env:ACTA_RUN_INTENTION_INTEGRATION = "1"
uv run pytest tests/test_intention_integration.py -q -s
```

Esses testes criam rascunhos de formulário e tarefas e alteram o status das tarefas
criadas. O teste verifica os dados reais via MongoDB e MCP. JEV, OpenAI e, nas
integrações de lições existentes, Gemini precisam estar disponíveis.

### Conversas completas com o perfil de teste 1

`tests/test_chat_flow_integration.py` acrescenta conversa com continuação,
histórico, pedidos incompletos e análise de metas/tarefas. Todas as mensagens usam
`usuario_id=1`, `empresa_id=1`, `id_ciclo=[1]` e `ciclo_ativo=1`.

As fixtures devem estar no projeto Compose `acta-chat-flow-test`, iniciado no
repositório MCP com `docker compose -p acta-chat-flow-test up -d --wait`. Os testes
conferem diretamente o contêiner `acta-chat-flow-test-postgres-1`, além do MongoDB
local, e usam os mesmos endereços de API/MCP acima.

```powershell
$env:ACTA_RUN_INTENTION_INTEGRATION = "1"
$env:ACTA_RUN_CHAT_FLOW_INTEGRATION = "1"
uv run pytest tests/test_intention_integration.py tests/test_chat_flow_integration.py -q -s
```
