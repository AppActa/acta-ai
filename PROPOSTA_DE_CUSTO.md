# Proposta de custo

## Premissas

- Cada usuário faz **10 conversas por semana**.
- Para esta estimativa, cada conversa conta como um turno que chama o assistente.
- Consideramos **5% de erro** nas solicitações.
- Cada requisição gera valor equivalente a **1,25× o custo**.
- Para estimar resoluções, usamos **15% das solicitações sem erro**. É uma referência de suporte técnico por bot sozinho do benchmark de conversas da Contentsquare de 2026, baseado em dados de 2025. Essa taxa é uma hipótese inicial para o ACTA, não um resultado medido no produto.
- A média do GPT-6 Luna veio do LangSmith, considerando traces LangGraph com mais de 3 segundos: **5.916 tokens por turno** (5.765 de entrada e 151 de saída).
- Preço do GPT-6 Luna: **US$ 0,10 por milhão de tokens de entrada** e **US$ 0,50 por milhão de tokens de saída**.
- Preço do JEV: **US$ 0,042 por milhão de tokens de entrada**; a saída é gratuita.

## Custo JEV por etapa

Medi uma chamada de exemplo para cada etapa, com os prompts do código e dados fictícios. O custo varia com o tamanho da mensagem, do histórico e das evidências enviadas.

| Etapa | Tokens de entrada | Custo por chamada |
| --- | ---: | ---: |
| Guardrail de entrada | 466 | US$ 0,00001957 |
| Roteador | 1.944 | US$ 0,00008165 |
| Guardrail de saída | 474 | US$ 0,00001991 |
| Juiz | 830 | US$ 0,00003486 |
| **Fluxo completo de exemplo** | **3.714** | **US$ 0,00015599** |

A medição representa uma chamada por etapa em um fluxo simples. Conversas com mais histórico, mais evidências, tentativas adicionais ou caminhos diferentes podem custar mais.

## Estimativa semanal

Aplicamos o custo medido de um fluxo JEV de exemplo a cada conversa e somamos ao custo médio do GPT-6 Luna.

| Usuários | Conversas | Erros (5%) | Resoluções | Custo semanal | Valor estimado (1,25×) | ROI |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 1.000 | 50 | 143 | US$ 0,81 | US$ 1,01 | **25%** |
| 1.000 | 10.000 | 500 | 1.425 | US$ 8,08 | US$ 10,10 | **25%** |

O custo combinado estimado por resolução é aproximadamente **US$ 0,0057**.

## Estimativa mensal

Valores calculados com **52 semanas ÷ 12 meses** (aproximadamente 4,33 semanas por mês).

| Usuários | Custo mensal | Valor estimado (1,25×) | ROI |
| ---: | ---: | ---: | ---: |
| 100 | US$ 3,50 | US$ 4,38 | **25%** |
| 1.000 | US$ 35,01 | US$ 43,76 | **25%** |


## Observações

- Aplicamos o custo médio de um fluxo completo a todas as conversas, inclusive às 5% que podem falhar. Uma falha no começo pode consumir menos.
- Os custos não incluem hospedagem, banco de dados e outros serviços externos.
- Se houver mais de um turno por conversa, o custo aumenta proporcionalmente.
