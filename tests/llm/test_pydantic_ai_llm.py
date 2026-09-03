import json
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
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from domain.models import AgentReply, Completion, Message, ToolCall, Usage
from llm.pydantic_ai_llm import PydanticAiLLM

SYSTEM = Message(role="system", content="Answer from the chunks.")
CONTEXT = Message(role="system", content='<chunks>\n<chunk id="c1" …>\n</chunks>')
USER = Message(role="user", content="power?")
REPLY_JSON = '{"answer": "2.3 kW", "citations": ["the motor draws 2.3 kW"], "has_answer": true}'


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


class SequencedProvider:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.calls += 1
        return self._responses.pop(0)


def malformed(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)], usage=RequestUsage(input_tokens=10, output_tokens=5))


def test_a_malformed_reply_is_requested_once_more_and_both_calls_count_in_the_usage():
    provider = SequencedProvider([malformed('{"answer": "x"} trailing'), malformed(REPLY_JSON)])
    llm = PydanticAiLLM(FunctionModel(provider))

    completion = llm.complete([SYSTEM, USER], [])

    assert provider.calls == 2
    assert completion.reply == AgentReply(answer="2.3 kW", citations=["the motor draws 2.3 kW"], has_answer=True)
    assert completion.usage.requests == 2
    assert completion.usage.output_tokens == 10


def test_a_second_malformed_reply_raises_unexpected_model_behavior_with_the_body():
    provider = SequencedProvider([malformed("not json"), malformed('{"answer": 1}')])
    llm = PydanticAiLLM(FunctionModel(provider))

    with pytest.raises(UnexpectedModelBehavior, match="malformed") as raised:
        llm.complete([SYSTEM, USER], [])

    assert provider.calls == 2
    assert raised.value.body is not None
    assert json.loads(raised.value.body) == {"answer": 1}


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

    assert completion.message == Message(role="assistant", content=REPLY_JSON)
    assert completion.reply == AgentReply(answer="2.3 kW", citations=["the motor draws 2.3 kW"], has_answer=True)


def test_a_response_violating_the_reply_schema_twice_is_rejected_as_unexpected_model_behavior():
    llm, provider = make_llm(ModelResponse(parts=[TextPart('{"answer": "2.3 kW"}')]))

    with pytest.raises(UnexpectedModelBehavior) as raised:
        llm.complete([SYSTEM, USER], [])

    assert isinstance(raised.value.__cause__, ValueError)
    assert provider.info is not None


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


def test_provider_usage_is_reported_as_one_request_with_its_token_counts():
    llm, _ = make_llm(
        ModelResponse(
            parts=[TextPart(REPLY_JSON)],
            usage=RequestUsage(input_tokens=2300, cache_read_tokens=1024, output_tokens=140),
        )
    )

    completion = llm.complete([SYSTEM, USER], [])

    assert completion.usage == Usage(
        requests=1, input_tokens=2300, cache_read_tokens=1024, output_tokens=140
    )


THINKING_PROFILE = ModelProfile(
    supports_json_schema_output=True, supports_json_object_output=True, supports_thinking=True
)


def test_the_thinking_level_reaches_a_model_that_supports_it_on_every_request():
    provider = ScriptedProvider(ModelResponse(parts=[TextPart(REPLY_JSON)]))
    model = FunctionModel(provider, profile=THINKING_PROFILE)
    llm = PydanticAiLLM(model, settings=ModelSettings(thinking="low"))

    llm.complete([SYSTEM, USER], [])

    assert seen_info(provider).model_request_parameters.thinking == "low"
    assert llm.settings == {"thinking": "low"}


def test_without_settings_the_provider_keeps_its_defaults():
    llm, provider = make_llm(ModelResponse(parts=[TextPart(REPLY_JSON)]))

    llm.complete([SYSTEM, USER], [])

    assert seen_info(provider).model_request_parameters.thinking is None
    assert seen_info(provider).model_settings is None
    assert llm.settings is None


def test_reasoning_tokens_and_the_priced_cost_of_a_known_model_reach_the_usage():
    usage = RequestUsage(
        input_tokens=5000, cache_read_tokens=3000, output_tokens=2000, details={"reasoning_tokens": 1800}
    )
    provider = ScriptedProvider(
        ModelResponse(parts=[TextPart(REPLY_JSON)], usage=usage, provider_name="openai")
    )
    llm = PydanticAiLLM(FunctionModel(provider, model_name="gpt-5-mini"))
    priced = ModelResponse(parts=[], usage=usage, model_name="gpt-5-mini", provider_name="openai")

    completion = llm.complete([SYSTEM, USER], [])

    assert completion.usage.reasoning_tokens == 1800
    assert completion.usage.cost_usd == pytest.approx(float(priced.cost().total_price))
    assert completion.usage.cost_usd > 0


def test_a_model_the_price_table_does_not_know_costs_nothing_and_does_not_raise():
    provider = ScriptedProvider(
        ModelResponse(
            parts=[TextPart(REPLY_JSON)],
            usage=RequestUsage(input_tokens=100, output_tokens=10),
            provider_name="openai",
        )
    )
    llm = PydanticAiLLM(FunctionModel(provider, model_name="gpt-99-ultra"))

    completion = llm.complete([SYSTEM, USER], [])

    assert completion.usage.cost_usd == 0.0
    assert completion.usage.reasoning_tokens == 0
