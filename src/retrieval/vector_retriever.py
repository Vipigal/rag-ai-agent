from domain.models import RetrievedChunk
from domain.ports import EmbeddingModel, VectorStore


class VectorRetriever:
    def __init__(self, embedder: EmbeddingModel, store: VectorStore) -> None:
        self._embedder = embedder
        self._store = store

    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]:
        vector = self._embedder.embed([query])[0]
        return self._store.search(vector, k)
