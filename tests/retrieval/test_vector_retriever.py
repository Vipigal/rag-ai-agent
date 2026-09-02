from domain.models import Chunk, RetrievedChunk
from retrieval.vector_retriever import VectorRetriever

QUERY_VECTOR = [0.1, 0.2, 0.3]


class FakeEmbedder:
    def __init__(self) -> None:
        self.embedded: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        self.embedded.append([text])
        return QUERY_VECTOR


class FakeStore:
    def __init__(self, results: list[RetrievedChunk]) -> None:
        self._results = results
        self.searches: list[tuple[list[float], int]] = []

    def search(self, vector: list[float], k: int) -> list[RetrievedChunk]:
        self.searches.append((vector, k))
        return self._results[:k]

    def add(self, chunks: list[Chunk], vectors: list[list[list[float]]]) -> None:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError


def _retrieved(text: str, score: float) -> RetrievedChunk:
    chunk = Chunk(
        id="c",
        document_id="d",
        filename="manual.pdf",
        text=text,
        page=1,
        section=None,
        index_in_doc=0,
    )
    return RetrievedChunk(chunk=chunk, score=score)


def test_retrieve_searches_with_the_embedded_query_and_returns_store_ranking() -> None:
    ranking = [_retrieved("primeiro", 0.9), _retrieved("segundo", 0.5)]
    embedder = FakeEmbedder()
    store = FakeStore(ranking)

    results = VectorRetriever(embedder, store).retrieve("qual graxa usar?", k=2)

    assert results == ranking
    assert embedder.embedded == [["qual graxa usar?"]]
    assert store.searches == [(QUERY_VECTOR, 2)]


def test_retrieve_passes_k_through_to_the_store() -> None:
    ranking = [_retrieved("primeiro", 0.9), _retrieved("segundo", 0.5)]

    results = VectorRetriever(FakeEmbedder(), FakeStore(ranking)).retrieve("q?", k=1)

    assert results == ranking[:1]
