# SDD: correção da resposta antes da entrega

## Objetivo

Recuperar respostas reprovadas pelo juiz final, preservando a validação de
intenções de escrita existente e sem repetir transações concluídas.

## Decisões

- Falta de evidência ou análise incorreta: repetir somente o especialista responsável, enviando feedback e evidências anteriores.
- Evidências e especialistas corretos, síntese errada: pedir reformulação somente ao orquestrador.
- Informação obrigatória depende do usuário: gerar pergunta, revisar no guardrail e aguardar resposta sem novas ações.
- Juiz indisponível, encaminhamento inválido ou correção impossível: encerrar com mensagem segura.

O JEV continua responsável por aprovar a resposta. Se ele reprovar, o modelo
existente produz `CorrecaoResposta`, com ação, especialista, feedback e pergunta.
Essa estrutura só encaminha: não aprova respostas nem executa ferramentas.

## Limites e segurança

- `ACTA_RESPONSE_MAX_RETRIES=2`: no máximo três avaliações da resposta, com duas correções no total.
- Toda correção passa novamente por guardrail e juiz; nenhum rascunho rejeitado é persistido como resposta final.
- A revisão de especialista permite somente leitura; o cliente bloqueia qualquer escrita antes de sua avaliação/envio.
- Consultas de revisão têm cache novo, mantendo o contexto autenticado e o escopo de ciclos.
- Preservar comprovantes de escrita e as respostas dos especialistas não envolvidos. Para a mesma consulta, usar a evidência mais recente.
- Ausência de registros confirmada pela ferramenta é uma limitação factual, não motivo para repetir indefinidamente.

## Implementação

Reaproveitar o nó `no_juiz` com um ciclo local limitado, a síntese do orquestrador,
os especialistas existentes e o cliente MCP. Sem novos nós no grafo, serviços ou
dependências. Alterar `agents/juiz.py`, `agents/estado.py`, `agents/execucao.py`,
o feedback do FAQ em `agents/agents.py`, configuração e testes relacionados.

## Aceitação

1. Reformulação do orquestrador não executa especialistas ou ferramentas.
2. Repetição executa apenas o especialista indicado e inclui o feedback.
3. Provas de operações anteriores permanecem disponíveis e leituras atualizadas substituem as antigas.
4. Esclarecimento não executa ferramentas e passa pelo guardrail.
5. Duas correções esgotadas, encaminhamento contraditório ou falha do juiz não entregam o rascunho rejeitado.
6. Mesmo com contexto transacional válido, uma escrita é bloqueada durante a revisão.
