import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from domain.models import AgentReply, Completion, Message, ToolCall
from llm.pydantic_ai_llm import PydanticAiLLM

SYSTEM = Message(role="system", content="Answer from the chunks.")
CONTEXT = Message(role="system", content='<chunks>\n<chunk id="c1" …>\n</chunks>')
USER = Message(role="user", content="power?")
REPLY_JSON = '{"answer": "2.3 kW", "citations": ["c1"], "has_answer": true}'


def query_knowledge(query: str) -> str:
    """Search the indexed documents for more chunks.

    Args:
        query: The search query, reformulated freely.
    """
    return "<chunks/>"


class ScriptedProvider:
    def __init__(self, response: ModelResponse) -> None:
        self._response = response
        self.messages: list[ModelMessage] = []
        self.info: AgentInfo | None = None

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.messages = list(messages)
        self.info = info
        return self._response


def make_llm(response: ModelResponse) -> tuple[PydanticAiLLM, ScriptedProvider]:
    provider = ScriptedProvider(response)
    return PydanticAiLLM(FunctionModel(provider)), provider


def seen_info(provider: ScriptedProvider) -> AgentInfo:
    assert provider.info is not None
    return provider.info


def test_prompt_messages_reach_the_provider_as_one_request_with_one_part_per_message():
    llm, provider = make_llm(ModelResponse(parts=[TextPart(REPLY_JSON)]))

    llm.complete([SYSTEM, CONTEXT, USER], [])

    [request] = provider.messages
    assert isinstance(request, ModelRequest)
    rules, context, question = request.parts
    assert isinstance(rules, SystemPromptPart) and rules.content == SYSTEM.content
    assert isinstance(context, SystemPromptPart) and context.content == CONTEXT.content
    assert isinstance(question, UserPromptPart) and question.content == USER.content


def test_a_python_function_becomes_a_strict_tool_definition_described_by_its_docstring():
    llm, provider = make_llm(ModelResponse(parts=[TextPart(REPLY_JSON)]))

    llm.complete([SYSTEM, USER], [query_knowledge])

    [tool] = seen_info(provider).function_tools
    assert tool.name == "query_knowledge"
    assert tool.description == "Search the indexed documents for more chunks."
    assert tool.strict is True
    assert tool.parameters_json_schema == {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query, reformulated freely."}
        },
        "required": ["query"],
        "additionalProperties": False,
    }


def test_no_tools_means_no_function_tools_offered():
    llm, provider = make_llm(ModelResponse(parts=[TextPart(REPLY_JSON)]))

    llm.complete([SYSTEM, USER], [])

    assert seen_info(provider).function_tools == []


def test_the_reply_schema_is_requested_as_strict_native_structured_output():
    llm, provider = make_llm(ModelResponse(parts=[TextPart(REPLY_JSON)]))

    llm.complete([SYSTEM, USER], [query_knowledge])

    params = seen_info(provider).model_request_parameters
    assert params.output_mode == "native"
    assert params.output_object is not None
    assert params.output_object.name == "AgentReply"
    assert params.output_object.strict is True
    assert set(params.output_object.json_schema["properties"]) == {"answer", "citations", "has_answer"}
    assert set(params.output_object.json_schema["required"]) == {"answer", "citations", "has_answer"}


def test_a_json_text_response_becomes_a_validated_reply():
    llm, _ = make_llm(ModelResponse(parts=[TextPart(REPLY_JSON)]))

    completion = llm.complete([SYSTEM, USER], [query_knowledge])

    assert completion == Completion(
        message=Message(role="assistant", content=REPLY_JSON),
        reply=AgentReply(answer="2.3 kW", citations=["c1"], has_answer=True),
    )


def test_a_response_violating_the_reply_schema_is_rejected():
    llm, _ = make_llm(ModelResponse(parts=[TextPart('{"answer": "2.3 kW"}')]))

    with pytest.raises(ValueError):
        llm.complete([SYSTEM, USER], [])


def test_tool_call_parts_come_back_as_domain_tool_calls_without_a_reply():
    llm, _ = make_llm(
        ModelResponse(
            parts=[
                ToolCallPart("query_knowledge", {"query": "potência"}, tool_call_id="call_1"),
                ToolCallPart("query_knowledge", '{"query": "power"}', tool_call_id="call_2"),
            ]
        )
    )

    completion = llm.complete([SYSTEM, USER], [query_knowledge])

    assert completion.reply is None
    assert completion.message == Message(
        role="assistant",
        content="",
        tool_calls=(
            ToolCall(id="call_1", name="query_knowledge", arguments={"query": "potência"}),
            ToolCall(id="call_2", name="query_knowledge", arguments={"query": "power"}),
        ),
    )


def test_tool_exchange_history_is_replayed_as_response_and_tool_return_parts():
    llm, provider = make_llm(ModelResponse(parts=[TextPart(REPLY_JSON)]))
    call = ToolCall(id="call_1", name="query_knowledge", arguments={"query": "lubrication"})
    history = [
        SYSTEM,
        USER,
        Message(role="assistant", content="Let me search.", tool_calls=(call,)),
        Message(role="tool", content="<chunks/>", tool_call_id="call_1"),
    ]

    llm.complete(history, [query_knowledge])

    assert len(provider.messages) == 3
    response = provider.messages[1]
    assert isinstance(response, ModelResponse)
    assert response.parts == [
        TextPart("Let me search."),
        ToolCallPart("query_knowledge", {"query": "lubrication"}, tool_call_id="call_1"),
    ]
    tool_return = provider.messages[2]
    assert isinstance(tool_return, ModelRequest)
    [part] = tool_return.parts
    assert isinstance(part, ToolReturnPart)
    assert (part.tool_name, part.content, part.tool_call_id) == ("query_knowledge", "<chunks/>", "call_1")


def test_tool_message_answering_no_known_call_is_rejected_before_reaching_the_provider():
    llm, provider = make_llm(ModelResponse(parts=[TextPart(REPLY_JSON)]))
    orphan = Message(role="tool", content="<chunks/>", tool_call_id="call_missing")

    with pytest.raises(ValueError, match="call_missing"):
        llm.complete([SYSTEM, USER, orphan], [])

    assert provider.messages == []
