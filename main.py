"""API HTTP do chatbot ACTA."""

import uuid
from time import perf_counter

import uvicorn
from fastapi import (
    FastAPI,
    HTTPException,
    File,
    Form,
    UploadFile
    )
from pydantic import BaseModel, Field
from clients.client_transcricao import transcrever_audio
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
from observability import instrument_fastapi_app, observed_span, record_chat_latency
from pipeline import get_response

app = FastAPI(
    title="ACTA AI API",
    description="API do chatbot gerencial do ACTA",
    version="1.1.1",
)
instrument_fastapi_app(app)


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


@app.get("/health")
def root() -> dict[str, str]:
    return {"message": "API do ACTA AI está online!"}


# Comentários para quem utilizar a API
# Primeiramente, você deve criar uma requisição POST para o endpoint /nova_sessao, passando os parâmetros da classe NovaSessaoRequest, que são: usuario_id e empresa_id. Essa requisição retorna essas 3 variáveis: usuario_id, empresa_id e session_id.

# Com essas variáveis junte mais essas duas: message e id_ciclo. Esses são os parâmetros da classe ChatRequest. Agora, crie uma requisição POST para o endpoint /chat, passando o ChatRequest. Ela retorna o session_id e a resposta.
# Para utilizar audio, usar o POST /chat/audio

# Uma coisa importante, o usuário Mobile não terá acesso para criar/alterar dados! apenas consultar-los. Enquanto no Web, ele tem acesso a alterações, apenas envolvendo os ciclos em que ele está presente e como um gestor/administrador

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
    started = perf_counter()
    status = "ok"
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
            with observed_span(
                "acta_ai.chat",
                {"acta.id_ciclo_present": request.id_ciclo is not None},
            ):
                response = get_response(
                    message=message,
                    session_id=session_id,
                    id_ciclo=request.id_ciclo,
                )
        except SkillClientError as exc:
            status = "invalid_skill"
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            status = "error"
            raise
        finally:
            record_chat_latency((perf_counter() - started) * 1000, status=status)
    return {"session_id": session_id, "resposta": response}

@app.post("/chat/audio")
async def chat_audio(
    audio: UploadFile = File(...),
    session_id: str = Form(..., min_length=1),
    usuario_id: int = Form(..., gt=0),
    empresa_id: int = Form(..., gt=0),
    id_ciclo: int | None = Form(default=None, gt=0),
) -> dict[str, str]:
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

    with mcp_request_context(
        usuario_id=usuario_id,
        empresa_id=empresa_id,
    ):
        resposta = get_response(
            message=transcricao,
            session_id=session_id,
            id_ciclo=id_ciclo,
        )

    return {
        "session_id": session_id,
        "transcricao": transcricao, # Quando utilizar a transcrição, Mostrar a Tradução, para o usuário ver se isso é realmente o que ele quiz dizer
        "resposta": resposta,
    }


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
