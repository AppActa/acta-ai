_PADROES_INJECAO = [
    r"ignore\s+(as\s+)?instru[çc][oõ]es",
    r"ignore\s+previous\s+instructions",
    r"forget\s+your\s+instructions",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(if\s+)?",
    r"pretend\s+(you\s+are|to\s+be)",
    r"jailbreak",
    r"dan\s+mode",
    r"modo\s+irrestrito",
    r"system\s*prompt",
    r"<\s*system\s*>",
    r"\[INST\]",
    r"###\s*instruction",
    r"override\s+(your\s+)?instructions",
    r"desconsider[ea]\s+(suas\s+)?instru[çc][oõ]es",
    r"im your developer",
    r"sou seu criador",
    r"since i created you",
    r"i am your (creator|developer|programmer|engineer)",
    r"i created you",
]
_KEYWORDS_DADOS_INTERNOS = [
    "prompt do sistema",
    "system prompt",
    "suas instruções",
    "your instructions",
    "variável de ambiente",
    "chave de api",
    "api key",
    "senha do sistema",
    "token de acesso",
    "infraestrutura interna",
    "organização interna dos dados",
    "dados de outros clientes",
    "lista de clientes",
    "credenciais",
]
_PROMPT_GUARDRAIL = """\
Você é um classificador de segurança de um aplicativo gerenciador de ciclos PDCA.
Classifique a mensagem em UMA categoria. Responda SOMENTE:

CATEGORIA: [categoria]
JUSTIFICATIVA: [uma linha]

Categorias:
APROVADO        - mensagem legítima sobre o ciclo PDCA (informativa) ou operações sobre o aplicativo
OFENSIVO        - xingamentos, assédio, discurso de ódio
PERIGOSO        - instruções que causam dano físico, psicológico ou coletivo
ILICITO         - pedido de auxílio para atividades ilegais ou fraudulentas
POLITICO        - opiniões ou debates políticos, partidos, eleições

Mensagem: {mensagem}
"""

_RESPOSTAS_BLOQUEIO = {
    "OFENSIVO": (
        "conteudo_ofensivo",
        "Por favor, não utilize linguagem ofensiva ou discriminatória e assim poderemos seguir com a conversa.",
    ),
    "PERIGOSO": ("pedido_perigoso", "Não posso ajudar com esse tipo de solicitação."),
    "ILICITO": ("pedido_ilicito", "Não posso auxiliar com atividades ilegais ou irregulares."),
    "POLITICO": (
        "pergunta_politica",
        "Não me envolvo em temas políticos. Posso te ajudar com o funcionamento do ACTA, dúvidas sobre o ciclo PDCA ou operações no aplicativo.",
    ),
}

_PROMPT_COMPLIANCE = """\
Você é um revisor de compliance de um aplicativo gerenciador de ciclos PDCA. Sua função é revisar a resposta de um especialista antes de entregar ao usuário final, garantindo que não haja informações pessoais, sensíveis ou que violem as políticas de uso do aplicativo.
Responda SOMENTE:
STATUS: APROVADO ou CORRIGIDO
RESPOSTA:
[texto final]

Resposta para revisar:
{resposta}
"""
