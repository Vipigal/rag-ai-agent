from pydantic import TypeAdapter, ValidationError
from pydantic_ai import Tool as FunctionTool
from pydantic_ai.exceptions import UnexpectedModelBehavior
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
from pydantic_ai.settings import ModelSettings

from domain.models import AgentReply, Completion, Message, ToolCall, Usage
from domain.ports import Tool

MAX_REPLY_ATTEMPTS = 2

REPLY_ADAPTER = TypeAdapter(AgentReply)

REPLY_OUTPUT = OutputObjectDefinition(
    name=AgentReply.__name__,
    json_schema=REPLY_ADAPTER.json_schema(),
    strict=True,
)


class PydanticAiLLM:
    def __init__(self, model: Model | str, settings: ModelSettings | None = None) -> None:
        self._model = model
        self._settings = settings

    @property
    def settings(self) -> ModelSettings | None:
        return self._settings

    def complete(self, messages: list[Message], tools: list[Tool]) -> Completion:
        provider_messages = _to_provider_messages(messages)
        parameters = ModelRequestParameters(
            function_tools=[FunctionTool(tool, strict=True).tool_def for tool in tools],
            output_mode="native",
            output_object=REPLY_OUTPUT,
        )
        usage = Usage()
        for attempt in range(MAX_REPLY_ATTEMPTS):
            response = model_request_sync(
                self._model,
                provider_messages,
                model_settings=self._settings,
                model_request_parameters=parameters,
            )
            usage += _to_usage(response)
            message = _to_domain_message(response)
            if message.tool_calls:
                return Completion(message=message, reply=None, usage=usage)
            try:
                reply = REPLY_ADAPTER.validate_json(message.content)
            except ValidationError as error:
                if attempt == MAX_REPLY_ATTEMPTS - 1:
                    raise UnexpectedModelBehavior(
                        f"the LLM returned a malformed reply {MAX_REPLY_ATTEMPTS} times: {error}",
                        body=message.content,
                    ) from error
                continue
            return Completion(message=message, reply=reply, usage=usage)
        raise AssertionError("unreachable: every attempt returns or raises")


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


def _to_usage(response: ModelResponse) -> Usage:
    details = response.usage.details
    return Usage(
        requests=1,
        input_tokens=response.usage.input_tokens,
        cache_read_tokens=response.usage.cache_read_tokens,
        output_tokens=response.usage.output_tokens,
        reasoning_tokens=details.get("reasoning_tokens", 0) + details.get("thoughts_tokens", 0),
        cost_usd=_cost_usd(response),
    )


def _cost_usd(response: ModelResponse) -> float:
    if not response.model_name:
        return 0.0
    try:
        return float(response.cost().total_price)
    except LookupError:
        return 0.0
