import os
import re
import uuid

from agents.helpers.llms import llm_fast
from agents.prompts.prompt_guardrail import (
    _KEYWORDS_DADOS_INTERNOS,
    _PADROES_INJECAO,
    _PROMPT_COMPLIANCE,
    _PROMPT_GUARDRAIL,
    _RESPOSTAS_BLOQUEIO,
)

llm = llm_fast

# A remoção de PII abaixo é sempre executada. A segunda revisão por LLM é
# opcional porque acrescenta uma chamada sequencial a toda resposta do chatbot.
LLM_OUTPUT_REVIEW = os.getenv("ACTA_GUARDRAIL_LLM_OUTPUT", "false").lower() == "true"


PII = [
    ("CPF", r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"),
    ("CNPJ", r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}"),
    ("TELEFONE", r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}"),
    (
        "EMAIL",
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    ),  # TBD: Encontrar possíveis PIIs para encaixar aqui
]


def _bloquear(motivo, mensagem):
    return {"valido": False, "motivo": motivo, "mensagem": mensagem}


def _aprovado():
    return {"valido": True, "motivo": "aprovado", "mensagem": ""}


def _saida_ok(conteudo):
    return {"valido": True, "motivo": "saida_revisada", "mensagem": conteudo}


def anonimizar_entrada(texto):
    mapa = {}

    for tipo, padrao in PII:
        matches = re.findall(padrao, texto)
        for valor in matches:
            token = f"[PII_{tipo}_{uuid.uuid4().hex[:6]}]"
            mapa[token] = valor
            texto = texto.replace(valor, token, 1)

    return texto, mapa


def desanonimizar_saida(texto, mapa, restaurar=False):
    """Resolve tokens de PII na saída. Por padrão omite — não repete dado pessoal."""
    for token, valor in mapa.items():
        if token in texto:
            substituto = valor if restaurar else f"[{token.split('_')[1]} OMITIDO]"
            texto = texto.replace(token, substituto)
    return texto


def guardrail_entrada(mensagem_anonimizada):
    """
    Executa as verificações de entrada em ordem de custo crescente:
    determinístico primeiro, LLM só se necessário.
    Retorna dict com bloqueado, motivo e mensagem.
    """
    for padrao in _PADROES_INJECAO:
        if re.search(padrao, mensagem_anonimizada, re.IGNORECASE):
            return _bloquear("prompt_injection", "Não consigo processar essa solicitação.")

    texto_lower = mensagem_anonimizada.lower()
    for kw in _KEYWORDS_DADOS_INTERNOS:
        if kw in texto_lower:
            return _bloquear(
                "acesso_dados_internos",
                "Não tenho como compartilhar informações internas do sistema.",
            )

    resposta = llm.invoke(_PROMPT_GUARDRAIL.format(mensagem=mensagem_anonimizada)).content

    categoria = "APROVADO"
    for linha in resposta.splitlines():
        if linha.strip().upper().startswith("CATEGORIA:"):
            categoria = linha.split(":", 1)[1].strip().upper()
            break

    if categoria in _RESPOSTAS_BLOQUEIO:
        motivo, mensagem = _RESPOSTAS_BLOQUEIO[categoria]
        return _bloquear(motivo, mensagem)

    return _aprovado()


def guardrail_saida(resposta, mapa_pii, restaurar_pii=False):
    """
    Limpa e revisa a resposta do especialista antes de entregar ao usuário.
    Nunca bloqueia — sempre retorna o texto revisado em 'conteudo'.
    """
    # 1. Remove PII que o modelo tenha gerado
    for tipo, padrao in PII:
        resposta = re.sub(padrao, f"[{tipo} OMITIDO]", resposta)

    # 2. Resolve tokens de PII da entrada
    resposta = desanonimizar_saida(resposta, mapa_pii, restaurar=restaurar_pii)

    # 3. Revisão semântica opcional. Em produção ela pode ser reativada por
    # ACTA_GUARDRAIL_LLM_OUTPUT=true se a política exigir uma segunda LLM.
    if LLM_OUTPUT_REVIEW:
        saida = llm.invoke(_PROMPT_COMPLIANCE.format(resposta=resposta)).content.strip()
        if "RESPOSTA:" in saida:
            resposta = saida.split("RESPOSTA:", 1)[1].strip() or resposta

    return _saida_ok(resposta)
