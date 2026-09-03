from dataclasses import replace

from domain.models import AgentReply, Chunk, Completion, Message, Reference, RetrievedChunk, ToolCall, Usage
from domain.ports import Tool
from domain.services.agent_service import AgentService
from domain.services.prompts import SYSTEM_PROMPT, render_chunks, render_context

QUESTION = "What is the power consumption of the motor?"


class FakeRetriever:
    def __init__(self, results: dict[str, list[RetrievedChunk]]) -> None:
        self._results = results
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]:
        self.calls.append((query, k))
        return self._results.get(query, [])[:k]


class FakeLLM:
    def __init__(self, script: list[Completion]) -> None:
        self._script = list(script)
        self.calls: list[tuple[list[Message], list[Tool]]] = []

    def complete(self, messages: list[Message], tools: list[Tool]) -> Completion:
        self.calls.append((list(messages), list(tools)))
        return self._script.pop(0)


def retrieved(
    chunk_id: str, text: str, score: float, page: int = 1, filename: str = "manual.pdf"
) -> RetrievedChunk:
    chunk = Chunk(
        id=chunk_id,
        document_id="doc",
        filename=filename,
        text=text,
        page=page,
        section=None,
        index_in_doc=0,
    )
    return RetrievedChunk(chunk=chunk, score=score)


def final(answer: str, citations: list[str], has_answer: bool = True) -> Completion:
    return Completion(
        message=Message(role="assistant", content="{…}"),
        reply=AgentReply(answer=answer, citations=citations, has_answer=has_answer),
    )


def tool_request(call_id: str, query: str, name: str = "query_knowledge") -> Completion:
    call = ToolCall(id=call_id, name=name, arguments={"query": query})
    return Completion(message=Message(role="assistant", content="", tool_calls=(call,)), reply=None)


def make_service(
    retriever: FakeRetriever,
    llm: FakeLLM,
    k: int = 5,
    max_tool_rounds: int = 3,
    tool_enabled: bool = True,
) -> AgentService:
    return AgentService(
        retriever=retriever,
        llm=llm,
        k=k,
        max_tool_rounds=max_tool_rounds,
        tool_enabled=tool_enabled,
    )


def tool_names(llm: FakeLLM) -> list[list[str]]:
    return [[tool.__name__ for tool in tools] for _, tools in llm.calls]


def reference(item: RetrievedChunk, quote: str, source: str = "seed") -> Reference:
    return Reference(chunk=item.chunk, quote=quote, retrieval_source=source)


VOLTAGE = "Nominal voltage 380 V"
POWER = "The motor draws 2.3 kW at 60 Hz"
GREASE = "Regrease every 8000 h with Mobil Polyrex EM"
SEED = [retrieved("c1", VOLTAGE, 0.9, page=3), retrieved("c2", POWER, 0.8, page=7)]
LUBRICATION = [retrieved("c3", GREASE, 0.6, page=42)]
AS_TOOL_RESULT = [replace(item, retrieval_source="tool") for item in LUBRICATION]


def test_seed_retrieval_uses_the_question_and_the_configured_k():
    retriever = FakeRetriever({QUESTION: SEED})

    make_service(retriever, FakeLLM([final("2.3 kW", [POWER])]), k=2).answer(QUESTION)

    assert retriever.calls == [(QUESTION, 2)]


def test_llm_receives_the_rules_then_the_retrieved_chunks_then_the_bare_question():
    llm = FakeLLM([final("2.3 kW", [POWER])])

    make_service(FakeRetriever({QUESTION: SEED}), llm).answer(QUESTION)

    messages, _ = llm.calls[0]
    assert [m.role for m in messages] == ["system", "system", "user"]
    assert messages[0].content == SYSTEM_PROMPT
    assert messages[1].content == render_context(SEED, tool_available=True)
    assert messages[2].content == QUESTION


def test_empty_index_is_presented_as_no_chunks():
    llm = FakeLLM([final("Não há documentos indexados.", [], has_answer=False)])

    make_service(FakeRetriever({}), llm).answer(QUESTION)

    messages, _ = llm.calls[0]
    assert "<chunks/>" in messages[1].content


def test_quoted_passages_become_references_in_citation_order_with_their_chunk():
    llm = FakeLLM([final("The motor draws 2.3 kW. It runs at 380 V.", [POWER, VOLTAGE])])

    answer = make_service(FakeRetriever({QUESTION: SEED}), llm).answer(QUESTION)

    assert answer.text == "The motor draws 2.3 kW. It runs at 380 V."
    assert answer.references == [reference(SEED[1], POWER), reference(SEED[0], VOLTAGE)]
    assert answer.has_answer is True
    assert answer.unmatched_citations == []


def test_a_fragment_quoted_loosely_still_resolves_to_its_chunk_and_is_returned_as_quoted():
    quote = "motor DRAWS   2.3 kw"
    llm = FakeLLM([final("2.3 kW", [quote])])

    answer = make_service(FakeRetriever({QUESTION: SEED}), llm).answer(QUESTION)

    assert answer.references == [reference(SEED[1], quote)]


def test_refusal_carries_no_references():
    llm = FakeLLM([final("Os documentos não informam a potência.", [], has_answer=False)])

    answer = make_service(FakeRetriever({QUESTION: SEED}), llm).answer(QUESTION)

    assert answer.text == "Os documentos não informam a potência."
    assert answer.references == []
    assert answer.has_answer is False


def test_an_answer_without_citations_has_no_references_and_no_seed_fallback():
    llm = FakeLLM([final("The motor draws 2.3 kW.", [])])

    answer = make_service(FakeRetriever({QUESTION: SEED}), llm).answer(QUESTION)

    assert answer.references == []
    assert answer.unmatched_citations == []


def test_quotes_found_in_no_chunk_are_dropped_and_counted_and_repeats_are_deduplicated():
    llm = FakeLLM([final("2.3 kW at 380 V.", [POWER, "a passage from nowhere", POWER.upper(), VOLTAGE])])

    answer = make_service(FakeRetriever({QUESTION: SEED}), llm).answer(QUESTION)

    assert answer.references == [reference(SEED[1], POWER), reference(SEED[0], VOLTAGE)]
    assert answer.unmatched_citations == ["a passage from nowhere"]


def test_a_quote_present_in_two_chunks_resolves_to_the_first_one_seen():
    twin = retrieved("c9", POWER, 0.5, page=70, filename="other.pdf")
    llm = FakeLLM([final("2.3 kW", [POWER])])

    answer = make_service(FakeRetriever({QUESTION: [*SEED, twin]}), llm).answer(QUESTION)

    assert answer.references == [reference(SEED[1], POWER)]


def test_garbled_context_refusal_does_not_fall_back_to_the_noise():
    garbled = [retrieved("g1", "�������� ���� ��� 2.3 ��", 0.7, filename="cestari.pdf")]
    llm = FakeLLM([final("The retrieved text is unreadable.", [], has_answer=False)])

    answer = make_service(FakeRetriever({QUESTION: garbled}), llm).answer(QUESTION)

    assert answer.references == []


def test_query_knowledge_is_offered_as_a_python_function_only_when_enabled_and_rounds_remain():
    enabled = FakeLLM([final("2.3 kW", [POWER])])
    disabled = FakeLLM([final("2.3 kW", [POWER])])
    capped = FakeLLM([final("2.3 kW", [POWER])])

    make_service(FakeRetriever({QUESTION: SEED}), enabled).answer(QUESTION)
    make_service(FakeRetriever({QUESTION: SEED}), disabled, tool_enabled=False).answer(QUESTION)
    make_service(FakeRetriever({QUESTION: SEED}), capped, max_tool_rounds=0).answer(QUESTION)

    assert tool_names(enabled) == [["query_knowledge"]]
    assert tool_names(disabled) == [[]]
    assert tool_names(capped) == [[]]
    assert "query_knowledge" not in disabled.calls[0][0][1].content


def test_tool_round_queries_the_same_retriever_and_appends_the_rendered_chunks():
    retriever = FakeRetriever({QUESTION: SEED, "lubrication interval": LUBRICATION})
    llm = FakeLLM([tool_request("call_1", "lubrication interval"), final("Every 8000 h.", [GREASE])])

    answer = make_service(retriever, llm, k=2).answer(QUESTION)

    assert retriever.calls == [(QUESTION, 2), ("lubrication interval", 2)]
    messages, _ = llm.calls[1]
    assert [m.role for m in messages] == ["system", "system", "user", "assistant", "tool"]
    assert messages[3] == tool_request("call_1", "lubrication interval").message
    assert messages[4].tool_call_id == "call_1"
    assert messages[4].content == render_chunks(AS_TOOL_RESULT)
    assert answer.text == "Every 8000 h."
    assert answer.references == [reference(LUBRICATION[0], GREASE, source="tool")]


def test_re_retrieved_chunk_is_shown_again_but_remembered_once_with_its_first_source():
    retriever = FakeRetriever({QUESTION: SEED, "motor power": [SEED[1], LUBRICATION[0]]})
    llm = FakeLLM([tool_request("call_1", "motor power"), final("2.3 kW; regrease.", [POWER, GREASE])])

    answer = make_service(retriever, llm).answer(QUESTION)

    tool_message = llm.calls[1][0][4].content
    assert tool_message.index(POWER) < tool_message.index(GREASE)
    assert answer.references == [reference(SEED[1], POWER), reference(LUBRICATION[0], GREASE, source="tool")]


def test_exhausted_tool_rounds_force_a_final_answer_without_tools():
    retriever = FakeRetriever({QUESTION: SEED, "lubrication interval": LUBRICATION})
    llm = FakeLLM([tool_request("call_1", "lubrication interval"), final("Every 8000 h.", [GREASE])])

    answer = make_service(retriever, llm, max_tool_rounds=1).answer(QUESTION)

    assert tool_names(llm) == [["query_knowledge"], []]
    assert retriever.calls == [(QUESTION, 5), ("lubrication interval", 5)]
    assert answer.text == "Every 8000 h."


def test_calling_an_unknown_tool_is_reported_back_to_the_model_instead_of_crashing():
    retriever = FakeRetriever({QUESTION: SEED})
    llm = FakeLLM([tool_request("call_x", "anything", name="nonexistent"), final("2.3 kW", [POWER])])

    answer = make_service(retriever, llm).answer(QUESTION)

    messages, _ = llm.calls[1]
    assert messages[4].role == "tool" and messages[4].tool_call_id == "call_x"
    assert "nonexistent" in messages[4].content
    assert retriever.calls == [(QUESTION, 5)]
    assert answer.references == [reference(SEED[1], POWER)]


def test_answer_sums_usage_over_the_tool_loop_and_counts_dispatched_tool_calls():
    retriever = FakeRetriever({QUESTION: SEED, "lubrication interval": LUBRICATION})
    asking = replace(
        tool_request("call_1", "lubrication interval"),
        usage=Usage(requests=1, input_tokens=2300, output_tokens=60),
    )
    answering = replace(
        final("Every 8000 h.", [GREASE]),
        usage=Usage(requests=1, input_tokens=4100, cache_read_tokens=2200, output_tokens=140),
    )

    answer = make_service(retriever, FakeLLM([asking, answering])).answer(QUESTION)

    assert answer.usage == Usage(
        requests=2, tool_calls=1, input_tokens=6400, cache_read_tokens=2200, output_tokens=200
    )


def test_the_reply_refusal_flag_reaches_the_answer():
    grounded = make_service(FakeRetriever({QUESTION: SEED}), FakeLLM([final("2.3 kW", [POWER])]))
    refusing = make_service(
        FakeRetriever({QUESTION: SEED}), FakeLLM([final("Não informa.", [], has_answer=False)])
    )

    assert grounded.answer(QUESTION).has_answer is True
    assert refusing.answer(QUESTION).has_answer is False
