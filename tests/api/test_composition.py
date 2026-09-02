import pytest
from pydantic_ai.models.fallback import FallbackModel

from api.composition import (
    build_agent_service,
    embedding_dimensions,
    embedding_model_name,
    llm_model,
)
from domain.models import AgentReply, Chunk, Completion, Message, RetrievedChunk, ToolCall
from domain.ports import Tool

QUESTION = "what grease should I use?"
KNOBS = (
    "LLM_MODEL",
    "LLM_FALLBACK_MODEL",
    "EMBEDDING_MODEL",
    "RETRIEVAL_K",
    "AGENT_MAX_TOOL_ROUNDS",
    "QUERY_KNOWLEDGE_ENABLED",
)


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


def test_embedding_model_defaults_to_the_gemini_embedding_model():
    assert embedding_model_name() == "google:gemini-embedding-001"
    assert embedding_dimensions() == 3072


def test_small_openai_embedding_model_is_a_supported_choice(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "openai:text-embedding-3-small")

    assert embedding_dimensions() == 1536


def test_unprefixed_or_unknown_embedding_models_are_rejected_naming_the_choices(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")

    with pytest.raises(ValueError, match="openai:text-embedding-3-small"):
        embedding_model_name()


@pytest.fixture
def provider_keys(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")


def test_llm_defaults_to_gpt_5_mini_with_a_gemini_flash_fallback(provider_keys):
    model = llm_model()

    assert isinstance(model, FallbackModel)
    assert [m.model_name for m in model.models] == ["gpt-5-mini", "gemini-3.5-flash"]


def test_env_knobs_choose_the_primary_and_the_fallback_model(
    provider_keys, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("LLM_MODEL", "openai-chat:gpt-5")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "google:gemini-3.5-flash-lite")

    model = llm_model()

    assert isinstance(model, FallbackModel)
    assert [m.model_name for m in model.models] == ["gpt-5", "gemini-3.5-flash-lite"]


def test_blank_fallback_model_disables_the_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "  ")

    assert llm_model() == "openai:gpt-5-mini"
