from openai import OpenAI


class OpenaiEmbeddingModel:
    def __init__(self, client: OpenAI, model: str, max_batch: int = 2048) -> None:
        self._client = client
        self._model = model
        self._max_batch = max_batch

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._max_batch):
            batch = texts[start : start + self._max_batch]
            response = self._client.embeddings.create(model=self._model, input=batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(item.embedding for item in ordered)
        return vectors
