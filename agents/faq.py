"""
Agente FAQ/RAG do Chatbot ACTA.

Responsabilidade:
- Responder perguntas conceituais sobre o ACTA.
- Explicar PDCA, Ishikawa, 5 Porquês, 5W2H, Pareto, lições aprendidas etc.
- Usar a base de conhecimento autorizada através da tool de consulta.
- Não consultar dados reais do ciclo, como tarefas atrasadas, colaboradores ou metas atuais.

Exemplos de perguntas adequadas para este agente:
- "O que é o ACTA?"
- "Como funciona o diagrama de Ishikawa?"
- "O que é 5W2H?"
- "Para que servem as lições aprendidas?"
- "Como funciona a padronização?"
"""

import logging

from agents.helpers.llms import llm_fast
from agents.prompts.prompt_faq import _PROMPT_FAQ
from tools.faq_tools import faq_retriever

logger = logging.getLogger(__name__)


def responder_faq(pergunta: str) -> str:
    """
    Responde uma pergunta conceitual usando a base de conhecimento do ACTA.

    Parâmetros:
        pergunta (str):
            Pergunta enviada pelo usuário.

    Retorno:
        str:
            Resposta final gerada pelo modelo com base no contexto recuperado.
    """

    # Remove espaços extras para evitar perguntas vazias ou mal formatadas.
    pergunta = pergunta.strip()

    if not pergunta:
        return "Não recebi uma pergunta válida para responder."

    try:
        # Busca na base de conhecimento autorizada.
        contexto = faq_retriever.invoke(pergunta)

        # Caso o retriever não encontre nada útil.
        if not contexto or not contexto.strip():
            return (
                "Não encontrei informação suficiente na base do ACTA para responder essa pergunta."
            )

        # Monta o prompt final com o contexto recuperado e a pergunta do usuário.
        prompt = _PROMPT_FAQ.format(contexto=contexto, pergunta=pergunta)

        # Chama o modelo de linguagem para gerar a resposta final.
        resposta = llm_fast.invoke(prompt).content

        # Garante que a resposta não volte com espaços extras.
        return resposta.strip()

    except Exception:
        logger.exception("Falha ao responder pelo especialista FAQ/RAG")
        return (
            "Não consegui consultar a base de conhecimento do ACTA no momento. "
            "Tente novamente em alguns instantes."
        )


# ============================================================
# Teste manual do agente
# ============================================================

if __name__ == "__main__":
    print("Agente FAQ iniciado. Digite 'sair' para encerrar.\n")

    while True:
        pergunta_teste = input("> ").strip()

        if pergunta_teste.lower() in ["sair", "tchau", "exit", "quit"]:
            print("Encerrando FAQ...")
            break

        resposta = responder_faq(pergunta_teste)

        print("\nResposta:")
        print(resposta)
        print()

# aq vc pode mudar a pergunta, se quiser, pode botar um while true aq com break.
# dai pra rodar, faz assim: py -m agents.faq
# vai dar esse warning grande pq eu escolhi um modelo meio ruim, dai ta dando esse warning, mas eu ja tiro.
