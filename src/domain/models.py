import uuid
from dataclasses import dataclass, field


def chunk_id(document_id: str, index_in_doc: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{index_in_doc}"))


@dataclass(frozen=True)
class Document:
    id: str
    filename: str


@dataclass(frozen=True)
class Page:
    number: int
    text: str
    section: str | None


@dataclass(frozen=True)
class IngestionResult:
    documents_indexed: int
    total_chunks: int


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    filename: str
    text: str
    page: int
    section: str | None
    index_in_doc: int
    kind: str = "text"
    metadata: dict[str, object] = field(default_factory=dict)
