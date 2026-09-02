from collections.abc import Callable
from typing import Protocol

from domain.models import Chunk, Completion, Document, Message, Page, RetrievedChunk


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


Tool = Callable[..., str]


class LLM(Protocol):
    def complete(self, messages: list[Message], tools: list[Tool]) -> Completion: ...


Chunker = Callable[[Document, list[Page]], list[Chunk]]
