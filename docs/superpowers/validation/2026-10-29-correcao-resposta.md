# Validação: correção da resposta final

Data: 29/10/2026.

## Resultado

- Suíte completa local: 240 aprovados, 18 integrações opcionais ignoradas, cobertura 86,69%.
- Mesma suíte dentro da imagem Docker final, Linux/Python 3.14.10: 240 aprovados, 18 ignorados, cobertura 86,69%.
- Ruff, verificação de diff e lockfile aprovados. Sem dependências novas.
- Imagem `acta-ai:response-review-test` construída pelo Dockerfile existente, identificação `426ab0866a2f`.
- Teste específico com MCP, MongoDB e PostgreSQL de fixtures no Docker e provedores reais do juiz e do orquestrador: aprovado.

Os 18 testes opcionais antigos de HTTP/MCP/especialistas não foram reativados
nesta rodada. O teste real desta adição exercitou especificamente o nó final de
revisão, com evidência obtida do MCP e persistência real no MongoDB local.

## Cenários automatizados da adição

- Falta de evidência ou resposta incorreta encaminha apenas o especialista indicado, com feedback.
- Correção apenas da síntese chama o orquestrador sem executar especialistas.
- Informação do usuário ausente gera pergunta revisada no guardrail, sem ferramentas.
- Cada novo rascunho passa pelo guardrail e pelo juiz novamente.
- Duas correções esgotadas encerram com mensagem segura; somente a resposta entregue é persistida.
- Resultado de encaminhamento inválido/contraditório, especialista desconhecido e falhas dos modelos não geram nova execução.
- Uma proposta de escrita com argumentos válidos é bloqueada na revisão antes do juiz de intenção e do transporte.
- O contexto de somente leitura é limpo mesmo em exceções.
- Consultas refeitas usam cache novo e substituem as evidências antigas da mesma chamada.
- Comprovantes de escritas anteriores são preservados, assim como os resultados dos demais especialistas.
- A revisão de lições mantém todos os ciclos de uma comparação e encaminha o feedback à consulta.

## Teste real no Docker

1. Consultou `tarefas_consultar` no MCP, com usuário/empresa 1 e ciclo autorizado 1.
2. A fixture retornou contagem real de 3 tarefas. A resposta do especialista dizia 3.
3. Injetou deliberadamente um rascunho incorreto do orquestrador: “Existem 999 tarefas.”
4. O JEV reprovou o rascunho; o encaminhamento estruturado indicou `reformular_orquestrador`.
5. O orquestrador reformulou para “Existem 3 tarefas no ciclo ativo.”
6. Guardrail e JEV aprovaram a nova resposta.
7. Conferiu apenas uma chamada MCP no total: a consulta inicial. A reformulação não fez novas consultas nem escritas de domínio.
8. Conferiu uma única mensagem persistida no MongoDB: a resposta final.

Saída da imagem final:

```json
{
  "avaliacoes": [
    {"status": "CORRIGIR", "acao": "reformular_orquestrador"},
    {"status": "APROVADO", "acao": null}
  ],
  "resposta": "Existem 3 tarefas no ciclo ativo.",
  "contagem_real": 3,
  "chamadas_mcp": 1,
  "mensagens_persistidas": 1
}
```

## Limitações e ambiente

Uma tentativa começou antes de o MCP terminar a inicialização; após verificar o
health check, a repetição passou. Em outra tentativa houve falha de DNS ao acessar
o JEV: a aplicação retornou a mensagem segura e não tentou corrigir/aprovar o
rascunho sem avaliação. A repetição final com o serviço acessível passou. As
validações não foram desativadas para contornar falhas de infraestrutura.

O encaminhamento é semântico e pode falhar; saída inválida ou erro do juiz encerra
com segurança. O limite padrão é de duas correções no total por rodada, separado
do limite de correções das intenções de escrita. Não há rollback de operações
anteriores já concluídas.

Foram usados somente bancos locais de fixtures. Os contêineres temporários foram
encerrados ao final; a imagem de teste permanece disponível localmente.
