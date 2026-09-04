# Conversas e Memória Persistente — Desenho

## Objetivo

Permitir iniciar uma nova conversa sem persistir sessões vazias, encerrar e resumir a conversa anterior quando ela tiver mensagens, listar os chats de cada usuário e empresa e manter mensagens e memórias sincronizadas entre MongoDB (fonte de verdade) e Qdrant (índice semântico).

## Escopo

Este desenho abrange `acta-ai` e `mcp-acta-ai`.

- `acta-ai` expõe os endpoints HTTP, gera resumos e chama as ferramentas MCP.
- `mcp-acta-ai` aplica autorização, persiste no MongoDB e mantém os índices Qdrant.
- MongoDB é a fonte de verdade. Uma indisponibilidade do Qdrant não invalida uma gravação no MongoDB; ela fica registrada para reindexação.

## API HTTP

### `POST /nova_conversa`

Entrada:

```json
{
  "usuario_id": 3,
  "empresa_id": 4,
  "session_id_atual": "opcional"
}
```

Comportamento:

1. Cria um novo UUID e o devolve como `session_id`.
2. Se `session_id_atual` não foi informado, não consulta nem persiste uma sessão anterior.
3. Se foi informado, consulta a sessão dentro do contexto autenticado.
4. Se a sessão não existe ou não contém mensagens, não cria resumo, não grava uma sessão vazia e não a lista como chat.
5. Se há mensagens, força a consolidação do resumo mesmo abaixo do limiar normal, persiste o resumo e encerra a sessão anterior.
6. O novo UUID é apenas um identificador até o primeiro `POST /chat`; a primeira mensagem cria a sessão e seus índices.

Saída:

```json
{
  "usuario_id": 3,
  "empresa_id": 4,
  "session_id": "novo-uuid",
  "conversa_anterior_encerrada": true
}
```

`/nova_sessao` será removido em favor deste contrato, pois sua criação antecipada de sessões vazias viola a regra de negócio.

### `GET /listar_chats`

Parâmetros: `usuario_id`, `empresa_id` e `limit` opcional (padrão 50, máximo 100).

Retorna apenas sessões do dono autenticado com `total_mensagens > 0`, ordenadas por `atualizada_em` decrescente. Cada chat contém `session_id`, `status`, `iniciada_em`, `atualizada_em`, `encerrada_em`, `total_mensagens` e `resumo`.

## Contratos MCP

Serão adicionadas ferramentas internas para:

- obter material de resumo sem criar sessão;
- encerrar sessão somente quando ela existir e tiver mensagens;
- listar chats do proprietário autenticado.

O contrato de material de resumo incluirá `tem_mensagens`. O `acta-ai` usará esse sinal para não invocar o LLM quando não houver conteúdo. A rotina de consolidação receberá um parâmetro `forcar`; no fluxo comum continua respeitando o limiar configurado, mas no encerramento cria o resumo de qualquer conversa não vazia.

## Persistência e índices

As coleções Mongo existentes permanecem:

- `memoria_sessoes`: metadados, resumo e ciclo de vida da conversa;
- `memoria_mensagens`: mensagens sanitizadas;
- `memoria_usuario`: memórias longas e explícitas/inferidas;
- `memoria_consentimentos`: política de retenção, sem representação vetorial.

O Qdrant terá uma coleção por conteúdo semanticamente pesquisável, com os mesmos nomes Mongo:

- `memoria_mensagens`, contendo o texto da mensagem e metadados de dono, sessão, papel e status;
- `memoria_usuario`, contendo o texto da memória e metadados de dono, tipo e status.

Ambas usarão distância cosseno e dimensão 768. Os pontos usarão o mesmo `_id` do Mongo. A sessão não será vetorizada pois não contém conteúdo semântico independente; ela é consultada diretamente no Mongo. Consentimentos também não são indexados por não constituírem conteúdo de busca.

O modelo de embeddings passará para `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`, que produz 768 dimensões e atende a conteúdo em português. A antiga coleção Qdrant de memória, de 384 dimensões, será substituída por coleções derivadas do Mongo; a inicialização recriará somente coleções de memória incompatíveis e reindexará os documentos ativos no Mongo.

Uma falha de Qdrant após a gravação no Mongo não desfaz o documento canônico: o documento receberá estado de índice pendente e será reprocessado na inicialização seguinte. Exclusão e expiração removem os pontos correspondentes depois de atualizar o Mongo.

## Refatoração limitada

- Remover `acta-ai/db_scripts/memory_mongo.py`, fachada não importada e contrária à centralização no MCP.
- Remover imports e funções que se tornarem órfãos por essa remoção e pela substituição de `/nova_sessao`.
- Preservar todas as alterações locais já existentes em `mcp-acta-ai`; não fazem parte desta mudança.

## Testes e critérios de aceite

1. Uma chamada a `/nova_conversa` sem sessão anterior devolve UUID e não chama persistência.
2. Uma conversa anterior inexistente ou vazia não é resumida, encerrada nem listada.
3. Uma conversa com mensagens é resumida mesmo abaixo do limiar, encerrada e o novo UUID é devolvido.
4. `/listar_chats` devolve somente chats do usuário e empresa autenticados, sem sessões vazias, com ordenação e limite aplicados.
5. Criar uma mensagem escreve um documento no Mongo e um ponto na coleção Qdrant `memoria_mensagens` com dimensão 768.
6. Criar uma memória mantém a escrita Mongo/Qdrant na coleção `memoria_usuario` de 768 dimensões.
7. Falhas do Qdrant não removem nem invalidam os dados canônicos Mongo.
8. Os testes atuais continuam verdes e os verificadores estáticos não reportam importações ou variáveis não usadas introduzidas pela alteração.
