from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.composition import embedding_model_name, get_vector_store, llm_model_name
from api.errors import error_responses
from domain.ports import VectorStore

router = APIRouter()


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "vector_store": "ok",
                    "indexed_chunks": 164,
                    "llm_model": "openai:gpt-5-mini",
                    "embedding_model": "google:gemini-embedding-001",
                }
            ]
        }
    )

    status: str = Field(description="`ok` when the API can serve requests.")
    vector_store: str = Field(description="`ok` when Qdrant answered and its collection matches the configured embedding model.")
    indexed_chunks: int = Field(description="Chunks currently in the vector store; 0 before the first upload.")
    llm_model: str = Field(description="The primary LLM, as configured by `LLM_MODEL`.")
    embedding_model: str = Field(description="The embedding model, as configured by `EMBEDDING_MODEL`.")


@router.get(
    "/health",
    summary="Readiness check",
    description=(
        "Reports whether the API can serve requests: the vector store is reached and its "
        "collection is compatible with the configured embedding model, how many chunks are "
        "indexed, and which models are configured. Use it first when something fails: a "
        "`503` here names the dependency that is down and the fix."
    ),
    tags=["operations"],
    response_model=HealthResponse,
    response_description="The API is ready.",
    responses=error_responses(503),
)
def health(store: Annotated[VectorStore, Depends(get_vector_store)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        vector_store="ok",
        indexed_chunks=store.count(),
        llm_model=llm_model_name(),
        embedding_model=embedding_model_name(),
    )
