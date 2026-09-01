from collections.abc import Callable
from typing import Protocol

from domain.models import Chunk, Document, Page, RetrievedChunk


class PdfExtractor(Protocol):
    def extract(self, data: bytes, filename: str) -> list[Page]: ...


class EmbeddingModel(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...

    def search(self, vector: list[float], k: int) -> list[RetrievedChunk]: ...

    def count(self) -> int: ...


class Retriever(Protocol):
    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]: ...


Chunker = Callable[[Document, list[Page]], list[Chunk]]
