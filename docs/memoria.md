# Memória entre conversas

## Papel dos dois repositórios

O ACTA AI identifica preferências e pontos explícitos na conversa, decide quando
consolidar um resumo e chama as tools de memória. O `mcp-acta-ai` persiste e consulta
os dados. Assim, a API conversacional não mantém credenciais de MongoDB ou Qdrant.

## Ciclo de vida

1. `POST /nova_conversa` gera um `session_id`, sem gravar uma sessão vazia.
2. A primeira chamada a `POST /chat` garante a sessão e salva as mensagens.
3. Antes de responder, o fluxo pede contexto ao MCP: resumo, últimas mensagens,
   preferências e memórias semanticamente relevantes.
4. O ACTA AI extrai memórias explícitas, como preferências e decisões, e pede sua
   gravação conforme o consentimento.
5. Ao abrir outra conversa com `session_id_atual`, a API força a consolidação do que
   ainda não foi resumido e encerra a conversa anterior se houver mensagens.

## Recuperação semântica

A pergunta atual é convertida em embedding no MCP e pesquisada no Qdrant. A consulta
sempre filtra por `usuario_id`, `empresa_id` e estado ativo. Por isso, uma nova
conversa pode recuperar uma preferência semanticamente relacionada a uma conversa
anterior, sem depender de correspondência literal por regex.

## Consentimento e retenção

| Modo | Efeito |
| --- | --- |
| `desativado` | Remove as memórias longas ativas; mensagens da conversa seguem a retenção operacional. |
| `somente_explicitas` | Aceita somente memórias declaradas explicitamente. |
| `automatica` | Permite memórias inferidas pelo fluxo, respeitando a retenção definida. |

As mensagens possuem TTL configurável. Memórias explícitas persistem até exclusão do
usuário, salvo se ele escolher uma retenção. Exclusão e expiração removem o registro
canônico e o vetor correspondente.

Detalhes das collections, embeddings de 768 dimensões e reindexação estão na
documentação de [memória do MCP](../../mcp-acta-ai/docs/memory.md).
