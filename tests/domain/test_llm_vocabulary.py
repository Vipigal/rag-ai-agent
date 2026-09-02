from dataclasses import FrozenInstanceError

import pytest

from domain.models import AgentReply, Answer, Chunk, Completion, Message, RetrievedChunk, ToolCall


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
    answer = Answer(text="2.3 kW", references=[RetrievedChunk(chunk=_chunk("2.3 kW"), score=0.9)])

    with pytest.raises(FrozenInstanceError):
        setattr(reply, "answer", "changed")
    with pytest.raises(FrozenInstanceError):
        setattr(answer, "text", "changed")


def test_answer_references_keep_the_structured_retrieved_chunks():
    retrieved = RetrievedChunk(chunk=_chunk("2.3 kW"), score=0.9, retrieval_source="tool")

    answer = Answer(text="The motor draws 2.3 kW.", references=[retrieved])

    assert answer.references[0].chunk.filename == "manual.pdf"
    assert answer.references[0].chunk.page == 3
    assert answer.references[0].retrieval_source == "tool"
