"""Parser estrito e validação de segurança das skills criadas pelo usuário."""

import re
import unicodedata

from agents.helpers.skills.schemas import SkillDefinition

_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_HEADING = re.compile(r"^#\s*([^#].*?)\s*$")
_PII_PATTERNS = (
    re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"),
    re.compile(r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}"),
)

_UNSAFE_PATTERNS = (
    # Código, conteúdo executável e referências externas.
    r"```|~~~|`[^`]+`",
    r"<\s*/?\s*[a-z][^>]*>",
    r"!\[[^]]*\]\s*\(|\[[^]]+\]\s*\([^)]*\)",
    r"\b(?:https?|file|data|javascript)\s*:",
    r"(?m)^\s*(?:#!|import\s+|from\s+\S+\s+import\s+|(?:async\s+)?def\s+|class\s+|function\s+|const\s+|let\s+|var\s+)",
    r"\b(?:import\s+[a-z_][\w.]*|from\s+\S+\s+import\s+\S+)",
    r"(?m)^\s*(?:[-*]\s*)?(?:print|input|console\.log|fetch|require)\s*\(",
    r"(?m)^\s*(?:[-*]\s*)?(?:if|else|for|while|try|except|return|await)\b.*(?:[:{;])\s*$",
    r"=>|&&|\|\||===|!==",
    r"(?m)^\s*(?:select|insert|update|delete|drop|alter|create)\s+\S+",
    r"\b(?:eval|exec|subprocess|os\.system|powershell|cmd\.exe|bash|curl|wget)\b",
    r"\\x[0-9a-f]{2}|\\u[0-9a-f]{4}|[a-z0-9+/]{120,}={0,2}",
    # Prompt injection e tentativas de mudar a hierarquia de instruções.
    r"\b(?:ignore|disregard|forget)\b.{0,50}\b(?:instruction|prompt|rule)s?\b",
    r"\b(?:ignore|desconsidere|esque[çc]a|anule|sobrescreva)\b.{0,60}\b(?:instru|regra|prompt)",
    r"\b(?:system|developer|assistant|user)\s*(?:prompt|message|role|:)",
    r"\b(?:prompt\s+do\s+sistema|prompt\s+interno|instru[çc][õo]es\s+internas)\b",
    r"\b(?:revele|mostre|exponha|vaze)\b.{0,50}\b(?:prompt|instru|segredo|chave|token)",
    r"\b(?:jailbreak|bypass|dan\s+mode|modo\s+(?:irrestrito|desenvolvedor))\b",
    r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|finja\s+ser|aja\s+como)\b",
    r"<\s*(?:system|developer|assistant|user)\s*>|\[\s*inst\s*\]",
    # A skill não pode selecionar componentes internos.
    r"\b(?:tool|tools|ferramenta|ferramentas|agente|agentes|especialista|especialistas|roteador|orquestrador)\b",
)


def _normalized_for_detection(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", _ZERO_WIDTH.sub("", value)).casefold()
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(character)
    )


def _slugify(name: str) -> str:
    normalized = _normalized_for_detection(name)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if not slug or len(slug) > 64:
        raise ValueError("O nome da skill deve gerar um comando de até 64 caracteres.")
    return slug


def _validate_safe_text(value: str) -> None:
    if any(pattern.search(value) for pattern in _PII_PATTERNS):
        raise ValueError("A skill não pode conter dados pessoais.")
    detected = _normalized_for_detection(value)
    # Impede que ênfase Markdown seja usada para quebrar palavras bloqueadas,
    # por exemplo ``i**gnore`` ou ``sys_tem prompt``.
    detected = re.sub(r"(?<=\w)[*_~]+(?=\w)", "", detected)
    if any(re.search(pattern, detected, flags=re.IGNORECASE) for pattern in _UNSAFE_PATTERNS):
        raise ValueError(
            "A skill contém conteúdo não permitido. Use apenas objetivo e regras de resposta, "
            "sem código, links, prompt injection ou componentes internos."
        )


def parse_skill_markdown(content: str) -> SkillDefinition:
    """Converte exatamente ``# nome``, ``# objetivo`` e ``# regras`` em dados seguros."""

    if not isinstance(content, str):
        raise ValueError("O conteúdo da skill deve ser texto Markdown.")
    content = unicodedata.normalize("NFKC", _ZERO_WIDTH.sub("", content)).replace("\r\n", "\n")
    content = content.replace("\r", "\n").strip()
    if not content or len(content) > 5000:
        raise ValueError("A skill deve ter entre 1 e 5000 caracteres.")

    lines = content.splitlines()
    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            match = _HEADING.fullmatch(line.strip())
            if match is None:
                raise ValueError("Use apenas títulos Markdown de nível 1: # nome, # objetivo e # regras.")
            headings.append((index, match.group(1).strip()))

    if len(headings) != 3 or headings[0][0] != 0:
        raise ValueError("Formato esperado: # nome, # objetivo e # regras, nesta ordem.")

    objective_label = _normalized_for_detection(headings[1][1])
    rules_label = _normalized_for_detection(headings[2][1])
    if objective_label != "objetivo" or rules_label != "regras":
        raise ValueError("Formato esperado: # nome, # objetivo e # regras, nesta ordem.")

    name = headings[0][1].strip()
    if len(name) > 64 or not re.fullmatch(r"[\wÀ-ÿ -]+", name, flags=re.UNICODE):
        raise ValueError("O nome aceita somente letras, números, espaços e hífens.")

    objective = "\n".join(lines[headings[1][0] + 1 : headings[2][0]]).strip()
    rules = "\n".join(lines[headings[2][0] + 1 :]).strip()
    if len(objective) < 3 or len(objective) > 1000:
        raise ValueError("O objetivo deve ter entre 3 e 1000 caracteres.")
    if not rules:
        rules = "Nenhuma regra observada"
    elif len(rules) > 3000:
        raise ValueError("As regras devem ter no máximo 3000 caracteres.")

    _validate_safe_text("\n".join((name, objective, rules)))
    slug = _slugify(name)
    canonical = f"# {name}\n\n# objetivo\n\n{objective}\n\n# regras\n\n{rules}"
    return SkillDefinition(
        nome=name,
        slug=slug,
        objetivo=objective,
        regras=rules,
        markdown=canonical,
    )


def normalize_skill_command(value: str) -> str:
    command = value.strip().lower().removeprefix("/")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", command) or len(command) > 64:
        raise ValueError("Comando de skill inválido.")
    return command
