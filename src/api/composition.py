import os
from functools import lru_cache

from openai import OpenAI
from qdrant_client import QdrantClient

from domain.services.ingestion_pipeline import IngestionPipelineService
from ingestion.chunking import fixed_size_chunks
from ingestion.pymupdf4llm_extractor import Pymupdf4llmExtractor
from retrieval.openai_embedder import OpenaiEmbeddingModel
from retrieval.qdrant_store import QdrantVectorStore

EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionPipelineService:
    model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    if model not in EMBEDDING_DIMENSIONS:
        supported = ", ".join(sorted(EMBEDDING_DIMENSIONS))
        raise ValueError(f"unknown EMBEDDING_MODEL '{model}'; supported: {supported}")

    qdrant = QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    return IngestionPipelineService(
        extractor=Pymupdf4llmExtractor(),
        chunker=fixed_size_chunks,
        embedder=OpenaiEmbeddingModel(OpenAI(), model=model),
        store=QdrantVectorStore(
            qdrant,
            collection=os.environ.get("QDRANT_COLLECTION", "chunks"),
            vector_size=EMBEDDING_DIMENSIONS[model],
        ),
    )
