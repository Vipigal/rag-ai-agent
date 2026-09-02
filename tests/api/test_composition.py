import pytest

from api.composition import build_agent_service
from domain.models import AgentReply, Chunk, Completion, Message, RetrievedChunk, ToolCall
from domain.ports import Tool

QUESTION = "what grease should I use?"
KNOBS = ("LLM_MODEL", "RETRIEVAL_K", "AGENT_MAX_TOOL_ROUNDS", "QUERY_KNOWLEDGE_ENABLED")


class FakeRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]:
        self.calls.append((query, k))
        chunk = Chunk(
            id="c1",
            document_id="d",
            filename="manual.pdf",
            text="Mobil Polyrex EM",
            page=42,
            section=None,
            index_in_doc=0,
        )
        return [RetrievedChunk(chunk=chunk, score=0.9)]


class FakeLLM:
    def __init__(self, script: list[Completion]) -> None:
        self._script = list(script)
        self.tools_offered: list[list[str]] = []

    def complete(self, messages: list[Message], tools: list[Tool]) -> Completion:
        self.tools_offered.append([tool.__name__ for tool in tools])
        return self._script.pop(0)


def final(answer: str, citations: list[str]) -> Completion:
    return Completion(
        message=Message(role="assistant", content="{…}"),
        reply=AgentReply(answer=answer, citations=citations, has_answer=True),
    )


def tool_request(query: str) -> Completion:
    call = ToolCall(id="c", name="query_knowledge", arguments={"query": query})
    return Completion(message=Message(role="assistant", content="", tool_calls=(call,)), reply=None)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for name in KNOBS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_retrieve_five_and_offer_the_query_knowledge_tool():
    retriever, llm = FakeRetriever(), FakeLLM([final("Polyrex", ["c1"])])

    build_agent_service(retriever, llm).answer(QUESTION)

    assert retriever.calls == [(QUESTION, 5)]
    assert llm.tools_offered == [["query_knowledge"]]


def test_env_knobs_override_k_and_disable_the_tool(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RETRIEVAL_K", "2")
    monkeypatch.setenv("QUERY_KNOWLEDGE_ENABLED", "false")
    retriever, llm = FakeRetriever(), FakeLLM([final("Polyrex", ["c1"])])

    build_agent_service(retriever, llm).answer(QUESTION)

    assert retriever.calls == [(QUESTION, 2)]
    assert llm.tools_offered == [[]]


def test_env_knob_caps_the_tool_rounds(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_MAX_TOOL_ROUNDS", "1")
    llm = FakeLLM([tool_request("grease"), final("Polyrex", ["c1"])])
    retriever = FakeRetriever()

    build_agent_service(retriever, llm).answer(QUESTION)

    assert retriever.calls == [(QUESTION, 5), ("grease", 5)]
    assert llm.tools_offered == [["query_knowledge"], []]
