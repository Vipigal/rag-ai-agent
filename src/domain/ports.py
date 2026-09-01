from collections.abc import Callable
from typing import Protocol

from domain.models import Chunk, Document, Page


class PdfExtractor(Protocol):
    def extract(self, data: bytes, filename: str) -> list[Page]: ...


class EmbeddingModel(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...


Chunker = Callable[[Document, list[Page]], list[Chunk]]
