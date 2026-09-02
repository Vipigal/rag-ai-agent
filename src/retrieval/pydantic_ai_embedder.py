from pydantic_ai.embeddings import Embedder


class PydanticAiEmbeddingModel:
    def __init__(self, embedder: Embedder, max_batch: int) -> None:
        self._embedder = embedder
        self._max_batch = max_batch

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._max_batch):
            batch = texts[start : start + self._max_batch]
            result = self._embedder.embed_sync(batch, input_type="document")
            vectors.extend(list(vector) for vector in result.embeddings)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return list(self._embedder.embed_sync(text, input_type="query").embeddings[0])
