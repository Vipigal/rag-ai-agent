import os
from functools import lru_cache

from pydantic_ai.embeddings import Embedder, EmbeddingSettings
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.settings import ModelSettings, ThinkingEffort
from qdrant_client import QdrantClient

from domain.ports import LLM, Retriever
from domain.services.agent_service import AgentService
from domain.services.ingestion_pipeline import IngestionPipelineService
from ingestion.chunking import page_chunks
from ingestion.embedding_units import embedding_units
from ingestion.pymupdf4llm_extractor import Pymupdf4llmExtractor
from llm.pydantic_ai_llm import PydanticAiLLM
from retrieval.pydantic_ai_embedder import PydanticAiEmbeddingModel
from retrieval.qdrant_store import QdrantVectorStore
from retrieval.vector_retriever import VectorRetriever

DEFAULT_LLM_MODEL = "openai:gpt-5-mini"
DEFAULT_LLM_FALLBACK_MODEL = "google:gemini-3.5-flash"
DEFAULT_EMBEDDING_MODEL = "google:gemini-embedding-001"
DEFAULT_LLM_THINKING = "low"

THINKING_EFFORTS: dict[str, ThinkingEffort] = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
}
THINKING_OFF = "off"

EMBEDDING_DIMENSIONS = {
    "openai:text-embedding-3-small": 1536,
    "openai:text-embedding-3-large": 3072,
    "google:gemini-embedding-001": 3072,
}

EMBEDDING_BATCH_SIZES = {"openai": 2048, "google": 100}

TRUE_VALUES = {"1", "true", "yes", "on"}

PROVIDER_KEYS = {
    "openai": ("OPENAI_API_KEY",),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}
PROVIDER_PREFIXES = {
    "openai": ("openai:", "openai-chat:", "openai-responses:"),
    "google": ("google:", "google-gla:", "google-vertex:"),
}


def qdrant_collection() -> str:
    return os.environ.get("QDRANT_COLLECTION", "chunks")


def llm_model_name() -> str:
    return os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL)


def llm_fallback_model_name() -> str:
    return os.environ.get("LLM_FALLBACK_MODEL", DEFAULT_LLM_FALLBACK_MODEL).strip()


def llm_model() -> Model | str:
    fallback = llm_fallback_model_name()
    return FallbackModel(llm_model_name(), fallback) if fallback else llm_model_name()


def llm_thinking_name() -> str | None:
    name = os.environ.get("LLM_THINKING", DEFAULT_LLM_THINKING).strip().lower()
    if not name:
        return None
    if name != THINKING_OFF and name not in THINKING_EFFORTS:
        supported = ", ".join([*THINKING_EFFORTS, THINKING_OFF])
        raise ValueError(f"unknown LLM_THINKING '{name}'; supported: {supported}")
    return name


def llm_settings() -> ModelSettings | None:
    name = llm_thinking_name()
    if name is None:
        return None
    return ModelSettings(thinking=False if name == THINKING_OFF else THINKING_EFFORTS[name])


def retrieval_k() -> int:
    return int(os.environ.get("RETRIEVAL_K", "5"))


def agent_max_tool_rounds() -> int:
    return int(os.environ.get("AGENT_MAX_TOOL_ROUNDS", "3"))


def query_knowledge_enabled() -> bool:
    return os.environ.get("QUERY_KNOWLEDGE_ENABLED", "true").strip().lower() in TRUE_VALUES


def embedding_model_name() -> str:
    model = os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    if model not in EMBEDDING_DIMENSIONS:
        supported = ", ".join(sorted(EMBEDDING_DIMENSIONS))
        raise ValueError(f"unknown EMBEDDING_MODEL '{model}'; supported: {supported}")
    return model


def embedding_dimensions() -> int:
    return EMBEDDING_DIMENSIONS[embedding_model_name()]


def qdrant_url() -> str:
    return os.environ.get("QDRANT_URL", "http://localhost:6333")


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=qdrant_url())


@lru_cache(maxsize=1)
def get_embedder() -> PydanticAiEmbeddingModel:
    model = embedding_model_name()
    provider = model.split(":", 1)[0]
    settings = EmbeddingSettings(dimensions=embedding_dimensions())
    return PydanticAiEmbeddingModel(
        lambda: Embedder(model, settings=settings),
        max_batch=EMBEDDING_BATCH_SIZES[provider],
    )


def build_llm() -> PydanticAiLLM:
    return PydanticAiLLM(llm_model(), settings=llm_settings())


def validate_configuration() -> None:
    embedding_model_name()
    llm_thinking_name()
    for provider, variables in PROVIDER_KEYS.items():
        needed_by = _settings_using(provider)
        if needed_by and not any(os.environ.get(name, "").strip() for name in variables):
            raise ValueError(
                f"{variables[0]} is not set but {', '.join(needed_by)} needs it: "
                "copy .env.example to .env and fill it in"
            )
    build_llm()
    get_vector_store()


def _settings_using(provider: str) -> list[str]:
    configured = {
        "LLM_MODEL": llm_model_name(),
        "LLM_FALLBACK_MODEL": llm_fallback_model_name(),
        "EMBEDDING_MODEL": embedding_model_name(),
    }
    return [
        f"{setting}={model}"
        for setting, model in configured.items()
        if model.startswith(PROVIDER_PREFIXES[provider])
    ]


def build_vector_store(collection: str) -> QdrantVectorStore:
    return QdrantVectorStore(
        get_qdrant_client(),
        collection=collection,
        vector_size=embedding_dimensions(),
    )


def build_ingestion_service(store: QdrantVectorStore) -> IngestionPipelineService:
    return IngestionPipelineService(
        extractor=Pymupdf4llmExtractor(),
        chunker=page_chunks,
        unit_splitter=embedding_units,
        embedder=get_embedder(),
        store=store,
    )


def build_agent_service(retriever: Retriever, llm: LLM, k: int | None = None) -> AgentService:
    return AgentService(
        retriever=retriever,
        llm=llm,
        k=retrieval_k() if k is None else k,
        max_tool_rounds=agent_max_tool_rounds(),
        tool_enabled=query_knowledge_enabled(),
    )


@lru_cache(maxsize=1)
def get_vector_store() -> QdrantVectorStore:
    return build_vector_store(qdrant_collection())


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionPipelineService:
    return build_ingestion_service(get_vector_store())


@lru_cache(maxsize=1)
def get_agent_service() -> AgentService:
    return build_agent_service(
        retriever=VectorRetriever(get_embedder(), get_vector_store()),
        llm=build_llm(),
    )
