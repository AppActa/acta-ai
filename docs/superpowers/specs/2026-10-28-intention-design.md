# SDD: intenções de transação

Escopo final: somente operações de domínio dos especialistas que alteram o banco. Consultas, FAQ e leituras de lições continuam no fluxo atual. Memória, histórico e skills são capacidades internas da aplicação, fora desse gate de domínio.

## Contrato

O tool_call estruturado vira uma intenção antes do envio ao MCP:

```json
{"tool": "formularios_criar_rascunho", "argumentos": {"id_ciclo": 1, "titulo": "Análise", "tipo": "ANALISE_FENOMENO"}}
```

O juiz recebe pergunta, histórico recente, ciclos autorizados, schema, intenção efetiva com defaults resolvidos e evidências reais. Retorna:

```json
{"decisao": "aprovada", "apoio": 0.9, "motivo": "Pedido explícito e completo.", "pergunta": null}
```

Schemas estritos: campos extras proibidos; motivo não vazio; apoio numérico finito entre 0 e 1, sem booleano ou string. Pedir esclarecimento exige pergunta não vazia; demais decisões exigem pergunta nula. Conteúdo recebido é dado não confiável, nunca instrução.

## Política

| Resultado | Ação |
| --- | --- |
| aprovada e apoio >= 0.7 | Executar o payload exato avaliado. |
| aprovada e apoio < 0.7 | Interromper sem executar a proposta. |
| corrigir_proposta | Retornar motivo e intenção ao especialista, sem executar. |
| pedir_esclarecimento | Encerrar com pergunta ao usuário, sem executar a proposta. |
| Inválido, contraditório ou falha do juiz | Interromper sem executar a proposta. |

Duas correções além da proposta inicial: no máximo três avaliações por ação. Sem reiniciar o agente inteiro ou repetir ações anteriores. Se o especialista terminar com correção pendente, bloquear. Limites isolados por especialista/rodada, com no máximo dez escritas aprovadas.

## Execução

Reaproveitar create_agent e tool_calls. O gate fica em call_acta_tool depois de defaults/contexto dos wrappers e antes de cache/rede. Uma lista fechada identifica consultas. Demais ferramentas exigem contexto de transações, schema conhecido e autorização do especialista; desconhecidas são bloqueadas.

Escritas não usam cache ou retry de transporte. Consultas preservam ambos. Lotes com múltiplas tool_calls contendo escrita são bloqueados antes de qualquer despacho. Especialistas são sequenciais para impedir iniciar os demais após esclarecimento/bloqueio.

O juiz de intenção usa saída estruturada do modelo existente. O juiz final JEV e o guardrail permanecem. A autorização efetiva de empresa/usuário/recurso continua no MCP. Apoio é pontuação semântica, não probabilidade calibrada. Não há rollback de ações já concluídas.

## Aceitação

1. Apoio 0.69 bloqueia; 0.70 e 1.0 executam uma vez.
2. Corrigir e aprovar executa somente os argumentos corrigidos.
3. Três pedidos de correção encerram sem escrita.
4. Esclarecimento chega ao usuário e interrompe novas ações da rodada.
5. Juiz inválido/contraditório/indisponível não gera envio de escrita.
6. Schema inválido, ferramenta desconhecida ou fora do especialista bloqueiam.
7. Consultas não recebem juiz de intenção.
8. Escrita direta sem contexto não contorna o gate; escrita não usa cache.
9. Timeout de escrita não provoca reenvio automático.
10. Contextos/limites não vazam entre rodadas.
11. Testes reais verificam API, consultas e criação única em fixtures Docker, além de pedido incompleto sem criação.

Sem novo banco, serviço, dependência ou nós no grafo. A proposta transacional não precisa de um executor manual adicional: a estrutura nativa da chamada já fornece ferramenta e argumentos.
