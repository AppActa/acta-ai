"""API HTTP do chatbot ACTA."""

import uuid

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from clients.mcp_acta_client import mcp_request_context
from clients.memory_client import (
    configurar_consentimento,
    excluir_memoria,
    garantir_sessao,
    listar_memorias,
    obter_consentimento,
)
from clients.skill_client import (
    SkillClientError,
    criar_skill,
    excluir_skill,
    listar_skills,
)
from pipeline import get_response

app = FastAPI(
    title="ACTA AI API",
    description="API do chatbot gerencial do ACTA",
    version="1.1.0",
)


class NovaSessaoRequest(BaseModel):
    usuario_id: int = Field(..., gt=0)
    empresa_id: int = Field(..., gt=0)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    id_ciclo: int | None = Field(default=None, gt=0)
    usuario_id: int = Field(..., gt=0)
    empresa_id: int = Field(..., gt=0)


class ConsentimentoRequest(BaseModel):
    usuario_id: int = Field(..., gt=0)
    empresa_id: int = Field(..., gt=0)
    modo: str = Field(..., pattern="^(desativado|somente_explicitas|automatica)$")
    retencao_dias: int | None = Field(default=None, ge=1, le=3650)


class CriarSkillRequest(BaseModel):
    usuario_id: int = Field(..., gt=0)
    empresa_id: int = Field(..., gt=0)
    conteudo_markdown: str = Field(..., min_length=1, max_length=5000)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API do ACTA AI está online!"}


@app.post("/nova_sessao")
def nova_sessao(request: NovaSessaoRequest) -> dict[str, int | str]:
    """Cria uma sessão persistente vinculada ao usuário e à empresa autenticados."""

    session_id = str(uuid.uuid4())
    with mcp_request_context(
        usuario_id=request.usuario_id,
        empresa_id=request.empresa_id,
    ):
        garantir_sessao(session_id)
    return {
        "usuario_id": request.usuario_id,
        "empresa_id": request.empresa_id,
        "session_id": session_id,
    }


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, str]:
    message = request.message.strip()
    session_id = request.session_id.strip()
    if not message:
        raise HTTPException(status_code=400, detail="O parâmetro 'message' é obrigatório.")
    if not session_id:
        raise HTTPException(status_code=400, detail="O parâmetro 'session_id' é obrigatório.")

    with mcp_request_context(
        usuario_id=request.usuario_id,
        empresa_id=request.empresa_id,
    ):
        try:
            response = get_response(
                message=message,
                session_id=session_id,
                id_ciclo=request.id_ciclo,
            )
        except SkillClientError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session_id": session_id, "resposta": response}


@app.get("/memoria")
def consultar_memorias(
    usuario_id: int,
    empresa_id: int,
    tipo: str | None = None,
    limit: int = 50,
) -> dict:
    """Lista o que está armazenado para dar transparência ao usuário."""

    with mcp_request_context(usuario_id=usuario_id, empresa_id=empresa_id):
        return {"memorias": listar_memorias(tipo=tipo, limit=limit)}


@app.delete("/memoria/{id_memoria}")
def apagar_memoria(id_memoria: str, usuario_id: int, empresa_id: int) -> dict:
    """Remove um item da fonte MongoDB e do índice semântico Qdrant."""

    with mcp_request_context(
        usuario_id=usuario_id,
        empresa_id=empresa_id,
    ):
        excluir_memoria(id_memoria)
    return {"id_memoria": id_memoria, "excluida": True}


@app.get("/memoria/consentimento")
def consultar_consentimento(usuario_id: int, empresa_id: int) -> dict:
    with mcp_request_context(usuario_id=usuario_id, empresa_id=empresa_id):
        return obter_consentimento()


@app.put("/memoria/consentimento")
def alterar_consentimento(request: ConsentimentoRequest) -> dict:
    with mcp_request_context(
        usuario_id=request.usuario_id,
        empresa_id=request.empresa_id,
    ):
        return configurar_consentimento(request.modo, request.retencao_dias)


@app.post("/skills")
def criar_skill_personalizada(request: CriarSkillRequest) -> dict:
    """Cria ou atualiza uma skill no formato Markdown seguro."""

    with mcp_request_context(
        usuario_id=request.usuario_id,
        empresa_id=request.empresa_id,
    ):
        try:
            return {"skill": criar_skill(request.conteudo_markdown)}
        except SkillClientError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/skills")
def consultar_skills(usuario_id: int, empresa_id: int, limit: int = 50) -> dict:
    with mcp_request_context(usuario_id=usuario_id, empresa_id=empresa_id):
        return {"skills": listar_skills(limit=limit)}


@app.delete("/skills/{nome}")
def apagar_skill(
    nome: str,
    usuario_id: int,
    empresa_id: int,
) -> dict:
    with mcp_request_context(
        usuario_id=usuario_id,
        empresa_id=empresa_id,
    ):
        try:
            return excluir_skill(nome)
        except SkillClientError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8200, reload=True)
