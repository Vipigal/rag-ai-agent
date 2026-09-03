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
class Usage:
    requests: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            requests=self.requests + other.requests,
            tool_calls=self.tool_calls + other.tool_calls,
            input_tokens=self.input_tokens + other.input_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


@dataclass(frozen=True)
class Completion:
    message: Message
    reply: AgentReply | None
    usage: Usage = Usage()


@dataclass(frozen=True)
class Reference:
    chunk: Chunk
    quote: str
    retrieval_source: str = "seed"


@dataclass(frozen=True)
class Answer:
    text: str
    references: list[Reference]
    has_answer: bool = True
    usage: Usage = Usage()
    unmatched_citations: list[str] = field(default_factory=list)
