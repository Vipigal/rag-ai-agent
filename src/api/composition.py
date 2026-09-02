import os
from functools import lru_cache

from openai import OpenAI
from qdrant_client import QdrantClient

from domain.ports import LLM, Retriever
from domain.services.agent_service import AgentService
from domain.services.ingestion_pipeline import IngestionPipelineService
from ingestion.chunking import fixed_size_chunks
from ingestion.pymupdf4llm_extractor import Pymupdf4llmExtractor
from llm.pydantic_ai_llm import PydanticAiLLM
from retrieval.openai_embedder import OpenaiEmbeddingModel
from retrieval.qdrant_store import QdrantVectorStore
from retrieval.vector_retriever import VectorRetriever

EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

TRUE_VALUES = {"1", "true", "yes", "on"}


def qdrant_collection() -> str:
    return os.environ.get("QDRANT_COLLECTION", "chunks")


def llm_model_name() -> str:
    return os.environ.get("LLM_MODEL", "openai:gpt-5-mini")


def retrieval_k() -> int:
    return int(os.environ.get("RETRIEVAL_K", "5"))


def agent_max_tool_rounds() -> int:
    return int(os.environ.get("AGENT_MAX_TOOL_ROUNDS", "3"))


def query_knowledge_enabled() -> bool:
    return os.environ.get("QUERY_KNOWLEDGE_ENABLED", "true").strip().lower() in TRUE_VALUES


def embedding_model_name() -> str:
    model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    if model not in EMBEDDING_DIMENSIONS:
        supported = ", ".join(sorted(EMBEDDING_DIMENSIONS))
        raise ValueError(f"unknown EMBEDDING_MODEL '{model}'; supported: {supported}")
    return model


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"))


@lru_cache(maxsize=1)
def get_embedder() -> OpenaiEmbeddingModel:
    return OpenaiEmbeddingModel(OpenAI(), model=embedding_model_name())


def build_vector_store(collection: str) -> QdrantVectorStore:
    return QdrantVectorStore(
        get_qdrant_client(),
        collection=collection,
        vector_size=EMBEDDING_DIMENSIONS[embedding_model_name()],
    )


def build_ingestion_service(store: QdrantVectorStore) -> IngestionPipelineService:
    return IngestionPipelineService(
        extractor=Pymupdf4llmExtractor(),
        chunker=fixed_size_chunks,
        embedder=get_embedder(),
        store=store,
    )


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionPipelineService:
    return build_ingestion_service(build_vector_store(qdrant_collection()))


def build_agent_service(retriever: Retriever, llm: LLM) -> AgentService:
    return AgentService(
        retriever=retriever,
        llm=llm,
        k=retrieval_k(),
        max_tool_rounds=agent_max_tool_rounds(),
        tool_enabled=query_knowledge_enabled(),
    )


#rebuilding vector store?
@lru_cache(maxsize=1)
def get_agent_service() -> AgentService:
    return build_agent_service(
        retriever=VectorRetriever(get_embedder(), build_vector_store(qdrant_collection())),
        llm=PydanticAiLLM(llm_model_name()),
    )
