# Histórico de conversas

## Persistência

O MongoDB usa duas collections para conversas:

- `memoria_sessoes`: identificação, proprietário, título, resumo e estado da sessão.
- `memoria_mensagens`: cada mensagem, armazenada separadamente e ligada por `session_id`.

O histórico não expira automaticamente. O contexto carregado para responder uma conversa
inclui até 30 mensagens mais recentes (15 turnos). A API de consulta do histórico pode
retornar páginas de até 100 mensagens.

Quando configurado, o Qdrant indexa as mensagens em `memoria_mensagens` para recuperação
semântica. O MongoDB continua sendo a fonte canônica. Resumos incrementais ficam no
documento da sessão.
