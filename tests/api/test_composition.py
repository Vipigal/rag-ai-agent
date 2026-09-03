from pydantic_ai.models.fallback import FallbackModel

import pytest
from qdrant_client.http.exceptions import ApiException

from api.composition import (
    build_agent_service,
    build_llm,
    embedding_dimensions,
    embedding_model_name,
    get_qdrant_client,
    get_vector_store,
    llm_model,
    llm_settings,
    llm_thinking_name,
    validate_configuration,
)
from domain.models import AgentReply, Chunk, Completion, Message, RetrievedChunk, ToolCall
from domain.ports import Tool

QUESTION = "what grease should I use?"
KNOBS = (
    "LLM_MODEL",
    "LLM_FALLBACK_MODEL",
    "LLM_THINKING",
    "EMBEDDING_MODEL",
    "RETRIEVAL_K",
    "AGENT_MAX_TOOL_ROUNDS",
    "QUERY_KNOWLEDGE_ENABLED",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "QDRANT_URL",
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
    retriever, llm = FakeRetriever(), FakeLLM([final("Polyrex", ["Mobil Polyrex EM"])])

    build_agent_service(retriever, llm).answer(QUESTION)

    assert retriever.calls == [(QUESTION, 5)]
    assert llm.tools_offered == [["query_knowledge"]]


def test_env_knobs_override_k_and_disable_the_tool(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RETRIEVAL_K", "2")
    monkeypatch.setenv("QUERY_KNOWLEDGE_ENABLED", "false")
    retriever, llm = FakeRetriever(), FakeLLM([final("Polyrex", ["Mobil Polyrex EM"])])

    build_agent_service(retriever, llm).answer(QUESTION)

    assert retriever.calls == [(QUESTION, 2)]
    assert llm.tools_offered == [[]]


def test_env_knob_caps_the_tool_rounds(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_MAX_TOOL_ROUNDS", "1")
    llm = FakeLLM([tool_request("grease"), final("Polyrex", ["Mobil Polyrex EM"])])
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


def test_thinking_defaults_to_low_effort():
    assert llm_thinking_name() == "low"
    assert llm_settings() == {"thinking": "low"}


def test_env_knob_picks_the_thinking_level(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_THINKING", " Minimal ")

    assert llm_thinking_name() == "minimal"
    assert llm_settings() == {"thinking": "minimal"}


def test_thinking_off_disables_reasoning_where_the_model_allows_it(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_THINKING", "off")

    assert llm_thinking_name() == "off"
    assert llm_settings() == {"thinking": False}


def test_blank_thinking_leaves_the_provider_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_THINKING", "  ")

    assert llm_thinking_name() is None
    assert llm_settings() is None


def test_unknown_thinking_level_is_rejected_naming_the_choices(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_THINKING", "turbo")

    with pytest.raises(ValueError, match="minimal, low, medium, high, xhigh, off"):
        llm_settings()


def test_build_llm_wires_the_fallback_model_with_the_thinking_settings(provider_keys):
    llm = build_llm()

    assert llm.settings == {"thinking": "low"}


@pytest.fixture
def fresh_stores():
    get_qdrant_client.cache_clear()
    get_vector_store.cache_clear()
    yield
    get_qdrant_client.cache_clear()
    get_vector_store.cache_clear()


def test_validation_names_the_missing_openai_key_and_what_needs_it(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")

    with pytest.raises(ValueError, match=r"OPENAI_API_KEY is not set.*LLM_MODEL=openai:gpt-5-mini.*\.env"):
        validate_configuration()


def test_validation_names_the_missing_gemini_key_under_the_name_the_readme_uses(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")

    with pytest.raises(ValueError, match=r"GEMINI_API_KEY is not set.*EMBEDDING_MODEL=google:gemini-embedding-001"):
        validate_configuration()


def test_validation_accepts_google_api_key_as_the_gemini_key(provider_keys, monkeypatch: pytest.MonkeyPatch, fresh_stores):
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6399")

    with pytest.raises(ApiException):
        validate_configuration()


def test_validation_does_not_ask_for_a_key_no_configured_model_uses(monkeypatch: pytest.MonkeyPatch, fresh_stores):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "openai:text-embedding-3-small")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6399")

    with pytest.raises(ApiException):
        validate_configuration()


def test_validation_rejects_bad_config_values_before_touching_any_dependency(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_THINKING", "turbo")

    with pytest.raises(ValueError, match="LLM_THINKING"):
        validate_configuration()


def test_validation_reaches_the_vector_store_last(provider_keys, monkeypatch: pytest.MonkeyPatch, fresh_stores):
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6399")

    with pytest.raises(ApiException, match="Connection refused"):
        validate_configuration()


def test_an_explicit_k_overrides_the_env_knob(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RETRIEVAL_K", "2")
    retriever, llm = FakeRetriever(), FakeLLM([final("Polyrex", ["Mobil Polyrex EM"])])

    build_agent_service(retriever, llm, k=3).answer(QUESTION)

    assert retriever.calls == [(QUESTION, 3)]
