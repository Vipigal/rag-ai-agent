---
type: Module
title: LLM Module
description: The LLM port's adapter stage — PydanticAiLLM over pydantic_ai.direct, one provider call per complete() that offers function-derived strict tools and demands the AgentReply schema as native structured output — and what its code cannot say: the sync-only constraint that keeps the question route a plain def, schema derivation and validation with TypeAdapter, message grouping and tool_name-by-id resolution, which exceptions reach the API edge as 502 versus 500, that openai: resolves to the Responses API, the FallbackModel wiring and why gemini-3.5-flash is the fallback, and how to test against FunctionModel.
tags: [llm, adapter, pydantic-ai, structured-output, tool-calling, provider-errors]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T02:30:26Z }
verified: { by: human:vinicius, at: 2026-09-02T02:46:00Z }
sources:
  - id: spec
    resource: /specs/question-agent-design.md
    title: Question Agent — Design & Implementation Plan
  - id: decision-0008
    resource: /docs/decisions/0008-question-agent-baseline.md
    title: 0008 — Question agent baseline
  - id: decision-0009
    resource: /docs/decisions/0009-structured-reply-function-tools.md
    title: 0009 — Structured agent reply, function-derived tools, chunk ids as citation handles
  - id: llm-evidence
    resource: /research/llm-adapter-library-evidence.md
    title: LLM Adapter Library Evidence
  - id: arch
    resource: /docs/architecture.md
    title: System Architecture — Ports & Adapters Lite
  - id: pai-direct
    resource: https://pydantic.dev/docs/ai/core-concepts/direct/
    title: PydanticAI docs — Direct model requests
---

# What this module is

The adapter stage for the `LLM` port: `PydanticAiLLM` implements
`complete(messages, tools) -> Completion` with exactly **one**
`pydantic_ai.direct.model_request_sync` call. Per call it translates the
domain's `Message` history into PydanticAI message parts, turns each
tool — a plain Python function — into a strict `ToolDefinition`, and
requests the domain's `AgentReply` dataclass as **native structured
output**; the response comes back either as tool calls (unexecuted, the
loop stays in `AgentService` — architecture rule 9[^arch]) or as JSON
validated into an `AgentReply`. The library choice is [Decision
0008](/docs/decisions/0008-question-agent-baseline.md);[^decision-0008]
the structured-output and function-tool contract is [Decision
0009](/docs/decisions/0009-structured-reply-function-tools.md).[^decision-0009]
Pinned: `pydantic-ai-slim[openai]==2.37.0`.

# What the code cannot say

- **Sync-only, and the route depends on it.** `model_request_sync` wraps
  the async call in `loop.run_until_complete(...)` and refuses to run
  inside an active event loop. `POST /question` is therefore a plain
  `def` — FastAPI runs it on the threadpool, where no loop is running.
  Turning `ask_question` into `async def` would fail at runtime on the
  first real question, and the route tests would **not** catch it: they
  override the service with a fake, so the adapter never runs there. The
  eval harness is a synchronous CLI and is unaffected. If an async path is
  ever wanted, the adapter grows an `acomplete` over `model_request` —
  a port change, so a decision record.
- **Pydantic does the schema work, from stdlib dataclasses.** The domain
  stays Pydantic-free (rule 1[^arch]) because `TypeAdapter(AgentReply)`
  generates the JSON schema from the frozen dataclass and
  `validate_json` builds the instance back. The schema is computed once
  at import (`REPLY_OUTPUT`) with `strict=True`; the OpenAI models then
  run PydanticAI's strict transformer on it (`additionalProperties:
false`, every property required). The output object and the function
  tools travel in the **same request** — the model either calls a tool
  or emits the final JSON.
- **Tools are derived, not declared.** `pydantic_ai.Tool(fn,
strict=True).tool_def` reads the function's signature and docstring:
  name from `__name__`, description from the docstring's first
  paragraph, parameter descriptions from its `Args:` section (griffe
  parses Google, NumPy and Sphinx styles). This is why the tool
  description is the only prompt text living outside `prompts.py` — it is
  runtime data, not a comment. A tool without type hints or with a
  parameter griffe cannot describe still works; it just ships a poorer
  schema.
- **A response that violates the reply schema raises.** With strict
  native output the provider guarantees the JSON matches the schema, so a
  `ValidationError` (a `ValueError`) from `validate_json` means a
  provider or configuration bug, not user input. It is deliberately
  **not** mapped to 502 — it surfaces as a 500 so it is investigated, not
  retried. A response carrying tool calls is never parsed as a reply,
  whatever text it also carries.
- **`openai:` means the Responses API.** In pydantic-ai 2.37.0
  `infer_model("openai:<name>")` resolves to `OpenAIResponsesModel`, not
  Chat Completions (verified locally, 2026-09-01). The default
  `LLM_MODEL=openai:gpt-5-mini` therefore talks to `/v1/responses`, where
  structured output is `text.format`; `openai-chat:<name>` selects
  `OpenAIChatModel` (Chat Completions, `response_format`) and
  `openai-responses:<name>` is the explicit spelling. Both accept the
  same tool definitions and output object, so the adapter is
  indifferent — but latency or behavior comparisons between the two are
  eval work, not a code change.
- **Model resolution is lazy.** A model string is resolved on the first
  `complete()`, not when `PydanticAiLLM` is constructed. A missing
  `OPENAI_API_KEY` or an unknown provider prefix (`nonexistent:model`)
  raises `pydantic_ai.exceptions.UserError` — a `RuntimeError`, **not** a
  `ModelAPIError` — so it surfaces as a **500 on the first question**,
  not at startup and not as a 502. Configuration errors are 500 on
  purpose; only upstream provider failures are 502 (next item).
- **Which exceptions reach the API edge as 502.** PydanticAI's OpenAI
  models wrap the SDK's `APIStatusError` (status ≥ 400) into
  `ModelHTTPError` and `APIConnectionError` into `ModelAPIError`;
  `ModelHTTPError` subclasses `ModelAPIError`, so `api/main.py`'s single
  `ModelAPIError` handler covers both ("LLM provider error", 502). When
  every model of the `FallbackModel` fails, pydantic-ai raises
  `FallbackExceptionGroup` — an `ExceptionGroup`, **not** a
  `ModelAPIError` — so a third handler answers 502 listing each model's
  error ("every LLM provider failed: …"). The `openai.OpenAIError`
  handler stays for SDK errors that escape unwrapped (the query embedding
  now runs through pydantic-ai's `Embedder`). Three handlers, same
  status.
- **Message grouping.** PydanticAI histories alternate `ModelRequest`
  (system/user/tool-return parts) and `ModelResponse` (text/tool-call
  parts). The adapter folds every run of consecutive request-side domain
  messages into one `ModelRequest` and each `assistant` message into one
  `ModelResponse` (a `TextPart` only when `content` is non-empty, then the
  `ToolCallPart`s). This reproduces the alternating shape PydanticAI's own
  agent loop emits, so every provider mapping in the library sees the
  history it was written for. The two opening `system` messages (rules,
  then the XML-rendered chunks) become two `SystemPromptPart`s in one
  request; for the Responses API each is its own `system` input item.
- **`tool_name` is resolved by id.** `ToolReturnPart` requires the tool's
  name, which the domain's `tool` `Message` does not carry (it links by
  `tool_call_id` only). The adapter learns names from the preceding
  `assistant` tool calls in the same history and looks the id up. A
  `tool` message whose id matches no earlier call is a
  history-construction bug in the caller; the adapter raises `ValueError`
  **before** any provider call, so the bug shows up locally with the
  offending id instead of as an opaque 400 from OpenAI.
- **Tool-call arguments arrive as dict or JSON string.** OpenAI returns
  `arguments` as a JSON string; PydanticAI keeps it as given
  (`args: str | dict | None`). The adapter always hands the domain a dict
  via `args_as_dict()`, so `AgentService` can call the tool function
  with `**arguments`.
- **The fallback is wired at the composition root.** `llm_model()` in
  `api/composition.py` returns `FallbackModel(LLM_MODEL, LLM_FALLBACK_MODEL)`
  — default `openai:gpt-5-mini`, then `google:gemini-3.5-flash` — or the
  plain model string when `LLM_FALLBACK_MODEL` is blank. `FallbackModel`
  moves to the next model on `ModelAPIError` (4xx, 5xx, connection
  errors), which is the challenge's optional multi-provider behavior as
  one config value.[^llm-evidence] Nothing in `src/llm/` or the domain
  moved: Gemini takes the same strict tool definitions and native
  JSON-schema output. Verified 2026-09-02 through this adapter with a
  tool offered: `gemini-3.5-flash` answers the schema and cites correctly
  (1.9 s to 45 s observed — Gemini latency varies widely), and a
  nonexistent primary model (404) fell through to it end to end. Why not
  the others: **`gemini-2.5-flash` cannot be the fallback** — pydantic-ai
  2.37.0 refuses native output together with function tools for it
  (`UserError`, a 500, not a fallback trigger); `gemini-3.8-flash` kept
  calling the tool instead of answering in the probe; `gemini-3.7-flash`
  and `gemini-3.5-flash-lite` returned 503 "high demand" at the time, the
  very failure the fallback exists for. The fallback needs
  `GEMINI_API_KEY`, which the default embedder requires anyway.

# How to test the adapter

No network. `pydantic_ai.models.function.FunctionModel(fn)` calls
`fn(messages, info)` with the exact `ModelMessage` list the adapter built
and an `AgentInfo` whose `function_tools` are the `ToolDefinition`s it
offered and whose `model_request_parameters` expose `output_mode` and
`output_object`; it returns whatever `ModelResponse` the test scripts
(a JSON `TextPart`, or `ToolCallPart`s with dict or string args). Learned
in TDD (2026-09-01/02):

- **Compare part fields, not whole parts.** `SystemPromptPart`,
  `UserPromptPart`, `ToolReturnPart` and `ModelResponse` carry a
  `timestamp` defaulting to now that **participates in dataclass
  equality**, so `assert request.parts == [SystemPromptPart(...)]` is
  flaky. Assert `isinstance` plus `.content` / `(tool_name, content,
tool_call_id)`. `ToolCallPart` has no timestamp and compares cleanly.
- **`FunctionModel` runs no OpenAI transformer.** The output schema it
  sees is Pydantic's raw one (with `title` keys and no
  `additionalProperties`); the strict rewrite happens only in the OpenAI
  models. Tests assert the properties and `strict=True`, not the
  transformed shape. Tool schemas are already strict-shaped because
  `Tool(fn, strict=True)` emits them that way.
- **A sync `fn` is fine** — `FunctionModel` runs it in a worker thread
  under `model_request_sync`, so adapter tests are plain `def`s.

Provider behavior (does the model cite the right chunks, refuse
correctly, call the tool well) belongs to evals, never to these tests
(architecture rule 7[^arch]).

[^pai-direct]: PydanticAI docs — Direct model requests: caller-owned single call, tools returned unexecuted, `ModelRequestParameters` carrying tools and output mode, the sync variant's event-loop constraint.

[^decision-0008]: 0008 — Question agent baseline: PydanticAI direct chosen over OpenAI-SDK-direct; `FallbackModel` path kept open.

[^decision-0009]: 0009 — Structured agent reply, function-derived tools, chunk ids as citation handles: the contract this adapter implements.

[^llm-evidence]: LLM Adapter Library Evidence — measured dependency weight (+10 packages / 4.2 MB), `openai>=3.0.0` alignment, `FallbackModel`, Gemini extras and the OpenAI-compatible endpoint.

[^arch]: System Architecture — rules 1 (stdlib-only domain), 7 (LLM accuracy belongs to evals) and 9 (the loop lives in `AgentService`; the port speaks domain vocabulary).
