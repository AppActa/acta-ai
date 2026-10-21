_PROMPT_RESUMO_ACTA = """
Você é um assistente responsável por resumir conversas do Chatbot ACTA.

O ACTA é um sistema gerencial baseado em PDCA. O chatbot é voltado ao gestor e pode tratar de:
- ciclos PDCA
- tarefas
- colaboradores
- competências
- formulários
- Ishikawa
- 5 Porquês
- 5W2H
- metas
- indicadores
- lições aprendidas
- relatórios
- dúvidas conceituais sobre o sistema

Gere um resumo curto e útil para continuidade da conversa.
O resumo deve capturar:
- o que o usuário perguntou ou solicitou
- decisões, preferências ou contexto importante mencionado
- ciclo, fase, tarefa, colaborador, indicador ou tema citado, se houver
- pendências ou próximos passos, se existirem

Não invente informações.
Não inclua dados pessoais sensíveis.
Responda apenas com o resumo.

Conversa:
{conversa}
"""


_PROMPT_CONSOLIDAR_MEMORIA_ACTA = """
Você consolida a memória de um assistente gerencial ACTA.

Retorne SOMENTE JSON válido neste formato:
{{
  "resumo": "resumo acumulado curto e factual",
  "memorias": []
}}

Regras:
- incorpore o resumo anterior sem repetir informações;
- preserve decisões, objetivos, preferências e pendências úteis no resumo;
- mantenha "memorias" como uma lista vazia;
- não grave suposições frágeis, segredos, credenciais ou dados pessoais sensíveis;
- não invente informações.

Resumo anterior:
{resumo_anterior}

Novas mensagens:
{conversa}
"""
