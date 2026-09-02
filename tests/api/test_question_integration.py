from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from api.composition import get_agent_service
from api.main import app
from domain.models import AgentReply, Chunk, Completion, Message, chunk_id
from domain.ports import Tool
from domain.services.agent_service import AgentService
from retrieval.qdrant_store import QdrantVectorStore
from retrieval.vector_retriever import VectorRetriever

QUESTION = "What is the power consumption of the motor?"
POWER_TEXT = "The W22 motor requires 2.3 kW to operate at a 60 Hz line frequency."
GREASE_TEXT = "Regrease the bearings every 8000 h with Mobil Polyrex EM."
POWER_CHUNK_ID = chunk_id("doc-a", 1)


class KeywordEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text.lower()) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text.lower())

    @staticmethod
    def _vector(text: str) -> list[float]:
        power = 1.0 if "power" in text or "kw" in text else 0.0
        grease = 1.0 if "grease" in text else 0.0
        return [power, grease, 0.1]


class CitingLLM:
    def __init__(self, answer: str, citations: list[str]) -> None:
        self._reply = AgentReply(answer=answer, citations=citations, has_answer=True)
        self.seen_context: str = ""

    def complete(self, messages: list[Message], tools: list[Tool]) -> Completion:
        self.seen_context = messages[1].content
        return Completion(message=Message(role="assistant", content="{…}"), reply=self._reply)


def make_chunk(document_id: str, filename: str, text: str, page: int, index: int) -> Chunk:
    return Chunk(
        id=chunk_id(document_id, index),
        document_id=document_id,
        filename=filename,
        text=text,
        page=page,
        section="3. Operation > 3.2 Electrical data",
        index_in_doc=index,
    )


def make_service(llm: CitingLLM) -> AgentService:
    embedder = KeywordEmbedder()
    store = QdrantVectorStore(QdrantClient(":memory:"), collection="chunks", vector_size=3)
    chunks = [
        make_chunk("doc-a", "w22-manual.pdf", GREASE_TEXT, page=42, index=0),
        make_chunk("doc-a", "w22-manual.pdf", POWER_TEXT, page=7, index=1),
    ]
    store.add(chunks, [[vector] for vector in embedder.embed_documents([chunk.text for chunk in chunks])])
    return AgentService(
        retriever=VectorRetriever(embedder, store),
        llm=llm,
        k=1,
        max_tool_rounds=3,
        tool_enabled=True,
    )


def test_question_flows_through_retriever_and_store_to_a_grounded_answer():
    llm = CitingLLM("The motor requires 2.3 kW.", [POWER_CHUNK_ID])

    answer = make_service(llm).answer(QUESTION)

    assert answer.text == "The motor requires 2.3 kW."
    [reference] = answer.references
    assert (reference.chunk.filename, reference.chunk.page) == ("w22-manual.pdf", 7)
    assert reference.chunk.text == POWER_TEXT
    assert reference.retrieval_source == "seed"
    assert f'<chunk id="{POWER_CHUNK_ID}" document="w22-manual.pdf" page="7">' in llm.seen_context
    assert "<section>3.2 Electrical data</section>" in llm.seen_context


def test_http_question_returns_the_verbatim_stored_excerpt_as_reference():
    app.dependency_overrides[get_agent_service] = lambda: make_service(
        CitingLLM("The motor requires 2.3 kW.", [POWER_CHUNK_ID])
    )
    try:
        response = TestClient(app).post("/question", json={"question": QUESTION})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "answer": "The motor requires 2.3 kW.",
        "references": [POWER_TEXT],
    }
