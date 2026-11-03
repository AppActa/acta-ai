# Intenções de transação — Implementation Plan

> **For agentic workers:** Executar na sessão atual, conforme a especificação e os critérios de aceitação. Delegação não é necessária.

**Goal:** Validar somente escritas dos especialistas antes de alterar dados.

**Architecture:** Reaproveitar create_agent e tool_calls. O cliente MCP converte escritas em intenção e aplica a decisão antes do envio; correções retornam como resultado não executado da ferramenta.

**Tech Stack:** Python, Pydantic, LangChain/LangGraph e pytest existentes.

**Spec:** `docs/superpowers/specs/2026-10-28-intention-design.md`.

## Global Constraints

- Apenas alterações no banco; consultas sem juiz de intenção.
- Apoio mínimo 0.7; duas correções além da proposta inicial.
- Falha, contradição ou resultado inválido não executa proposta.
- Sem cache/retry de transporte em escrita; sem novas dependências.

## Arquivos, alterações e motivos

| Arquivo | Alteração | Por quê / simplicidade |
| --- | --- | --- |
| `agents/intencao.py` — novo | Schemas Intention/AvaliacaoIntencao, limites e exceções. | Contrato estrito e compartilhado. |
| `agents/execucao.py` — novo | Contexto local, lista de consultas, validação de escrita, limites e bloqueio de lote. | Um gate comum, sem novo subgrafo. |
| `agents/juiz.py` | Nova avaliar_intencao; manter avaliar_resposta/JEV. | Separar revisão da ação e do texto no módulo existente. |
| `clients/mcp_acta_client.py` | Aplicar gate antes de escrita; sem cache ou retry de escrita. | Cobrir wrappers e chamadas diretas. |
| `agents/agents.py` | Listas por especialista e middleware que bloqueia lote com escrita. | Reutilizar agentes e ferramentas existentes. |
| `agents/estado.py` | Contexto transacional por especialista; sequência; tratar bloqueio/esclarecimento e registrar intenções. | Interromper novas ações e preservar pergunta do juiz. |
| `agents/roteador.py` | Incluir escritas nas descrições de ciclos, tarefas e formulários. | Teste real demonstrou que descrições só de consulta impediam criação. |
| `tools/licoes_tools.py` | Escrita de lição com nome MCP e id_ciclo explícito. | Juiz vê todos os argumentos efetivos; leituras preservadas. |
| `tools/tarefas_tools.py` | Incluir id_ciclo em detalhe, atualização e mudança de status. | Alinhar ao contrato real do MCP e manter o escopo de ciclos nas transações. |
| `config.py`, `.env.example` | ACTA_INTENTION_MAX_RETRIES=2, inteiro >=0. | Configuração simples e separada do retry de rede. |
| `tests/test_intencao.py` — novo | Apoio, campos extras e contradições. | Garantir contrato da decisão. |
| `tests/test_execucao_intencao.py` — novo | Gate, correções, bloqueios, limites, consultas livres e ciclo real create_agent com modelo simulado. | Verificar chamadas efetivas, não apenas mensagens. |
| `tests/test_intention_integration.py` — novo | HTTP e perguntas reais contra fixtures locais. | Provar consulta e criação única no banco. |
| `tests/test_juiz.py` | Avaliação estruturada, contexto e falha do juiz. | Verificar integração do novo juiz. |
| `tests/test_optimizations.py`, `tests/test_licoes_tools.py` | Adequar sequência, ferramenta de leitura e ciclo explícito. | Atualizar contratos afetados sem enfraquecer segurança. |
| `tests/test_pipeline.py`, `tests/test_specialists_integration.py`, `tests/test_system_owned_features.py` | Regressão de texto multimodal, mensagens reais do LangChain e estado de ciclo no formato atual. | Problemas observados nas verificações reais, sem alterar a API. |
| `docs/arquitetura.md`, `docs/configuracao.md`, `README.md` | Fluxo de escrita e configuração. | Evitar documentação desatualizada. |

## Etapas

- [x] Criar testes de schema; confirmar falha antes de implementar os contratos.
- [x] Implementar schemas, constantes e configuração; testar com `python -m pytest tests/test_intencao.py -q`.
- [x] Adicionar avaliar_intencao com saída estruturada, proteção de PII e sem ferramentas disponíveis.
- [x] Normalizar argumentos antes da avaliação; executar exatamente a intenção aprovada.
- [x] Retornar correções ao especialista sem execução; encerrar no terceiro pedido de correção.
- [x] Bloquear em juiz inválido/falha e propagar pergunta em esclarecimento.
- [x] Exigir contexto/schema/ferramenta autorizada e bloquear operações desconhecidas.
- [x] Remover cache/retry de escrita, preservando consultas.
- [x] Integrar contexto e tratamento de interrupções em executar_especialistas.
- [x] Bloquear lotes com escrita antes do despacho e expor ciclo explícito em criação de lições.
- [x] Rodar grupos afetados: `python -m pytest tests/test_execucao_intencao.py tests/test_juiz.py tests/test_licoes_tools.py tests/test_optimizations.py -q`.
- [x] Iniciar PostgreSQL/MongoDB locais por Docker Compose do MCP em projeto de teste separado, MCP em :8001 e API em :8201.
- [x] Testar HTTP inválido, FAQ, atrasos, metas, formulários e pedido incompleto; verificar criação única no MongoDB local.
- [x] Ativar integrações existentes de MCP/especialistas e registrar limitações reais.
- [x] Rodar Ruff, lock check e suíte completa com cobertura >=80%, conforme Makefile.
- [x] Atualizar documentação e registrar os resultados.

## Pode ser mais simples?

O escopo de escritas permite manter os agentes existentes, dispensando o executor manual e o julgamento de consultas do plano original. Não adicionar filas, serviços, rollback, auditoria persistente ou novos nós do grafo. O gate no cliente é necessário para impedir chamadas diretas sem validação.

## Execução concluída

Resultados e limitações: [relatório de validação](../validation/2026-10-28-intention.md).
