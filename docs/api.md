# Referência da API HTTP

Todos os identificadores numéricos devem ser positivos. A documentação OpenAPI
interativa está em `/docs` quando a aplicação está em execução.

## Saúde

`GET /health`

Retorna que a API do ACTA AI está ativa. Essa rota não verifica a saúde dos serviços
internos; para isso, consulte `GET /health` no MCP.

## Conversas

### Criar conversa

`POST /nova_conversa`

```json
{
  "usuario_id": 1,
  "empresa_id": 1,
  "session_id_atual": "opcional"
}
```

Sempre devolve um novo UUID ainda não persistido. Ele só passa a existir no MongoDB
quando a primeira mensagem é salva. Se `session_id_atual` for enviado, a API tenta
consolidar o resumo pendente e encerra a conversa anterior somente se ela tiver
mensagens. Portanto, uma conversa vazia não é criada, resumida nem listada.

```json
{
  "usuario_id": 1,
  "empresa_id": 1,
  "session_id": "uuid",
  "conversa_anterior_encerrada": true
}
```

### Enviar mensagem

`POST /chat`

```json
{
  "message": "Quais tarefas estão atrasadas?",
  "session_id": "uuid",
  "id_ciclo": 12,
  "usuario_id": 1,
  "empresa_id": 1
}
```

`id_ciclo` é opcional. A resposta contém o mesmo `session_id` e o campo `resposta`.
Mensagens de usuário e assistente são persistidas pelo fluxo da conversa.

### Listar conversas

`GET /listar_chats?usuario_id=1&empresa_id=1&limit=50`

Retorna somente conversas não vazias pertencentes ao usuário dentro da empresa. Cada
item inclui o `session_id`, estado, contagem de mensagens e datas de atividade.
O limite é aplicado pelo MCP, entre 1 e 100.

### Áudio

`POST /chat/audio` recebe `multipart/form-data` com `audio`, `session_id`,
`usuario_id`, `empresa_id` e `id_ciclo` opcional. O arquivo não pode exceder 25 MB.
A resposta inclui a transcrição e a resposta do chat.

## Memória e consentimento

- `GET /memoria?usuario_id=1&empresa_id=1&tipo=preferencia&limit=50`
- `DELETE /memoria/{id_memoria}?usuario_id=1&empresa_id=1`
- `GET /memoria/consentimento?usuario_id=1&empresa_id=1`
- `PUT /memoria/consentimento`

O corpo do `PUT` aceita `modo`: `desativado`, `somente_explicitas` ou `automatica`,
e `retencao_dias` opcional. Veja a política em [Memória](memoria.md).

## Skills personalizadas

- `POST /skills` recebe `usuario_id`, `empresa_id` e `conteudo_markdown`.
- `GET /skills?usuario_id=1&empresa_id=1&limit=50` lista as skills privadas.
- `DELETE /skills/{nome}?usuario_id=1&empresa_id=1` remove uma skill.

Uma skill é um contrato Markdown restrito com `# nome`, `# objetivo` e `# regras`.
Ela orienta a apresentação da resposta e não concede acesso adicional a dados ou
tools.
