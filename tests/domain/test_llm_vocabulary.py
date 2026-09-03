from dataclasses import FrozenInstanceError

import pytest

from domain.models import AgentReply, Answer, Chunk, Completion, Message, Reference, ToolCall, Usage


def _chunk(text: str) -> Chunk:
    return Chunk(
        id="c1",
        document_id="d1",
        filename="manual.pdf",
        text=text,
        page=3,
        section=None,
        index_in_doc=0,
    )


def test_message_defaults_to_no_tool_calls_and_no_tool_call_id():
    message = Message(role="user", content="qual a potência do motor?")

    assert message.tool_calls == ()
    assert message.tool_call_id is None


def test_message_links_a_tool_result_to_the_call_it_answers():
    call = ToolCall(id="call_1", name="query_knowledge", arguments={"query": "potência"})
    request = Message(role="assistant", content="", tool_calls=(call,))
    result = Message(role="tool", content="<chunk id=\"c1\" …>", tool_call_id="call_1")

    assert request.tool_calls[0].arguments == {"query": "potência"}
    assert result.tool_call_id == request.tool_calls[0].id


def test_completion_carries_either_a_final_reply_or_a_tool_requesting_message():
    final = Completion(
        message=Message(role="assistant", content='{"answer": "2.3 kW", …}'),
        reply=AgentReply(answer="2.3 kW", citations=["c1"], has_answer=True),
    )
    asking = Completion(
        message=Message(
            role="assistant",
            content="",
            tool_calls=(ToolCall(id="call_1", name="query_knowledge", arguments={"query": "kW"}),),
        ),
        reply=None,
    )

    assert final.reply is not None and final.reply.citations == ["c1"]
    assert asking.reply is None and asking.message.tool_calls[0].name == "query_knowledge"


def test_vocabulary_entities_are_immutable():
    reply = AgentReply(answer="2.3 kW", citations=[], has_answer=True)
    answer = Answer(text="2.3 kW", references=[Reference(chunk=_chunk("2.3 kW"), quote="2.3 kW")])

    with pytest.raises(FrozenInstanceError):
        setattr(reply, "answer", "changed")
    with pytest.raises(FrozenInstanceError):
        setattr(answer, "text", "changed")


def test_answer_references_pair_the_quoted_passage_with_its_chunk_and_source():
    reference = Reference(chunk=_chunk("The motor draws 2.3 kW."), quote="draws 2.3 kW", retrieval_source="tool")

    answer = Answer(text="The motor draws 2.3 kW.", references=[reference])

    assert answer.references[0].chunk.filename == "manual.pdf"
    assert answer.references[0].chunk.page == 3
    assert answer.references[0].quote == "draws 2.3 kW"
    assert answer.references[0].retrieval_source == "tool"
    assert Reference(chunk=_chunk("x"), quote="x").retrieval_source == "seed"
    assert answer.unmatched_citations == []


def test_usage_defaults_to_zero_and_adds_field_wise():
    first = Usage(requests=1, input_tokens=2300, output_tokens=140)
    second = Usage(requests=1, tool_calls=1, input_tokens=4100, cache_read_tokens=2200, output_tokens=160)

    assert Usage() == Usage(requests=0, tool_calls=0, input_tokens=0, cache_read_tokens=0, output_tokens=0)
    assert first + second == Usage(
        requests=2, tool_calls=1, input_tokens=6400, cache_read_tokens=2200, output_tokens=300
    )


def test_completion_and_answer_carry_usage_and_the_answer_a_refusal_flag_with_defaults():
    completion = Completion(message=Message(role="assistant", content="{…}"), reply=None)
    answer = Answer(text="2.3 kW", references=[])

    assert completion.usage == Usage()
    assert answer.usage == Usage()
    assert answer.has_answer is True
    assert answer.unmatched_citations == []
    assert Answer(text="Não sei.", references=[], has_answer=False).has_answer is False
