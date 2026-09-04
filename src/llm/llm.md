---
type: Module
title: LLM Module
description: The LLM port's adapter stage — PydanticAiLLM over pydantic_ai.direct, one provider call per complete() that offers function-derived strict tools, demands the AgentReply schema as native structured output and carries the model settings the composition root chose — and what its code cannot say: the sync-only constraint that keeps the question route a plain def, schema derivation and validation with TypeAdapter, message grouping and tool_name-by-id resolution, which exceptions reach the API edge as 502 versus 500, that openai: resolves to the Responses API, the FallbackModel wiring and why gemini-3.5-flash is the fallback, why the thinking level is low by default (reasoning tokens were 85–94 % of the output and the whole latency), how usage carries reasoning tokens and a priced cost, why a malformed reply is requested once more before it becomes a 502 and where every exception class lands at the API edge, and how to test against FunctionModel.
tags: [llm, adapter, pydantic-ai, structured-output, tool-calling, provider-errors, thinking, latency, cost]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-03T00:40:00Z }
verified: { by: human:vinicius, at: 2026-09-02T02:46:00Z }
sources:
  - id: decision-0008
    resource: /docs/decisions/0008-question-agent-baseline.md
    title: 0008 — Question agent baseline
  - id: decision-0009
    resource: /docs/decisions/0009-structured-reply-function-tools.md
    title: 0009 — Structured agent reply, function-derived tools, chunk ids as citation handles
  - id: llm-evidence
    resource: /docs/research/llm-adapter-library-evidence.md
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
- **A response that violates the reply schema is requested once more,
  then rejected as the model's fault.** With strict native output the
  provider guarantees the JSON matches the schema, yet the answer eval saw
  one malformed reply in 93 (trailing characters after the object), so
  `complete()` loops over `MAX_REPLY_ATTEMPTS = 2`: a `ValidationError`
  from `validate_json` on the first attempt sends the same request again;
  on the second it raises `pydantic_ai.exceptions.UnexpectedModelBehavior`
  with the offending text as `body`, which the API maps to
  **502 "LLM reply unusable: …"** ([Decision 0014](/docs/decisions/0014-error-semantics-and-startup-validation.md),
  reversing the deliberate 500 of Decision 0009). Both attempts count in
  `Usage`. A response carrying tool calls is never parsed as a reply,
  whatever text it also carries. The unreachable case in which the model
  still requests tools after the cap is `domain.errors.ToolRoundsExhausted`,
  also a 502.
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
  `ModelAPIError`. Since Decision 0014 it no longer reaches a question:
  `validate_configuration()` at the composition root builds the LLM inside
  the FastAPI lifespan, so a missing key or an unknown prefix fails the
  **startup** with the message in the `make up` terminal (and before that,
  `make check-env` refuses an empty key). Should a `UserError` still
  surface at request time, `api/errors.py` answers **503 "provider not
  configured: …"** with `GOOGLE_API_KEY` rewritten to the `GEMINI_API_KEY`
  the README documents (pydantic-ai's `GoogleProvider` accepts both).
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
  now runs through pydantic-ai's `Embedder`). Google's model and embedding
  adapters wrap `genai.errors.APIError` into `ModelHTTPError` too, so the
  fallback provider needs no handler of its own. The full map — 422 for
  the request, 502 for providers and unusable replies, 503 for the vector
  store and the configuration, 500 only as a catch-all that names the
  exception — is `register_exception_handlers` in `src/api/errors.py`
  (Decision 0014).
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
- **The thinking level is a setting, chosen at the composition root, low
  by default.** `PydanticAiLLM(model, settings=ModelSettings(thinking=…))`
  forwards the settings to every `model_request_sync`; `build_llm()` in
  `api/composition.py` reads **`LLM_THINKING`** (`minimal`, `low`,
  `medium`, `high`, `xhigh`, `off`; blank keeps the provider default;
  anything else is rejected naming the choices) and both the route and
  the eval build the LLM through it, so a run measures what the API
  ships. pydantic-ai's unified `thinking` field is what makes one knob
  cover the fallback: `Model.prepare_request` strips it from the settings
  and puts it on `ModelRequestParameters.thinking` **only when the
  model's profile says `supports_thinking`** — `gpt-5-mini` becomes
  `reasoning.effort` on the Responses API, `gemini-3.5-flash` a
  `thinking_level`; a model without support ignores it silently (profiles
  checked 2026-09-02: `gpt-5*` and `gemini-3.5-flash*` support it,
  `gpt-4o` does not). Why low: measured 2026-09-02 on the answer eval,
  latency correlates 0.92 with output tokens at ≈ 10.6 ms per token, and
  at the provider default (medium) **reasoning tokens were 85–94 % of the
  output** — the 23 s case spent 1,920 of its 2,048 output tokens
  reasoning to quote 130. The same three questions: default 6.5 / 12.0 /
  23.6 s, `low` 4.4 / 3.1 / 5.2 s, `minimal` 2.6 / 2.6 / 5.1 s — but
  `minimal` produced a number that was not in the table on one of them,
  so `low` is the default and the answer eval decides (see the
  [findings](/evals/results/experiment-findings.md)). Quotes, retrieval
  (≈ 0.5 s, the Gemini query embedding) and the 4–5 k input tokens were
  ruled out as causes.
- **Usage carries reasoning tokens and a priced cost.** `_to_usage` reads
  `response.usage.details["reasoning_tokens"]` (OpenAI) plus
  `["thoughts_tokens"]` (Google) into `Usage.reasoning_tokens` — they are
  already inside `output_tokens`, this only names them — and prices the
  response with `ModelResponse.cost()`, pydantic-ai's binding of
  **genai-prices** (`total_price`, input discounted for cache reads, as
  `Usage.cost_usd`). A model the price table does not know
  (`LookupError`; `FunctionModel` in tests) costs `0.0` rather than
  failing the request, and a response without `model_name` is not priced.
  Embedding calls are not in the domain's `Usage` and are not priced —
  their per-question cost is measured separately in the findings and is
  three orders of magnitude below the LLM's.

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
- **`FunctionModel` stamps its own `model_name` and needs a profile to
  route `thinking`.** It overwrites `response.model_name` with
  `function:<fn>:` (pass `model_name="gpt-5-mini"` to test pricing) and its
  default profile has `supports_thinking=False`, so the unified setting is
  dropped before the function sees it — give it
  `ModelProfile(supports_json_schema_output=True,
  supports_json_object_output=True, supports_thinking=True)` and assert on
  `AgentInfo.model_request_parameters.thinking`, not on `model_settings`.
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
