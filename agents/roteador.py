"""Roteamento das mensagens para os especialistas do ACTA."""

import logging

from typesafe_sdk import Choice, Noul, TypeSafeClient

from config import JEV_API_KEY

logger = logging.getLogger(__name__)

DESCRICOES_ESPECIALISTAS: dict[str, str] = {
    "rag": (
        "Dúvidas conceituais e explicações que não exigem consultar dados de um ciclo: "
        "o que é o ACTA, como funciona um processo ou recurso e conhecimento documentado. "
        "Exemplos: 'O que é o ACTA?', 'Quais são as etapas do PDCA?', "
        "'Qual etapa do PDCA vem primeiro?' e 'Como funciona a área de tarefas?'. "
        "Perguntas conceituais sobre PDCA pertencem a rag mesmo sem mencionar ACTA."
    ),
    "ciclo": (
        "Somente consultar dados reais registrados para um ciclo específico do ACTA: "
        "fase, status, riscos ou andamento. Não deve ser escolhido para explicar o método "
        "PDCA, suas etapas ou conceitos gerais. Exemplos: 'Como está o ciclo 12?', "
        "'Qual a fase atual do ciclo 12?'"
    ),
    "licoes": (
        "Consultar, resumir, comparar ou registrar lições aprendidas de ciclos. "
        "Não deve ser escolhido para perguntas conceituais sobre PDCA ou referências à "
        "lista de etapas; escolha somente quando a pessoa pedir lições aprendidas ou "
        "registradas nos ciclos do ACTA. Exemplos: 'O que aprendemos no ciclo 1?', "
        "'Quais lições foram registradas?'"
    ),
    "tarefas": (
        "Consultar ou acompanhar tarefas registradas: responsáveis, prazos, atrasos, "
        "dependências ou justificativas. Exemplos: 'Quais tarefas estão atrasadas?'"
    ),
    "colaboradores": (
        "Consultar colaboradores, competências, disponibilidade, carga ou realocação. "
        "Exemplos: 'Quem está disponível?', 'Como está a carga da equipe?'"
    ),
    "formularios": (
        "Consultar formulários respondidos, respostas, padrões ou ocorrências registradas. "
        "Exemplos: 'Quais ocorrências apareceram nas respostas?'"
    ),
    "indicadores": (
        "Consultar metas, indicadores, valores base ou alvo, atingimento e limitações "
        "de medição. Exemplos: 'Qual o atingimento da meta?'"
    ),
    "relatorios": (
        "Preparar contexto, resumo ou relatório usando dados registrados do ACTA. "
        "Exemplos: 'Gere um resumo do ciclo'"
    ),
}


def rotear(pergunta: str, contexto_conversa: str) -> dict:
    """Seleciona a rota, os especialistas e o escopo de ciclos com JEV."""

    try:
        with TypeSafeClient(api_key=JEV_API_KEY) as client:
            routing = client.system_one(
                state={
                    "mensagem_usuario": pergunta,
                    "contexto_conversa": contexto_conversa,
                },
                questions={
                    "tipo_mensagem": Choice(
                        instructions=(
                            "Classifique a mensagem atual considerando o contexto recente, "
                            "quando houver. Mensagens de continuação herdam o assunto anterior. "
                            "Use conversa somente para saudações, agradecimentos, conversa casual "
                            "e perguntas sobre o histórico. Pedidos concretos fora do ACTA não são "
                            "conversa, mesmo que possam ser respondidos com conhecimento geral."
                        ),
                        criteria={
                            "conversa": (
                                "Somente saudação, agradecimento, conversa casual ou pergunta "
                                "sobre o histórico desta conversa. Não inclua pedidos de conteúdo, "
                                "código, receitas, recomendações ou informações gerais."
                            ),
                            "negocio": "Solicitação relacionada ao ACTA.",
                            "fora_escopo": (
                                "Qualquer pedido concreto não relacionado ao ACTA, seus recursos "
                                "ou PDCA, incluindo código, receitas, recomendações e conteúdo "
                                "geral. Use esta categoria para impedir que o pedido seja respondido."
                            ),
                        },
                    ),
                    "escopo_ciclos": Choice(
                        instructions=(
                            "Determine o escopo de ciclos necessário considerando também "
                            "o contexto recente da conversa."
                        ),
                        criteria={
                            "ativo": "Consulta referente a um único ciclo ativo ou pedido singular.",
                            "todos": "Consulta que precisa considerar todos os ciclos disponíveis.",
                            "comparacao": "Consulta que compara dois ou mais ciclos entre si.",
                        },
                    ),
                    **{
                        name: Noul(
                            instructions=(
                                "A mensagem atual, considerando o contexto recente, deve ser "
                                "encaminhada a este especialista? Só marque quando houver relação "
                                "direta com o ACTA e com este domínio. Nunca encaminhe pedidos "
                                "fora do ACTA, como código ou receita. Considere o contexto para "
                                f"mensagens curtas de continuação. Domínio e exemplos: {description}"
                            ),
                        )
                        for name, description in DESCRICOES_ESPECIALISTAS.items()
                    },
                },
            )
            message_type = routing.choices["tipo_mensagem"].choice
            if message_type == "conversa":
                return {
                    "rota": "resposta_geral",
                }
            if message_type == "fora_escopo":
                logger.info("Mensagem classificada fora do escopo do ACTA")
                return {"rota": "fora_escopo"}
            if message_type != "negocio":
                return {"rota": "falha_classificacao"}

    except Exception:  # noqa: BLE001 - o guardrail já aprovou a entrada
        logger.exception("Falha na triagem do JEV; bloqueando resposta sem escopo validado")
        return {"rota": "falha_classificacao"}

    # Os Noul retornam probabilidades; 0.5 separa especialistas relevantes dos demais.
    selected = [
        name
        for name in DESCRICOES_ESPECIALISTAS
        if routing.nouls[name].noul >= 0.5
    ]
    scores = {
        name: float(routing.nouls[name].noul)
        for name in DESCRICOES_ESPECIALISTAS
    }
    logger.warning(
        "Roteamento JEV: tipo=%s escopo=%s notas={%s} selecionados=%s",
        message_type,
        routing.choices["escopo_ciclos"].choice,
        ", ".join(f"{name}={score:.2f}" for name, score in scores.items()),
        selected,
    )
    if not selected:
        return {"rota": "escopo_nao_identificado"}

    return {
        "rota": "especialistas",
        "especialistas": selected,
        "escopo_ciclos": routing.choices["escopo_ciclos"].choice,
    }
