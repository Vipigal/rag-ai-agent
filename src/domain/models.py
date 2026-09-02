import uuid
from dataclasses import dataclass, field

SECTION_SEPARATOR = " > "


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


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    retrieval_source: str = "seed"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class AgentReply:
    answer: str
    citations: list[str]
    has_answer: bool


@dataclass(frozen=True)
class Completion:
    message: Message
    reply: AgentReply | None


@dataclass(frozen=True)
class Answer:
    text: str
    references: list[RetrievedChunk]
