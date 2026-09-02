from pydantic import TypeAdapter
from pydantic_ai import Tool as FunctionTool
from pydantic_ai.direct import model_request_sync
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ModelResponsePart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.output import OutputObjectDefinition

from domain.models import AgentReply, Completion, Message, ToolCall
from domain.ports import Tool

REPLY_ADAPTER = TypeAdapter(AgentReply)

REPLY_OUTPUT = OutputObjectDefinition(
    name=AgentReply.__name__,
    json_schema=REPLY_ADAPTER.json_schema(),
    strict=True,
)


class PydanticAiLLM:
    def __init__(self, model: Model | str) -> None:
        self._model = model

    def complete(self, messages: list[Message], tools: list[Tool]) -> Completion:
        response = model_request_sync(
            self._model,
            _to_provider_messages(messages),
            model_request_parameters=ModelRequestParameters(
                function_tools=[FunctionTool(tool, strict=True).tool_def for tool in tools],
                output_mode="native",
                output_object=REPLY_OUTPUT,
            ),
        )
        message = _to_domain_message(response)
        reply = None if message.tool_calls else REPLY_ADAPTER.validate_json(message.content)
        return Completion(message=message, reply=reply)


def _to_provider_messages(messages: list[Message]) -> list[ModelMessage]:
    provider_messages: list[ModelMessage] = []
    pending_request: list[ModelRequestPart] = []
    tool_names: dict[str, str] = {}
    for message in messages:
        if message.role == "assistant":
            if pending_request:
                provider_messages.append(ModelRequest(parts=pending_request))
                pending_request = []
            tool_names.update((call.id, call.name) for call in message.tool_calls)
            provider_messages.append(_to_model_response(message))
        else:
            pending_request.append(_to_request_part(message, tool_names))
    if pending_request:
        provider_messages.append(ModelRequest(parts=pending_request))
    return provider_messages


def _to_model_response(message: Message) -> ModelResponse:
    parts: list[ModelResponsePart] = []
    if message.content:
        parts.append(TextPart(message.content))
    parts.extend(
        ToolCallPart(call.name, dict(call.arguments), tool_call_id=call.id)
        for call in message.tool_calls
    )
    return ModelResponse(parts=parts)


def _to_request_part(message: Message, tool_names: dict[str, str]) -> ModelRequestPart:
    if message.role == "system":
        return SystemPromptPart(message.content)
    if message.role == "tool":
        call_id = message.tool_call_id
        tool_name = tool_names.get(call_id) if call_id is not None else None
        if call_id is None or tool_name is None:
            raise ValueError(
                f"tool message with tool_call_id={call_id!r} answers no preceding "
                "assistant tool call"
            )
        return ToolReturnPart(tool_name=tool_name, content=message.content, tool_call_id=call_id)
    return UserPromptPart(message.content)


def _to_domain_message(response: ModelResponse) -> Message:
    return Message(
        role="assistant",
        content=response.text or "",
        tool_calls=tuple(
            ToolCall(id=part.tool_call_id, name=part.tool_name, arguments=part.args_as_dict())
            for part in response.tool_calls
        ),
    )
