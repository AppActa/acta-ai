# Validação: intenções de transação

Data: 28/10/2026. Escopo: alterações de domínio no banco; consultas sem juiz de intenção.

## Revalidação em Docker — 28/10/2026

A nova tentativa conseguiu construir as duas imagens pelos Dockerfiles atuais,
sem reutilizar a imagem antiga ou montar o código da aplicação no runtime:

- `acta-ai:intention-test` — imagem `8903f42c25e5`, com dependências do lockfile.
- `acta-mcp:intention-test` — imagem `e9a5ea2d58cd`, construída no repositório MCP.

API, MCP, PostgreSQL e MongoDB executaram em contêineres na mesma rede de teste.
Somente o cliente que enviou as requisições HTTP executou no Windows. O JEV
respondeu a partir do contêiner, e a comunicação API → MCP respondeu HTTP 200.

| Verificação no novo ambiente Docker | Resultado |
| --- | --- |
| Construção da imagem ACTA AI | Aprovada. |
| Construção da imagem MCP | Aprovada. |
| Ruff e suíte automatizada dentro de contêiner Linux/Python 3.14.10 | 216 aprovados, 18 integrações opcionais ignoradas nessa execução; cobertura 86,00%. |
| Primeira rodada HTTP completa | 7 aprovados e 1 falho, em 124,55 segundos. |
| Diagnóstico da atualização dentro do contêiner | Proposta aprovada com apoio 1.0 e alteração confirmada no PostgreSQL. |
| Reteste HTTP de criação e atualização de uma tarefa nova | Aprovado em 40,71 segundos; status final EM_ANDAMENTO. |

Assim, os oito cenários HTTP foram aprovados no Docker considerando a rodada
inicial e o reteste direcionado. Na tentativa inicialmente falha, a tarefa foi
criada, mas a atualização recebeu um bloqueio seguro e permaneceu pendente.
Esse bloqueio não foi reproduzido em dois diagnósticos nem no reteste HTTP com
uma tarefa nova. Os logs da primeira chamada não permitiram determinar sua
origem exata; não foi considerado erro de rede nem uma falha corrigida no código.

Também foi conferido diretamente nos bancos: um único rascunho para o título de
teste e a tarefa nova com status EM_ANDAMENTO. O pedido incompleto não criou
formulário. Nenhuma regra do juiz foi relaxada para obter esses resultados.

Não foi necessário alterar código da aplicação nesta nova tentativa. O `.env`
do MCP continha um nome de variável com espaço, rejeitado por `docker --env-file`;
as credenciais necessárias foram carregadas com o parser dotenv e repassadas
ao contêiner, sem modificar o arquivo original nem imprimir segredos.

As imagens novas permanecem disponíveis localmente. Os contêineres e bancos
temporários foram encerrados após a validação; o contêiner original foi preservado.

## Resultado da primeira validação

| Verificação | Resultado |
| --- | --- |
| Suíte automatizada completa | 216 aprovados; 18 integrações opcionais ignoradas nessa execução. |
| Cobertura | 86,00%, acima dos 80% exigidos pelo Makefile. |
| Ruff | Aprovado. |
| Lockfile (`uv lock --check`) | Aprovado, sem novas dependências. |
| Diff (`git diff --check`) | Aprovado. |
| Integrações existentes MCP/especialistas, ativadas separadamente | 10 aprovadas. |
| HTTP real: saúde/validação, FAQ, tarefas atrasadas, metas, formulários, criação de rascunho e pedido incompleto | 7 aprovados na rodada final (54,83 segundos). |
| HTTP real: criação e atualização de status de tarefa | 1 aprovado, em execução separada (33,66 segundos). |

Os 18 testes opcionais ignorados na suíte padrão correspondem aos 10 de MCP/especialistas e aos 8 novos de HTTP. Foram ativados e executados separadamente; não se trata de verificações omitidas.

## Evidências funcionais

- Aprovação exige apoio >= 0.7: 0.69 bloqueia, 0.70 e 1.0 executam.
- Duas correções permitem até três avaliações. Somente a proposta corrigida e aprovada chega ao transporte.
- Juiz inválido, contraditório ou indisponível não envia escrita.
- Esclarecimento interrompe os demais especialistas e preserva a pergunta, sem síntese que invente execução.
- Consultas não recebem avaliação de intenção; mantêm cache e retries de transporte.
- Escritas sem contexto, fora das ferramentas do especialista ou com schema inválido são bloqueadas; desconhecidas também.
- Escritas não usam cache e não recebem retry de transporte, incluindo timeout ambíguo.
- Um agente LangChain real com modelo simulado recebeu corrigir_proposta, propôs os novos argumentos e executou uma única escrita aprovada.
- Lote com múltiplas tool_calls contendo escrita foi bloqueado antes de qualquer despacho.
- O juiz real recebeu uma proposta de criar formulário para um pedido que autorizava apenas consulta. Respondeu corrigir_proposta, apoio 0.99, indicando trocar pela consulta; nenhuma ferramenta foi executada nessa verificação semântica.
- Na API real, cada título único de formulário produziu exatamente um documento de rascunho no MongoDB local. O pedido incompleto perguntou título/tipo e não criou documento.
- A tarefa de teste foi criada uma única vez no PostgreSQL local, com prazo 31/12/2026. A atualização foi confirmada por consulta MCP e diretamente no PostgreSQL: status final EM_ANDAMENTO.
- As respostas de consultas reais corresponderam às fixtures: tarefa Mapear processo atrasada; meta com base 100 e alvo 80; três respostas de formulário com recorrência de retrabalho em duas delas.

## Correções demonstradas pelos testes

1. O roteador descrevia alguns domínios somente como consulta e não encaminhava criação de formulário. As descrições agora incluem as escritas oferecidas pelos especialistas.
2. Os wrappers de detalhe/atualização/status de tarefas não enviavam id_ciclo, exigido pelo MCP atual. O argumento passou a ser explícito, mantendo o isolamento de ciclos.
3. Algumas respostas do modelo vinham em blocos de texto. A extração agora usa o texto da mensagem LangChain, evitando devolver a representação interna dos blocos ao usuário.
4. As integrações antigas passavam id_ciclo como inteiro diretamente no estado interno. Foram alinhadas ao contrato atual de lista; a compatibilidade HTTP com inteiro permanece testada.
5. Testes unitários não ativam tracing externo por padrão.

## Ambiente e limitações observadas

Foram usados PostgreSQL e MongoDB de fixtures em um projeto Docker Compose separado, MCP local em :8001 e API local em :8201. As alterações de domínio foram feitas somente nesses bancos de teste. A configuração .env real não foi modificada.

Ao terminar, os processos e contêineres temporários criados para essa validação foram encerrados e removidos. O contêiner original do usuário foi preservado.

A criação de uma nova imagem falhou no acesso ao Docker Hub, com TLS handshake timeout. Para testar o runtime em Docker, foi usada a imagem local existente com o código atualizado montado como somente leitura. O contêiner iniciou e respondeu ao health check, mas apresentou falhas de conexão de saída/timeout com o JEV. A suíte HTTP completa nesse contêiner não passou: 2 aprovados e 6 falhos por bloqueios nas validações externas, sem criação dos registros esperados.

O caminho completo foi então verificado com a API executando localmente e os mesmos bancos Docker: os 8 cenários HTTP passaram em dois grupos. Também houve um timeout intermitente do JEV em uma rodada local anterior; a repetição final passou. Essas falhas de infraestrutura não foram transformadas em aprovações ou contornadas no produto.

Permanecem avisos de depreciação das dependências Google GenAI/Python e do cliente MCP Streamable HTTP. Nenhuma dependência foi trocada nesta entrega.

Não há rollback de ações anteriores já concluídas. Apoio é uma pontuação semântica; a autorização efetiva continua sendo aplicada pelo MCP. Histórico, memória e skills internas continuam fora do gate de transações de domínio.
