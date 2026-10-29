"""API HTTP do chatbot ACTA."""

import uuid

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator, model_validator

from agents.helpers.errors import AuthorizationError, NotFoundError
from agents.memoria import consolidar_memoria
from clients.client_transcricao import transcrever_audio
from clients.mcp_acta_client import mcp_request_context
from clients.memory_client import (
    encerrar_sessao,
    listar_chats,
    listar_mensagens,
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
    version="1.1.1",
)


class NovaSessaoRequest(BaseModel):
    usuario_id: int = Field(..., gt=0)
    empresa_id: int = Field(..., gt=0)
    session_id_atual: str | None = Field(default=None, min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    id_ciclo: list[int] = Field(default_factory=list, max_length=20)
    ciclo_ativo: int | None = Field(default=None, gt=0)
    usuario_id: int = Field(..., gt=0)
    empresa_id: int = Field(..., gt=0)

    @field_validator("id_ciclo", mode="before")
    @classmethod
    def _aceitar_ciclo_legado(cls, cycles: object) -> object:
        if cycles is None:
            return []
        if isinstance(cycles, int):
            return [cycles]
        return cycles

    @field_validator("id_ciclo")
    @classmethod
    def _normalizar_ciclos(cls, cycles: list[int]) -> list[int]:
        if any(cycle <= 0 for cycle in cycles):
            raise ValueError("id_ciclo deve conter somente inteiros positivos.")
        return list(dict.fromkeys(cycles))

    @model_validator(mode="after")
    def _validar_ciclo_ativo(self) -> "ChatRequest":
        if self.ciclo_ativo is not None and self.ciclo_ativo not in self.id_ciclo:
            raise ValueError("ciclo_ativo deve estar presente em id_ciclo.")
        return self


class CriarSkillRequest(BaseModel):
    usuario_id: int = Field(..., gt=0)
    empresa_id: int = Field(..., gt=0)
    conteudo_markdown: str = Field(..., min_length=1, max_length=5000)


def _responder_chat(request: ChatRequest, *, message: str, session_id: str) -> str:
    with mcp_request_context(
        usuario_id=request.usuario_id,
        empresa_id=request.empresa_id,
    ):
        try:
            return get_response(
                message=message,
                session_id=session_id,
                id_ciclo=request.id_ciclo,
                ciclo_ativo=request.ciclo_ativo,
            )
        except SkillClientError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
def root() -> dict[str, str]:
    return {"message": "API do ACTA AI está online!"}


@app.post("/nova_conversa")
def nova_conversa(request: NovaSessaoRequest) -> dict[str, int | str | bool]:
    """Encerra uma conversa não vazia e devolve um identificador ainda não persistido."""

    session_id = str(uuid.uuid4())
    with mcp_request_context(
        usuario_id=request.usuario_id,
        empresa_id=request.empresa_id,
    ):
        if request.session_id_atual:
            consolidada = consolidar_memoria(request.session_id_atual, forcar=True)
            encerrada = encerrar_sessao(request.session_id_atual) if consolidada else False
        else:
            encerrada = False
    return {
        "usuario_id": request.usuario_id,
        "empresa_id": request.empresa_id,
        "session_id": session_id,
        "conversa_anterior_encerrada": encerrada,
    }


@app.get("/listar_chats")
def consultar_chats(usuario_id: int, empresa_id: int, limit: int = 50) -> dict:
    with mcp_request_context(usuario_id=usuario_id, empresa_id=empresa_id):
        return {"chats": listar_chats(limit=limit)}


@app.get("/chats/{session_id}/mensagens")
def consultar_mensagens(
    session_id: str,
    usuario_id: int,
    empresa_id: int,
    limit: int = Query(default=30, ge=1, le=100),
) -> dict:
    with mcp_request_context(usuario_id=usuario_id, empresa_id=empresa_id):
        try:
            messages = listar_mensagens(session_id, limit=limit)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"session_id": session_id, "mensagens": messages}


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, str]:
    message = request.message.strip()
    session_id = request.session_id.strip()
    if not message:
        raise HTTPException(status_code=400, detail="O parâmetro 'message' é obrigatório.")
    if not session_id:
        raise HTTPException(status_code=400, detail="O parâmetro 'session_id' é obrigatório.")

    response = _responder_chat(request, message=message, session_id=session_id)
    return {"session_id": session_id, "resposta": response}

@app.post("/chat/audio")
async def chat_audio(
    audio: UploadFile = File(...),  # noqa: B008 - marcador exigido pelo FastAPI
    session_id: str = Form(..., min_length=1),
    usuario_id: int = Form(..., gt=0),
    empresa_id: int = Form(..., gt=0),
    id_ciclo: list[int] = Form(default_factory=list),  # noqa: B008 - default de formulário
    ciclo_ativo: int | None = Form(default=None, gt=0),
) -> dict[str, str]:
    try:
        scope = ChatRequest(
            message="audio",
            session_id=session_id,
            id_ciclo=id_ciclo,
            ciclo_ativo=ciclo_ativo,
            usuario_id=usuario_id,
            empresa_id=empresa_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    conteudo = await audio.read()

    if not conteudo:
        raise HTTPException(status_code=400, detail="O arquivo de áudio está vazio.")

    if len(conteudo) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="O arquivo de áudio não pode ultrapassar 25 MB.",
        )

    transcricao = transcrever_audio(
        conteudo,
        audio.filename or "audio.webm",
        language="pt",
    )

    if not transcricao:
        raise HTTPException(
            status_code=422,
            detail="Não foi possível transcrever o áudio.",
        )

    resposta = _responder_chat(scope, message=transcricao, session_id=session_id)

    return {
        "session_id": session_id,
        "transcricao": transcricao,
        "resposta": resposta,
    }


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
