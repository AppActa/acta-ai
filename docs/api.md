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
  "usuario_id": 1,
  "empresa_id": 1,
  "id_ciclo": [12, 15],
  "ciclo_ativo": 12
}
```

`id_ciclo` aceita o formato legado de um inteiro ou uma lista opcional com até 20 IDs
positivos. O inteiro legado é normalizado para lista. IDs duplicados são removidos
mantendo a ordem da primeira ocorrência. `ciclo_ativo` também é opcional e, quando
informado, precisa constar na lista; ele é consultado primeiro. Lista ausente ou
vazia não permite consultas de dados de ciclo. Perguntas comparativas usam chamadas
MCP separadas para cada ID permitido; sem ciclo ativo, perguntas ambíguas com vários
ciclos pedem que o usuário escolha. Cada chamada continua sendo autorizada pelo MCP.
A resposta contém o mesmo `session_id` e o campo `resposta`. Mensagens de usuário e
assistente são persistidas pelo fluxo da conversa.

### Listar conversas

`GET /listar_chats?usuario_id=1&empresa_id=1&limit=50`

Retorna somente conversas não vazias pertencentes ao usuário dentro da empresa. Cada
item inclui `session_id`, `titulo`, estado, contagem de mensagens e datas de atividade.
O título é derivado da primeira mensagem do usuário, limitado a 80 caracteres; sessões
antigas sem título são preenchidas ao serem listadas. O limite é aplicado pelo MCP,
entre 1 e 100.

### Listar mensagens de uma conversa

`GET /chats/{session_id}/mensagens?usuario_id=1&empresa_id=1&limit=30`

Retorna as mensagens mais recentes da sessão em ordem cronológica. `limit` é opcional,
usa 30 por padrão e aceita valores entre 1 e 100. A sessão precisa pertencer ao
usuário e à empresa informados; uma sessão inexistente retorna 404.

### Áudio

`POST /chat/audio` recebe `multipart/form-data` com `audio`,
`session_id`, `usuario_id`, `empresa_id`, um `id_ciclo`
legado ou até 20 campos `id_ciclo`, e
`ciclo_ativo` opcional. O ciclo legado é normalizado para lista; IDs duplicados são
removidos mantendo a ordem da primeira ocorrência. O ciclo ativo, se informado,
precisa estar na lista e será priorizado. O arquivo não pode exceder 25 MB. A resposta
inclui a transcrição e a resposta do chat.

## Memória e consentimento

- `GET /memoria?usuario_id=1&empresa_id=1&tipo=preferencia&limit=50`
- `DELETE /memoria/{id_memoria}?usuario_id=1&empresa_id=1`
- `GET /memoria/consentimento?usuario_id=1&empresa_id=1`
- `PUT /memoria/consentimento`
- `GET /memoria/buscar?pergunta=preferência&usuario_id=1&empresa_id=1&limit=6`

O corpo do `PUT` aceita `modo`: `desativado`, `somente_explicitas` ou `automatica`,
e `retencao_dias` opcional. Veja a política em [Memória](memoria.md).

## Skills personalizadas

- `POST /skills` recebe `usuario_id`, `empresa_id` e `conteudo_markdown`.
- `GET /skills?usuario_id=1&empresa_id=1&limit=50` lista as skills privadas.
- `DELETE /skills/{nome}?usuario_id=1&empresa_id=1` remove uma skill.

Uma skill é um contrato Markdown restrito com `# nome`, `# objetivo` e `# regras`.
Ela orienta a apresentação da resposta e não concede acesso adicional a dados ou
tools.
