---
type: Reference
title: LLM Adapter Library Evidence
description: Evidence gathered 2026-09-01 comparing candidate libraries for the LLM port adapter — OpenAI SDK direct, LangChain deepagents (vs plain init_chat_model), Strands Agents, PydanticAI, LiteLLM — on loop ownership, dependency weight, latency-overhead evidence, multi-provider support, and maturity, against the domain-owned tool loop of Decision 0005.
tags: [llm, adapters, tool-calling, frameworks, dependencies]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-01T16:26:51Z }
verified: { by: human:vinicius, at: 2026-09-01T17:25:00Z }
sources:
  - id: arch
    resource: /docs/architecture.md
    title: System Architecture — Ports & Adapters Lite
  - id: decision-0005
    resource: /docs/decisions/0005-retrieval-architecture.md
    title: "Decision 0005 — Retrieval architecture: strategy port, dual-path agent, Qdrant"
  - id: pypi-openai
    resource: https://pypi.org/project/openai/
    title: openai on PyPI (3.6.0, 2026-08-28)
  - id: openai-fc
    resource: https://developers.openai.com/api/docs/guides/function-calling
    title: OpenAI — Function calling guide
  - id: gemini-compat
    resource: https://ai.google.dev/gemini-api/docs/openai
    title: Google — OpenAI compatibility for the Gemini API
  - id: deepagents-gh
    resource: https://github.com/langchain-ai/deepagents
    title: langchain-ai/deepagents (GitHub)
  - id: pypi-deepagents
    resource: https://pypi.org/project/deepagents/
    title: deepagents on PyPI (0.7.11, 2026-08-28)
  - id: langchain-models
    resource: https://docs.langchain.com/oss/python/langchain/models
    title: LangChain 1.x docs — Models (init_chat_model, bind_tools)
  - id: strands-loop
    resource: https://strandsagents.com/docs/user-guide/concepts/agents/agent-loop/
    title: Strands Agents docs — Agent Loop
  - id: strands-gh
    resource: https://github.com/strands-agents/harness-sdk
    title: strands-agents/harness-sdk (GitHub)
  - id: strands-ga
    resource: https://aws.amazon.com/blogs/opensource/introducing-strands-agents-1-0-production-ready-multi-agent-orchestration-made-simple/
    title: AWS Open Source Blog — Introducing Strands Agents 1.0
  - id: pypi-strands
    resource: https://pypi.org/project/strands-agents/
    title: strands-agents on PyPI (1.54.0, 2026-08-27)
  - id: pai-direct
    resource: https://pydantic.dev/docs/ai/core-concepts/direct/
    title: PydanticAI docs — Direct model requests
  - id: pai-direct-api
    resource: https://pydantic.dev/docs/ai/api/pydantic-ai/direct/
    title: PydanticAI API reference — pydantic_ai.direct
  - id: pai-models
    resource: https://pydantic.dev/docs/ai/models/overview/
    title: PydanticAI docs — Models overview (provider strings, FallbackModel)
  - id: pai-google
    resource: https://pydantic.dev/docs/ai/models/google/
    title: PydanticAI docs — Google model (install extra, gemini endpoints)
  - id: pypi-pydantic-ai
    resource: https://pypi.org/project/pydantic-ai/
    title: pydantic-ai / pydantic-ai-slim on PyPI (2.37.0, 2026-09-01)
  - id: litellm-input
    resource: https://docs.litellm.ai/docs/completion/input
    title: LiteLLM docs — completion() inputs
  - id: litellm-routing
    resource: https://docs.litellm.ai/docs/routing
    title: LiteLLM docs — Router (fallbacks, retries)
  - id: litellm-bench
    resource: https://docs.litellm.ai/docs/benchmarks
    title: LiteLLM docs — Benchmarks (proxy overhead)
  - id: pypi-litellm
    resource: https://pypi.org/project/litellm/
    title: litellm on PyPI (1.99.0, 2026-09-01)
---

# Why this document exists

The `LLM` port needs its first adapter in `src/llm/`. The port's contract
is fixed by [Decision 0005](/docs/decisions/0005-retrieval-architecture.md):
it speaks the domain's `Message`/`ToolSpec`/`ToolCall` vocabulary, never
provider types, and the tool loop (iteration-capped) lives in
`AgentService` — so swapping the library never touches the
domain.[^decision-0005] The adapter is swapped in one line at the
composition root.[^arch] This concept records the evidence gathered
2026-09-01 on five candidate libraries so the upcoming decision record can
cite it. It presents fit, not a final choice.

The decisive axis follows from the constraint: a candidate must work as a
**thin stateless translation layer** — one API call per loop iteration,
tool-call requests returned to the caller unexecuted. A library that
insists on owning the agent loop is fighting Decision 0005, whatever its
other merits.

# Method

- Dependency weight was measured locally on 2026-09-01: `pip install
--dry-run --report` against this repo's venv (so counts are marginal to
  what `requirements.txt` already installs, `openai==3.6.0` included),
  with artifact sizes taken from HTTP `Content-Length` of the exact wheels
  pip resolved. Disk and import figures come from isolated venvs per
  candidate (Python 3.14, this machine; an empty venv is 13 MB of pip;
  cold import is best-of-3 `python -c "import X"` subprocess runs).
- Everything else cites primary sources: official docs, PyPI metadata,
  GitHub, vendor announcements.

# Dependency weight (measured 2026-09-01)

| Candidate (install spec)          | New pkgs over this repo | Compressed download | Isolated venv | Cold import        | Keeps `openai==3.6.0`?                                  |
| --------------------------------- | ----------------------- | ------------------- | ------------- | ------------------ | ------------------------------------------------------- |
| `openai` (already installed)      | +0                      | 0 MB                | 49 MB         | 0.58 s             | —                                                       |
| `pydantic-ai-slim[openai]` 2.37.0 | +10                     | 4.2 MB              | 77 MB         | 0.38 s (`.direct`) | yes — extra requires `openai>=3.0.0`                    |
| `langchain-openai` 1.6.0          | +17                     | 9.7 MB              | 107 MB        | 0.92 s             | yes — `openai<4.0.0,>=2.45.0`                           |
| `deepagents` 0.7.11               | +36                     | 16.8 MB             | not measured  | not measured       | yes, but OpenAI use needs `langchain-openai` on top     |
| `strands-agents[openai]` 1.54.0   | +32                     | 24.3 MB             | 124 MB        | 0.32 s             | **no — downgrades to 2.54.0** (`openai<3.0.0,>=1.68.0`) |
| `litellm` 1.99.0                  | +37                     | 53.7 MB             | 258 MB        | 1.86 s             | **no — core pin `openai>=2.20.0,<3.0.0`** (see below)   |

Notable line items behind the counts: `deepagents` hard-depends on
`langchain-anthropic` and `langchain-google-genai` (two provider SDKs you
did not ask for) plus the langchain/langgraph/langsmith stack;
`strands-agents` hard-depends on `boto3`/`botocore` (15.4 MB), the
OpenTelemetry SDK, `mcp`, and `watchdog` even when no AWS or telemetry is
used — and its `[openai]` extra additionally pulls
`aws-bedrock-token-generator`; `litellm`'s own wheel is 23 MB and its core
deps include `boto3`, `tokenizers`, and `huggingface_hub`. Forcing
`openai==3.6.0` alongside litellm makes pip backtrack to litellm 1.83.0,
a release from 2026-03-31 — five months stale on a package that ships
~113 releases per quarter.

# Candidate 1 — OpenAI Python SDK direct

Already pinned in `requirements.txt` (3.6.0, released 2026-08-28; Apache-2.0;
417 releases since 2020).[^pypi-openai] Tools are declared as JSON-schema
function definitions; the model returns tool-call items carrying a
`call_id`, `name`, and JSON-encoded `arguments`; results go back as
`function_call_output` entries — and the official guide's own examples
show a **developer-owned loop** ("Tool calling is a multi-step
conversation between your application and a model"), i.e. exactly the
shape Decision 0005 mandates.[^openai-fc] Chat Completions remains
"supported indefinitely" alongside the newer Responses API; streaming is
native.[^pypi-openai]

Our adapter: map `Message`/`ToolSpec` → one `chat.completions.create(...)`
per loop iteration → map `tool_calls` back to domain `ToolCall`. Zero new
dependencies; no framework to fight.

Multi-provider: the same client targets any OpenAI-compatible endpoint by
changing `base_url` — Google documents running the official OpenAI library
against Gemini "by updating three lines of code", tool calling
included.[^gemini-compat] That covers the two keys Decision 0005 already
plans for (OpenAI, Gemini).[^decision-0005] It does **not** cover
non-compatible native APIs (e.g. Anthropic's), and provider fallback would
be hand-written (a small decorator adapter in `src/llm/`).

# Candidate 2 — LangChain deepagents (and plain `init_chat_model`)

`deepagents` is "an open source agent harness — an opinionated agent that
runs out of the box", built on the LangGraph runtime, shipping a
filesystem abstraction, sub-agent delegation, context management, and
defaults explicitly "tuned for long-horizon, multi-step
work".[^deepagents-gh] `create_deep_agent(...)` returns a compiled
LangGraph agent you `invoke()` — the harness and graph runtime own the
loop end to end.[^deepagents-gh] It is popular (28.8k GitHub stars) but
pre-1.0 (0.7.11, first release 2025-07, 123 releases).[^pypi-deepagents]
Using it here would mean handing our bounded tool loop to the harness —
the exact inversion Decision 0005 rejects — to buy planning/filesystem/
sub-agent machinery this system does not need.

The distinction that matters: plain LangChain's model layer is **not**
loop-owning. `init_chat_model("provider:model")` returns a chat model;
`bind_tools()` declares tools; a single `.invoke()` returns an `AIMessage`
whose `tool_calls` the caller handles — the docs state "When using a model
separately from an agent, it is up to you to execute the requested tool
and return the result back to the model."[^langchain-models] So the
LangChain-family candidate compatible with our port is
`langchain-openai`/`init_chat_model` (+17 packages), not deepagents. Each
provider still needs its own integration package
(`langchain-openai`, `langchain-anthropic`, ...).[^langchain-models]

# Candidate 3 — Strands Agents (AWS)

AWS-maintained harness (repo: strands-agents/harness-sdk, "Build an agent
harness and control it end-to-end"; 7.1k stars, Apache-2.0).[^strands-gh]
GA since 1.0 in 2025 after a May 2025 preview; 1.54.0 shipped
2026-08-27 with steady cadence.[^strands-ga][^pypi-strands] The Agent
class runs the loop itself: "invoke the model, check if it wants to use a
tool, execute the tool if so, then invoke the model again with the result"
— repeating "until the model produces a final response", with tools
executed automatically inside the SDK.[^strands-loop] Loop limits exist
(turn caps, token budgets checked "at the top of each loop iteration"),
but they configure _its_ loop, not ours.[^strands-loop] The docs describe
no supported single-call path that returns tool-call requests unexecuted —
using Strands under our port means either surrendering the loop or calling
undocumented model internals.[^strands-loop] Add the mandatory
boto3/OTel/mcp/watchdog baggage and the `openai<3.0.0` extra pin that
downgrades our SDK (measured above), and it is a well-built framework at
the wrong layer for this port. It supports 13+ model providers — but only
inside its own Agent abstraction.[^pypi-strands]

# Candidate 4 — PydanticAI (slim, direct API)

PydanticAI's headline Agent owns a loop like the others — but it also
ships `pydantic_ai.direct`, a documented low-level API where "the only
abstraction is input and output schema translation": `model_request()`
takes messages plus `ModelRequestParameters(function_tools=
[ToolDefinition(name, description, JSON schema)])` and returns a
`ModelResponse` whose `ToolCallPart`s the **caller** handles — tools are
never executed by the library; the docs recommend it precisely for
"building your own abstractions".[^pai-direct] Sync, async, and streaming
variants exist (`model_request_sync`, `model_request_stream`).[^pai-direct]

Multi-provider is a string: `"openai:..."`, `"anthropic:..."`, etc., with
OpenAI-compatible endpoints handled by `OpenAIChatModel` plus a custom
provider; a built-in `FallbackModel` "attempt[s] multiple models in
sequence until one succeeds" on 4xx/5xx.[^pai-models] `model_request`
accepts `Model | KnownModelName | str`, so a `FallbackModel` instance
drops into the same call — the challenge's optional fallback enhancement
stays a one-line composition-root change.[^pai-direct-api] Extras are
per-provider: the native `GoogleModel` requires the `google` optional
group (`pydantic-ai-slim[google]`; extras combine, so
`[openai,google]`),[^pai-google] and Gemini is absent from the documented
OpenAI-compatible provider list[^pai-models] — so a Gemini fallback under
`[openai]` alone means pointing `OpenAIChatModel` at Google's own
OpenAI-compatibility endpoint,[^gemini-compat] while the documented native
route costs one more extra.

Weight is the smallest real addition measured: `pydantic-ai-slim[openai]`
adds 10 packages / 4.2 MB, requires `openai>=3.0.0` (aligned with our
pin), and imports faster than `openai` itself. Mature and fast-moving: MIT,
2.37.0 on 2026-09-01, 57 releases since June, 19.6k
stars.[^pypi-pydantic-ai] Caveat: the full `pydantic-ai` metapackage is
the heavy path (+72 packages, logfire/mcp/anthropic/google bundled) — the
slim spelling is the one this evidence supports.

# Candidate 5 — LiteLLM

`litellm.completion()` is the right _shape_: a stateless function that
"accepts and translates the OpenAI Chat Completion params across all
providers" (100+), `tools`/`tool_choice` included, returning OpenAI-format
responses; the provider is a model-string prefix.[^litellm-input] The
`Router` (SDK, not proxy) adds retries, cooldowns, and ordered fallbacks
across deployments.[^litellm-routing] It is huge and hyperactive: 57.8k
stars, 1,021 releases, 113 since June.[^pypi-litellm]

Against this repo it loses on cost, not shape: current litellm pins
`openai>=2.20.0,<3.0.0` in core[^pypi-litellm] — a hard conflict with our
pinned 3.6.0 (pip either downgrades the SDK to 2.54.0 or backtracks to
March's litellm 1.83.0) — and it is the heaviest candidate measured
(+37 packages, 53.7 MB compressed, 258 MB venv, 1.86 s cold import).
Since our adapter already speaks the OpenAI wire format through the
official SDK, litellm's marginal code saving here is roughly an import
line.

# Latency-overhead evidence

- **LiteLLM** publishes overhead numbers only for its **proxy server**
  (median 12 ms at 2 instances, 2 ms at 4 instances, measured against a
  fake backend); the docs contain no SDK (`litellm.completion`) per-call
  overhead figures.[^litellm-bench]
- **No candidate publishes per-call SDK overhead benchmarks vs the raw
  provider SDK** — for PydanticAI direct, LangChain models, Strands, or
  deepagents, no primary-source per-request numbers exist; we decline to
  guess. Structurally, every candidate terminates in the same provider
  HTTP request, so thin-layer overhead is schema translation in-process.
- What we could measure honestly is startup, not per-call, cost: cold
  import of `litellm` is 1.86 s vs 0.38–0.92 s for the thin layers and
  0.58 s for `openai` alone (method above).

# Maturity snapshot (PyPI/GitHub, 2026-09-01)

| Library        | Latest (date)       | First release | Releases since 2026-06 | Stars | License                                        |
| -------------- | ------------------- | ------------- | ---------------------- | ----- | ---------------------------------------------- |
| openai         | 3.6.0 (2026-08-28)  | 2020-02       | 26                     | 31.5k | Apache-2.0                                     |
| deepagents     | 0.7.11 (2026-08-28) | 2025-07       | 27                     | 28.8k | MIT (pre-1.0)                                  |
| strands-agents | 1.54.0 (2026-08-27) | 2025-05       | 14                     | 7.1k  | Apache-2.0 (AWS)                               |
| pydantic-ai    | 2.37.0 (2026-09-01) | 2024-05       | 57                     | 19.6k | MIT                                            |
| litellm        | 1.99.0 (2026-09-01) | 2023-07       | 113                    | 57.8k | MIT on PyPI; GitHub repo license `NOASSERTION` |

# Fit verdicts (against this repo's constraints)

- **OpenAI SDK direct — strong fit, zero marginal cost.** Already
  installed; the vendor's own guide models the developer-owned loop
  Decision 0005 mandates; the adapter is pure translation. Multi-provider
  reach is real but bounded to OpenAI-compatible endpoints (Gemini
  documented; Anthropic-native out of reach), and fallback is hand-rolled.
- **deepagents — misfit for this port.** A loop-owning harness for
  long-horizon agents; adopting it surrenders the domain-owned loop and
  imports two unrelated provider SDKs. If the LangChain family is wanted,
  the right unit is `init_chat_model`/`langchain-openai` — a documented
  caller-owned-loop path at middleweight cost (+17 pkgs), with per-provider
  integration packages.
- **Strands Agents — wrong layer, despite real quality.** GA, AWS-backed,
  cleanly documented — but the loop is internal with no documented
  single-call escape hatch, the core drags boto3/OTel/mcp/watchdog
  everywhere, and its `[openai]` extra downgrades our pinned SDK. Worth
  the owner's curiosity as a standalone harness experiment, not as an
  `LLM`-port adapter.
- **PydanticAI (`pydantic-ai-slim[openai]`, direct API) — strong fit as a
  thin multi-provider layer.** The only framework here that _documents_ a
  caller-owned, single-call, tools-in/tool-calls-out API; +10 packages;
  `openai>=3.0.0` aligned with our pin; `FallbackModel` makes the optional
  fallback enhancement a composition-root swap.
- **LiteLLM — right shape, wrong weight.** Stateless OpenAI-format
  translation plus Router fallbacks fit the port, but the `openai<3` core
  pin conflicts with this repo today, and it is by far the heaviest option
  measured for a benefit our OpenAI-format adapter mostly already has.

The live contest for the decision record is therefore **openai-direct**
(zero new deps; multi-provider via `base_url` only) versus
**pydantic-ai-slim's direct API** (small, aligned dependency; true
multi-provider strings plus built-in fallback). Both keep the loop in
`AgentService` and the swap at the composition root.[^arch]

[^arch]: System Architecture — adapters in stage packages, one-line swaps at the composition root.

[^decision-0005]: Decision 0005 — `LLM` port vocabulary, domain-owned iteration-capped tool loop, OpenAI/Gemini keys.

[^pypi-openai]: openai on PyPI — 3.6.0 metadata, release history, Responses-primary / Chat Completions "supported indefinitely".

[^openai-fc]: OpenAI — Function calling guide (developer-owned loop, `call_id`/`arguments`, `function_call_output`).

[^gemini-compat]: Google — OpenAI compatibility for the Gemini API (`base_url`, tool calling supported).

[^deepagents-gh]: langchain-ai/deepagents — README (harness on LangGraph, built-in tools, long-horizon defaults); repo stats via GitHub API 2026-09-01.

[^pypi-deepagents]: deepagents on PyPI — 0.7.11 metadata and requires_dist.

[^langchain-models]: LangChain 1.x docs — Models: `init_chat_model` strings, `bind_tools`, caller executes requested tools.

[^strands-loop]: Strands Agents docs — Agent Loop (automatic tool execution, recursion, limits).

[^strands-gh]: strands-agents/harness-sdk — repo description and stats via GitHub API 2026-09-01.

[^strands-ga]: AWS Open Source Blog — Strands Agents 1.0 GA announcement.

[^pypi-strands]: strands-agents on PyPI — 1.54.0 metadata, requires_dist (boto3/OTel core; `openai<3.0.0` extra), provider extras.

[^pai-direct]: PydanticAI docs — Direct model requests ("the only abstraction is input and output schema translation").

[^pai-direct-api]: PydanticAI API reference — `model_request(model: Model | KnownModelName | str, ...)`.

[^pai-models]: PydanticAI docs — Models overview (provider:model strings, OpenAI-compatible endpoints, `FallbackModel`).

[^pypi-pydantic-ai]: pydantic-ai / pydantic-ai-slim on PyPI — 2.37.0 metadata, `openai>=3.0.0` extra pin, release cadence.

[^litellm-input]: LiteLLM docs — completion() inputs (OpenAI-param translation across providers, tools support).

[^litellm-routing]: LiteLLM docs — Router: fallback ordering, retries, cooldowns (Python SDK).

[^litellm-bench]: LiteLLM docs — Benchmarks (proxy-only overhead figures; no SDK numbers).

[^pypi-litellm]: litellm on PyPI — 1.99.0 metadata, `openai>=2.20.0,<3.0.0` core pin, release history.
