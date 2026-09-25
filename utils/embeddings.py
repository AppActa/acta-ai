from functools import lru_cache

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import GEMINI_API_KEY

EMBEDDING_MODEL = "gemini-embedding-2-preview"
EMBEDDING_DIM = 768


@lru_cache(maxsize=1)
def _embeddings(api_key: str) -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=api_key)


def gerar_embedding(texto: str) -> list[float]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada para busca semântica.")
    return _embeddings(GEMINI_API_KEY).embed_query(texto, output_dimensionality=EMBEDDING_DIM)


def gerar_embeddings_batch(textos: list[str]) -> list[list[float]]:
    if not textos:
        return []
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada para busca semântica.")
    return _embeddings(GEMINI_API_KEY).embed_documents(
        textos, output_dimensionality=EMBEDDING_DIM
    )
