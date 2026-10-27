"""Consolidação do resumo das conversas."""

import json
import logging
import re

from agents.helpers.llms import llm
from agents.prompts.prompt_memory_mongo import _PROMPT_CONSOLIDAR_MEMORIA_ACTA

logger = logging.getLogger(__name__)


def consolidar_memoria(session_id: str, *, forcar: bool = False) -> bool:
    """Atualiza o resumo incremental da conversa."""

    try:
        from clients.memory_client import atualizar_resumo, obter_material_resumo

        material = (
            obter_material_resumo(session_id, forcar=True)
            if forcar
            else obter_material_resumo(session_id)
        )
        if not material.get("deve_resumir") or not material.get("resumido_ate"):
            return True
        prompt = _PROMPT_CONSOLIDAR_MEMORIA_ACTA.format(
            resumo_anterior=material.get("resumo_anterior") or "(sem resumo anterior)",
            conversa=material.get("conversa_formatada") or "",
        )
        response = llm.invoke(prompt)
        cleaned = str(response.content).strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(
                r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE
            )
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("O modelo não retornou JSON de memória.")
        parsed = json.loads(cleaned[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("O JSON de memória deve ser um objeto.")
        summary = str(parsed.get("resumo", "")).strip()
        if not summary:
            raise ValueError("O modelo não retornou resumo.")
        atualizar_resumo(session_id, summary, material["resumido_ate"])
        return True
    except Exception:  #memória não deve derrubar o atendimento
        logger.exception("Não foi possível consolidar a memória da sessão %s", session_id)
        return False
