# Validação do fluxo completo do chatbot

Data: 29/10/2026.

## Escopo e ambiente

Requisições HTTP reais ao FastAPI, passando pelo fluxo normal do chatbot:
guardrail de entrada, memória, roteador, especialistas, MCP, síntese, guardrail de
saída, juiz final e persistência. A consulta ao histórico da própria conversa usa
a rota geral, conforme o comportamento existente.

API, MCP, PostgreSQL e MongoDB executaram em Docker, com provedores reais dos
modelos. Os bancos são fixtures locais. O código da aplicação veio das imagens
construídas pelos Dockerfiles; um observador temporário apenas registrou etapas e
decisões, devolvendo os resultados originais sem alterações. Não foram injetados
rascunhos incorretos nem simuladas decisões nesta rodada.

Todas as 14 chamadas válidas ao `/chat` na rodada final usaram:

```json
{
  "message": "pergunta do cenário",
  "session_id": "identificador da conversa de teste",
  "usuario_id": 1,
  "empresa_id": 1,
  "id_ciclo": [1],
  "ciclo_ativo": 1
}
```

Endpoint usado durante os testes: `http://127.0.0.1:8201/chat`.

## Resultado final

| Verificação | Resultado |
| --- | --- |
| Cenários HTTP completos | 12 aprovados em 184,92 segundos. |
| Chamadas válidas de chat | 14 iniciadas e 14 concluídas. |
| Revisões finais observadas | 13 aprovadas pelo juiz; uma chamada tratou apenas do histórico pela rota geral. |
| Encaminhamentos corretivos nessa rodada final | Nenhum: os rascunhos foram aprovados. |
| Suíte automatizada após a correção encontrada | 241 aprovados, 22 integrações opcionais ignoradas; cobertura 86,73%. |
| Ruff e diff | Aprovados. |

Doze das integrações opcionais ignoradas na suíte padrão são justamente os
cenários HTTP ativados e executados separadamente nesta validação. Os dez testes
anteriores de integração direta MCP/especialistas não foram reativados nesta rodada.

## Cenários completos executados

| Cenário | Verificação |
| --- | --- |
| Saúde da API e corpo HTTP inválido | HTTP 200 para saúde e 422 para corpo sem campos obrigatórios. |
| Explicação de PDCA | Quatro etapas com resposta fundamentada no FAQ. |
| Tarefas atrasadas | Identificou Mapear processo; distinguiu bloqueio de atraso. |
| Meta principal | Base 100%, alvo 80%, sem apresentar alvo como medição atual. |
| Resumo de formulários | Três respostas da fixture, com recorrência de retrabalho em duas delas. |
| Criação de formulário | Um único documento para o título de teste no MongoDB. |
| Formulário com informações ausentes | Pediu título/tipo e não criou documento. |
| Criação e atualização de tarefa | Uma tarefa por título, depois EM_ANDAMENTO, conferido por consulta MCP e no PostgreSQL. |
| Conversa com continuação | Pediu informações, recebeu título/tipo, criou um rascunho e lembrou o título na mensagem seguinte. |
| Prazo de tarefa sem tarefa/data informadas | Pediu os dados; snapshot das tarefas permaneceu idêntico. |
| Contagem e status de tarefas | Informou cinco tarefas no ciclo após as criações de teste; separou status e vencimento corretamente. |
| Alvo planejado versus resultado medido | Informou base 100%, alvo 80% e ausência de medição para confirmar atingimento. |

Na conversa com continuação, o histórico retornado pela própria API teve seis
mensagens: três do usuário e três do assistente. Os rascunhos novos foram
conferidos por título e cada título produziu um único documento. As duas tarefas
criadas em execuções distintas tinham títulos distintos e terminaram em
EM_ANDAMENTO; não eram reenvios automáticos da mesma criação.

## Problema encontrado e corrigido durante o teste real

A primeira execução da pergunta mais ampla sobre metas retornou a mensagem segura.
O JEV rejeitou a requisição com HTTP 400 e `max_tokens_exceeded`. O contexto levava
os resultados completos dentro de cada resposta de especialista e novamente na
lista central, além de resultados idênticos de consultas feitas por mais de um
especialista.

`agents/juiz.py` passou a enviar somente nome/texto dos especialistas e uma cópia
de cada evidência distinta na lista central. O conteúdo integral de cada resultado
distinto permanece disponível; não houve corte arbitrário, resumo das provas ou
relaxamento das validações. Um teste de regressão verifica a preservação integral
do resultado e a ausência de cópias aninhadas/duplicadas.

A mesma requisição passou no reteste e a suíte HTTP completa foi repetida: os 12
cenários passaram juntos, sem novo `max_tokens_exceeded` nos registros do servidor.

## Limites desta evidência

As perguntas normais desta rodada não acionaram `repetir_especialista` ou
`reformular_orquestrador`: o juiz aprovou os rascunhos. Esta validação demonstra o
fluxo completo com entradas reais, persistência e pedidos de informação ausente;
não equivale a forçar cada decisão corretiva. Essas decisões têm testes próprios
em `tests/test_revisao_resposta.py` e o ensaio específico registrado em
`2026-10-29-correcao-resposta.md`.

Arquivos de teste: `tests/test_intention_integration.py` e
`tests/test_chat_flow_integration.py`. O ambiente temporário foi encerrado após a
validação; o contêiner original do usuário foi preservado e as imagens de teste
continuam disponíveis localmente.
