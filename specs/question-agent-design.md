---
type: Spec
title: Question Agent — Design & Implementation Plan
description: Approved design for POST /question — the domain LLM vocabulary and LLM port, the AgentService dual-path flow (seed retrieval + bounded query_knowledge tool loop) with the [i]-citation / NO_ANSWER protocol, the PydanticAI direct adapter, the thin route, composition/config — plus the ordered TDD implementation plan (no separate plan document), the implementation notes from the first landing (2026-09-01) and the Decision 0009 revision (2026-09-02) — structured AgentReply output, function-derived tools, chunk ids as citation handles, XML-rendered context in a system message.
tags: [agent, question, llm, tool-loop, citations, pydantic-ai, design, spec]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T21:53:05Z }
verified: { by: human:vinicius, at: 2026-09-01T18:58:00Z }
sources:
  - id: challenge
    resource: /docs/challenge.md
    title: Challenge Brief — ML Engineering (LLM)
  - id: decision-0005
    resource: /docs/decisions/0005-retrieval-architecture.md
    title: "0005 — Retrieval architecture: strategy port, dual-path agent, Qdrant"
  - id: decision-0009
    resource: /docs/decisions/0009-structured-reply-function-tools.md
    title: "0009 — Structured agent reply, function-derived tools, chunk ids as citation handles"
  - id: arch
    resource: /docs/architecture.md
    title: System Architecture — Ports & Adapters Lite
  - id: llm-evidence
    resource: /research/llm-adapter-library-evidence.md
    title: LLM Adapter Library Evidence
  - id: eval-harness-spec
    resource: /specs/eval-harness-design.md
    title: Eval Harness — Design & Implementation Plan
  - id: eval-spec
    resource: /specs/eval-structure-design.md
    title: Eval Structure & Golden Dataset — Design
  - id: baseline
    resource: /evals/results/20260901-190240-baseline.json
    title: Retrieval baseline run (2026-09-01, commit f518762, dirty tree)
---

# Goal

> **Revised by [Decision 0009](/docs/decisions/0009-structured-reply-function-tools.md)**
> (2026-09-02) after the owner's review of the first implementation. The
> current design is the **Revision** section at the end; the sections
> "Domain vocabulary", "AgentService" (steps 2–4 and the tool), "System
> prompt requirements", "LLM adapter" and Implementation notes 1–5 describe
> the superseded first version and are kept as history.

Give the system its answer path: `POST /question` takes a question and
returns an answer grounded in the indexed PDF chunks, with the source
excerpts that ground it, per the challenge contract.[^challenge] The macro
shape is fixed by [Decision 0005](/docs/decisions/0005-retrieval-architecture.md)
— deterministic seed retrieval plus a bounded `query_knowledge` tool loop
over the same `Retriever`, the loop living in the domain[^decision-0005] —
this spec fills in everything below that: vocabulary, protocol, adapter,
route, config, tests. Serves all six [Golden Rules](/docs/golden-rules.md);
_LLM Use_ and _Functionality_ most directly.

# Scope

**In:** domain LLM vocabulary and `LLM` port, `AgentService`, the
citation/refusal protocol, the PydanticAI direct adapter, the route, the
composition-root additions and config knobs, the TDD test plan, the first
eval plan (tool on/off), and the ordered implementation plan — this spec
doubles as the plan.

**Out:** answer-layer eval metrics (the harness side — deferred to the
eval session's answer layer[^eval-harness-spec]), the `FallbackModel`
multi-provider enhancement (a recorded cheap follow-up, not v1), token/cost
accounting on `Answer` (deferred with it), streaming, and any retrieval
strategy beyond the existing `VectorRetriever`.

# Contract consumed (owned by the eval-harness spec)

Implemented, tested, and frozen by the parallel eval-harness
session:[^eval-harness-spec]

- `RetrievedChunk(chunk: Chunk, score: float, retrieval_source: str = "seed")`
  in `src/domain/models.py`; retrievers always return the default
  `"seed"` — they cannot know which path called them.
- `Retriever.retrieve(query: str, k: int) -> list[RetrievedChunk]` in
  `src/domain/ports.py` — the only retrieval seam `AgentService` sees
  (architecture rule 9[^arch]).
- `VectorRetriever(embedder, store)` in `src/retrieval/vector_retriever.py`.
- Composition form in `src/api/composition.py`: `embedding_model_name()`,
  cached `get_qdrant_client()` / `get_embedder()`, parameterizable
  `build_vector_store(collection)`, cached services composed on top.

This spec adds to those files without redefining any of that.

# Domain vocabulary (additions to `src/domain/models.py` and `ports.py`)

Frozen dataclasses, stdlib only, like the existing entities:

- `ToolSpec(name: str, description: str, parameters: dict)` — `parameters`
  is a JSON Schema.
- `ToolCall(id: str, name: str, arguments: dict)`.
- `Message(role: str, content: str, tool_calls: tuple[ToolCall, ...] = (),
tool_call_id: str | None = None)` — roles `"system" | "user" |
"assistant" | "tool"`; `tool_call_id` links a `"tool"` message to the
  call it answers.
- `Answer(text: str, references: list[RetrievedChunk])` — references stay
  **structured** in the domain: each carries the full `Chunk`
  (`document_id`, `filename`, `page`, `section`, text) plus `score` and
  `retrieval_source`. The eval harness consumes `(question) -> Answer`
  in-process and reads `(chunk.filename, chunk.page)` for citation
  scoring;[^eval-harness-spec] the route flattens to strings.

Port:

- `LLM.complete(messages: list[Message], tools: list[ToolSpec]) -> Message`
  — stateless, **one provider call per invocation**; returned assistant
  message may carry `tool_calls`, never executed by the adapter. The loop
  is the domain's.

# AgentService (`src/domain/services/agent_service.py`)

`AgentService(retriever: Retriever, llm: LLM, k: int, max_tool_rounds:
int, tool_enabled: bool)` — stateless orchestrator, `Service`-suffixed per
architecture rule 6.[^arch]

`answer(question: str) -> Answer`:

1. **Seed** — `retriever.retrieve(question, k)`; results enter a
   **numbered registry** `[1..n]`, deduplicated by chunk id (a chunk
   re-retrieved later keeps its original number, so citations stay
   stable). Seed results keep `retrieval_source="seed"`.
2. **Messages** — system prompt (below) + one user message holding the
   numbered context blocks, each headed `[i] {filename}, p. {page}`, then
   the question. An empty index yields an explicit `(no indexed content)`
   block — not an error; the protocol leads the model to refuse.
3. **Tool loop** — up to `max_tool_rounds` iterations:
   `llm.complete(messages, tools)` where `tools` is
   `[query_knowledge]` when `tool_enabled`, else `[]`. If the response
   carries `tool_calls`: for each, run
   `retriever.retrieve(arguments["query"], k)`, re-tag results
   `retrieval_source="tool"` via `dataclasses.replace`, extend the
   registry (continuing the numbering), and append a `"tool"` message
   with the new numbered blocks; iterate. A text-only response exits the
   loop. If the cap is hit while the model still wants tools, one final
   `complete(messages, [])` forces a text answer.
4. **Post-process** —
   - Refusal: response text starting with the sentinel `NO_ANSWER` →
     `Answer(text=<sentinel stripped>, references=[])`.
   - Otherwise parse `[i]` markers: `references` = registry entries in
     first-citation order, deduplicated; markers stripped from `text`.
   - Answered with **zero** parsed citations (the prompt makes this rare)
     → fallback `references` = the seed results, in score order.
5. Provider exceptions bubble to the API edge; the service catches
   nothing it cannot act on.

## The `query_knowledge` tool

`ToolSpec(name="query_knowledge", description=<search the indexed
manuals; reformulate freely; returns numbered excerpts>, parameters=
{"query": string, required})`. Same `k` as the seed. The 0005 toggle
exists so evals can ask whether the agentic path earns its
latency;[^decision-0005] with retrieval at ~340 ms median per call (mean
548 / p95 2518 ms, the tail being five cold OpenAI connections — network
risk, not per-round cost),[^baseline] each round costs a retrieval plus
an LLM call — the cap of 3 has measured justification.

## System prompt requirements

Prompts are deliberate artifacts (Golden Rule _LLM Use_): named constants
in `src/domain/services/prompts.py` (stdlib-pure, domain-safe), iterated
under evals. The v1 prompt must state:

1. Answer **only** from the numbered context (seed + tool results).
2. Cite every load-bearing excerpt inline as `[i]`; cite only what
   actually grounds the answer.
3. If the context does not contain the answer, reply starting with
   `NO_ANSWER` followed by a one-sentence refusal in the question's
   language, citing nothing.
4. Answer in the question's language.
5. Ignore irrelevant or garbled context — measured necessity, not
   boilerplate: baseline precision@5 is 0.24 (76% of seed context is
   noise) and CESTARI chunks can be `�`-runs;[^baseline] garbled context
   is a refusal case, never material to paraphrase.

# LLM adapter (`src/llm/pydantic_ai_llm.py`)

`PydanticAiLLM(model: Model | str)` implements the port with **one**
`pydantic_ai.direct.model_request_sync` call per `complete()` — the
documented thin path whose "only abstraction is input and output schema
translation"; `ToolCallPart`s come back unexecuted by
construction.[^llm-evidence] Translation: domain `Message` list →
`ModelRequest`/`ModelResponse` parts; `ToolSpec` →
`ToolDefinition(name, description, parameters_json_schema)` inside
`ModelRequestParameters`; response parts → domain `Message` with
`tool_calls`. Library choice and rejected alternatives are recorded in
[Decision 0008](/docs/decisions/0008-question-agent-baseline.md), grounded
in the measured evidence.[^llm-evidence] Accepting `Model | str` keeps the
future `FallbackModel` (with the `google` extra for native Gemini) a
composition-root-only change.[^llm-evidence]

`requirements.txt` gains `pydantic-ai-slim[openai]` pinned (2.37.0 at
research time). `src/api/main.py` gains an exception handler mapping the
adapter's provider errors to 502, alongside the existing `openai` handler.

# Route (`src/api/routes/question.py`)

- `QuestionRequest(question: str)` with `min_length=1` (blank → 422, free
  via Pydantic).
- `QuestionResponse(answer: str, references: list[str])` — the challenge
  contract, byte-compatible.[^challenge] Each reference is the **verbatim
  text of one cited chunk**; structure (doc, page) stays in the domain for
  the harness.
- The route is a **sync `def`** — FastAPI runs it on the threadpool, so
  the seconds-long LLM exchange never blocks the event loop.
- Thin per architecture rule 5: validate → `service.answer(question)` →
  map. No other logic.

# Composition & config (`src/api/composition.py`)

Cached `get_agent_service()` composed from the landed form:
`VectorRetriever(get_embedder(), build_vector_store(QDRANT_COLLECTION))` +
`PydanticAiLLM(LLM_MODEL)`. New env knobs, all with defaults:

| Env var                   | Default             | Meaning                                                                               |
| ------------------------- | ------------------- | ------------------------------------------------------------------------------------- |
| `LLM_MODEL`               | `openai:gpt-5-mini` | PydanticAI model string                                                               |
| `RETRIEVAL_K`             | `5`                 | k for seed and tool retrieval — single source, matching the eval gates' k[^eval-spec] |
| `AGENT_MAX_TOOL_ROUNDS`   | `3`                 | tool-loop iteration cap                                                               |
| `QUERY_KNOWLEDGE_ENABLED` | `true`              | the 0005 toggle[^decision-0005]                                                       |

# Test plan (TDD, per the Development Workflow)

- **`AgentService`** against scripted `FakeRetriever`/`FakeLLM`
  (`tests/domain/`): seed-only answer with citations; one tool round with
  `"tool"` re-tagging and continued numbering; registry dedup (re-retrieved
  chunk keeps its number); cap exhaustion forces a final no-tools call;
  `NO_ANSWER` → empty references and stripped sentinel; answer without
  citations → seed fallback; citation order/dedup and marker stripping;
  `tool_enabled=False` passes `tools=[]`; garbled/irrelevant-context case
  refuses (the CESTARI `�` scenario[^baseline]).
- **Adapter** (`tests/llm/`): vocabulary translation exercised against
  PydanticAI's built-in test models (`TestModel`/`FunctionModel` — no
  network), both directions, tool_calls included.
- **Route** (`tests/api/`): `dependency_overrides` with a fake service —
  exact challenge JSON contract, empty question → 422.
- **Seam integration**: `AgentService` + real `VectorRetriever` over
  `QdrantClient(":memory:")` with fake embedder + fake LLM.

- **Typecheck gate** (Development Workflow): `make typecheck` — pyright in
  `standard` mode — reports zero errors before any step counts as done.
  Standard mode checks fakes against the Protocols in full: `FakeRetriever`
  implements `retrieve` and `FakeLLM` implements `complete` with the ports'
  exact signatures; SDK-typed values inside test fakes may use `cast()`.

LLM/embedding **accuracy** belongs to evals, not unit tests (architecture
rule 7[^arch]).

# Eval plan

With the endpoint standing, run the harness's answer flow in-process
(`(question) -> Answer`) in **both configs** — `QUERY_KNOWLEDGE_ENABLED`
on and off — the 0005 "does the agentic path earn its latency?"
question,[^decision-0005] raised in priority by the measured retrieval
latency.[^baseline] Both runs go through the official DX — `make eval
label=agent-tool-on` and `make eval label=agent-tool-off`, the toggle
flipped through `QUERY_KNOWLEDGE_ENABLED` in `.env` (which `make eval`
sources) and any answer-layer flag the harness adds passed via
`args='...'`; no loose `python -m` invocations. Retrieval reference
numbers this design builds on
(2026-09-01 baseline, 83 gated cases, k=5): recall@5 0.65 · hit_rate@5
0.66 · MRR@5 0.60; WEG guia 0.94 recall vs CESTARI 0.30 (the expected
canary); precision@5 0.24.[^baseline]

# Implementation plan (TDD, in order)

This spec is the implementation plan — no separate plan document. Each
step starts with its failing test; no production code without one.

1. **Vocabulary + port** — `ToolSpec`/`ToolCall`/`Message`/`Answer`
   appended to `models.py`, `LLM` Protocol appended to `ports.py`
   (`Retriever`/`RetrievedChunk` untouched). Light tests: frozen-dataclass
   invariants and defaults (empty `tool_calls` tuple, `tool_call_id`
   None); everything after pulls these into use.
2. **`AgentService` — seed path** (scripted `FakeRetriever`/`FakeLLM`):
   seed retrieval called with `k`; numbered registry; message assembly —
   system prompt from `prompts.py` constants, `[i] {filename}, p. {page}`
   block headers, question last, empty index → `(no indexed content)`
   block; cited answer → references in first-citation order, markers
   stripped from `text`.
3. **`AgentService` — protocol edges**: `NO_ANSWER` → empty references,
   sentinel stripped; answer with zero citations → seed fallback in score
   order; citation dedup; the garbled-context case (CESTARI-style
   `�`-run fixture[^baseline]) refuses instead of paraphrasing noise.
4. **`AgentService` — tool loop**: scripted `tool_calls` → the **same**
   retriever queried with the tool's `query`, results re-tagged `"tool"`
   via `dataclasses.replace`, numbering continues, re-retrieved chunk
   keeps its original number, `"tool"` message appended with
   `tool_call_id`; cap exhaustion forces one final `complete(messages,
[])`; `tool_enabled=False` passes `tools=[]` on every round.
5. **`PydanticAiLLM`** — translation both directions against PydanticAI's
   `TestModel`/`FunctionModel` (no network): `Message` list →
   request parts, `ToolSpec` → `ToolDefinition`, `ToolCallPart` → domain
   `ToolCall`, text parts → assistant `Message`. `requirements.txt` gains
   the pinned `pydantic-ai-slim[openai]`.
6. **Route** — `routes/question.py` with a fake service via
   `dependency_overrides`: exact challenge JSON,[^challenge] references =
   verbatim cited-chunk texts, blank question → 422; provider-error
   handler in `main.py` → 502 alongside the existing `openai` one.
7. **Composition + config** — cached `get_agent_service()` over the
   landed provider form; the four env knobs with defaults; `RETRIEVAL_K`
   read here as the single source. Notify the eval-harness session when
   this lands (standing rebase agreement, 2026-09-01).
8. **Seam integration** — `AgentService` + real `VectorRetriever` on
   `QdrantClient(":memory:")` with fake embedder + fake LLM: question in,
   grounded `Answer` out, references carrying `(filename, page)`.
9. **Live smoke + evals** — `make test` and `make typecheck` green;
   docker-compose path (`make up`): upload `case_files/`, ask the
   challenge's example question end-to-end; then the tool-on/off
   `make eval` runs per the eval plan above (answer-layer metrics land
   with the harness session's answer layer).
10. **Documentation ritual** — update this spec's status per owner
    review; log the implementation entry in `log.md`; propose (approval
    gate) any module concept the implementation earns — knowledge the
    code cannot say, e.g. observed tool-loop behavior; prompt rationale
    already lives here and in [Decision
    0008](/docs/decisions/0008-question-agent-baseline.md).

# Implementation notes (landed 2026-09-01, steps 1–9)

Steps 1–8 landed TDD-first (35 new tests, 103 green; pyright `standard`
zero errors). Where the code had to decide beyond this text, the choice is
recorded here rather than in the code:

1. **Tool offering follows one rule.** Tools are offered on a call iff
   `tool_enabled and rounds_so_far < max_tool_rounds`. This is the spec's
   "final `complete(messages, [])`" generalized: with
   `AGENT_MAX_TOOL_ROUNDS=0` the tool is never offered at all (the
   original draft offered it on the first call and then ignored the
   resulting tool call — incoherent). Cap 3 therefore means at most 4 LLM
   calls and 3 tool executions per question.
2. **Citation markers** accept `[i]` and grouped `[i, j]`; numbers absent
   from the registry are ignored; markers are stripped with their leading
   whitespace. The refusal sentinel is stripped together with trailing
   `:;,.-—–` and whitespace.
3. **Tool results are rendered like context blocks.** A tool message lists
   every result of that query with its registry number — a re-retrieved
   chunk shows under its original number, so the model sees the hit
   without the registry growing. An empty retrieval renders the same
   `(no indexed content)` block as an empty index.
4. **Prompt wording is generic.** The challenge indexes arbitrary PDFs, so
   the system prompt and the tool description say "uploaded documents" /
   "indexed documents", not "manuals". The prompt text lives in
   `src/domain/services/prompts.py` as `SYSTEM_PROMPT`; the tool as
   `QUERY_KNOWLEDGE_TOOL`.
5. **Adapter translation.** Consecutive request-side domain messages
   (`system`/`user`/`tool`) are grouped into one `ModelRequest`; each
   `assistant` message becomes a `ModelResponse` (`TextPart` if content,
   then `ToolCallPart`s). PydanticAI's `ToolReturnPart` requires a
   `tool_name` the domain `Message` does not carry, so the adapter
   resolves it from the preceding assistant `ToolCall` with the same id; a
   `tool` message answering no known call is rejected with `ValueError`
   before any provider call. Tool-call `args` arrive as dict or JSON
   string; both decode via `args_as_dict()`.
6. **Provider errors.** PydanticAI's OpenAI model wraps the SDK's
   `APIStatusError`/`APIConnectionError` into
   `pydantic_ai.exceptions.ModelHTTPError`/`ModelAPIError`, so the
   question path's 502 handler catches `ModelAPIError` ("LLM provider
   error"). The pre-existing `openai.OpenAIError` handler now serves the
   query-embedding step of both routes and its message was generalized to
   "OpenAI provider error".
7. **Composition shape.** `build_agent_service(retriever, llm)` reads the
   four knobs and is the builder the eval harness's answer layer will
   reuse over the eval collection (same pattern as
   `build_ingestion_service`); `get_agent_service()` is the cached
   production wiring. `docker-compose.yml` passes the four knobs through
   with their defaults so `.env` reaches the container, and `make up` now
   runs `docker compose up -d --build` (foreground, without `-d`, since
   [Decision 0010](/docs/decisions/0010-examiner-developer-ux.md)) — a dependency change must rebuild
   the image.
8. **Route validation** uses `StringConstraints(strip_whitespace=True,
   min_length=1)`, so whitespace-only questions are also 422.
9. **`openai:` is the Responses API.** In pydantic-ai 2.37.0 the default
   `LLM_MODEL=openai:gpt-5-mini` resolves to `OpenAIResponsesModel`;
   `openai-chat:<name>` selects Chat Completions. Resolution is lazy
   (first `complete()`), and a bad model string or missing key is a
   `UserError` → 500 on the first question, not 502. Details in the
   [LLM Module](/src/llm/llm.md) concept.

## Live smoke (step 9, 2026-09-01, `chunks` collection = 570 corpus chunks)

Through the compose path with `openai:gpt-5-mini`, defaults:

- "Qual graxa devo usar para relubrificar os rolamentos do motor?" →
  correct (Polyrex EM), 1 verbatim reference (LB5001), Portuguese. ~9 s.
- "What grease should I use to relubricate the motor bearings?" →
  correct, 2 references, English.
- "Qual é a capital da Austrália?" → clean refusal, empty references
  (sentinel stripped end to end). ~5 s.
- **"What is the power consumption of the motor?"** (the challenge's
  example) → refusal. Legitimate: the seed top-5 are conceptual WEG-guide
  passages on "potência absorvida" with no figure, and the question names
  no motor. **Defect observed (2/2 runs): the refusal sentence came in
  Portuguese** — the model followed the context's language, not the
  question's, violating prompt rules 3–4. Answered questions did respect
  the question's language. This is the first answer-layer finding; fixing
  it is prompt iteration and therefore eval-gated — it waits for the
  harness's answer layer and belongs in the golden dataset as a
  cross-lingual refusal case.

The tool-on/off runs in the eval plan became runnable on 2026-09-02 with
the answer layer (`make eval-answers`, [Answer Eval — Design &
Implementation Plan](/specs/answer-eval-design.md)); the first pair
(`agent-tool-on` / `agent-tool-off`) is read in the [Eval Experiment
Findings](/evals/results/experiment-findings.md).

# Revision — Decision 0013 (2026-09-02)

Citations stopped being chunk ids: [Decision
0013](/docs/decisions/0013-citations-as-quotes.md) makes `AgentReply.citations`
a list of passages quoted verbatim, resolved by normalized containment over
the chunks the model saw (`domain/services/quotes.py`), returned as
`Reference(chunk, quote, retrieval_source)` and rendered on the wire as the
quotes; `<chunk>` lost its `id` attribute and the seed fallback for
uncited answers is gone. The Decision 0009 revision below is otherwise the
design as implemented.

# Revision — Decision 0009 (2026-09-02)

The choices and the rejected alternatives are in [Decision
0009](/docs/decisions/0009-structured-reply-function-tools.md);[^decision-0009]
this section is the design as implemented (TDD, 112 tests green, pyright
zero errors).

## Vocabulary and port

- `ToolSpec` is gone. `Tool = Callable[..., str]` in `ports.py`: a tool is
  a typed Python function whose docstring is its description.
- `AgentReply(answer: str, citations: list[str], has_answer: bool)` — the
  model's structured reply; `citations` are chunk ids.
- `Completion(message: Message, reply: AgentReply | None)` — `reply` set
  when the model answered, `message.tool_calls` set when it asked for a
  tool.
- `LLM.complete(messages: list[Message], tools: list[Tool]) -> Completion`.
  Not generic: one output type exists.

## AgentService flow

1. **Seed** — `retriever.retrieve(question, k)`; every result is
   remembered in `seen: dict[str, RetrievedChunk]` keyed by chunk id
   (`setdefault`, so a re-retrieved chunk keeps its first entry and
   source).
2. **Messages** — `system` with `SYSTEM_PROMPT` (the rules; no tool
   mention — the tool describes itself); `system` with
   `render_context(seed, tool_available)` (the XML-rendered chunks, plus
   the "call `query_knowledge` again" follow-up only when the tool will
   actually be offered); `user` with the bare question.
3. **Tool** — `query_knowledge(query: str) -> str` is a closure created
   per question: retrieves with the same `k`, re-tags results
   `retrieval_source="tool"`, remembers them, returns
   `render_chunks(results)`.
4. **Loop** — while `completion.reply is None and rounds < cap`: append
   the assistant message, dispatch each tool call **by function name**
   (an unknown name gets an error text back as the tool result instead of
   crashing), `rounds += 1`, call again offering tools iff
   `rounds < cap`. The tool is offered on a call iff
   `tool_enabled and rounds < cap` — cap 0 never offers it.
5. **Post-process** — `has_answer=False` → `Answer(reply.answer, [])`.
   Otherwise references = the cited ids resolved through `seen`, in
   citation order, deduplicated, unknown ids dropped; no valid citation →
   the seed results in score order (0008's fallback, unchanged).
6. A `Completion` without a reply after the cap (the model kept asking
   for tools with none offered) is a contract violation → `RuntimeError`.

## Prompt shape (`prompts.py`)

Stdlib `string.Template` constants — `CONTEXT_PROMPT`, `TOOL_FOLLOWUP`,
`CHUNK_TEMPLATE`, `SECTION_TEMPLATE` — and two renderers.
`render_chunks(list[RetrievedChunk])` emits:

```xml
<chunks>
<chunk id="3f9a…" document="WEG-guia-50032749.pdf" page="34">
  <section>2. Características da Rede de Alimentação</section>
  <section>3.4.3 Partida com chave compensadora</section>
  <text>
…raw chunk text…
  </text>
</chunk>
</chunks>
```

Sections are the ` > `-separated breadcrumb levels as ordered siblings;
a chunk without a section has none; an empty list renders `<chunks/>`.
Attributes go through `quoteattr`; the text is raw (pymupdf4llm markdown
such as `<br>` stays readable). `kind` and `metadata` render nothing
until they carry data.

## Adapter

`PydanticAiLLM.complete` builds `ModelRequestParameters(function_tools=
[Tool(fn, strict=True).tool_def …], output_mode="native", output_object=
OutputObjectDefinition(name="AgentReply", json_schema=TypeAdapter(AgentReply)
.json_schema(), strict=True))`. A response with tool calls → `reply=None`;
otherwise `TypeAdapter(AgentReply).validate_json(text)` → `reply`. A
schema violation raises (`ValidationError` is a `ValueError`) and is
**not** mapped to 502. Details in the [LLM Module](/src/llm/llm.md).

## Tests (TDD)

`tests/domain/test_llm_vocabulary.py` (5), `test_prompts.py` (6 — exact
XML literals, quoting, raw text, empty list, conditional follow-up),
`test_agent_service.py` (13 — fakes return `Completion`s; message shape,
citation resolution, refusal, fallback, dedup, tool offering rules, tool
round with re-tagging, re-retrieval, cap exhaustion, unknown tool),
`tests/llm/test_pydantic_ai_llm.py` (9 — parts per message, function →
strict tool def with docstring descriptions, native strict output
object, validated reply, schema violation, tool calls, history replay,
orphan tool message), `tests/api/test_composition.py` (3),
`test_question_integration.py` (2 — real Qdrant `:memory:`, the XML
context carries the stored chunk's id, page and sections).

## Live smoke (2026-09-02, compose, `openai:gpt-5-mini`, 570 chunks)

- "What is the power consumption of the motor?" → refusal **in
  English**: "I can't determine the motor's power consumption from the
  provided document excerpts — no specific power or consumption value is
  given." The refusal-language defect of the first smoke is gone:
  `has_answer=false` carries the sentence in the question's language.
- "Qual graxa devo usar para relubrificar os rolamentos do motor?" →
  answers per equipment (Baldor: Polyrex EM; WEG-Cestari seals: NLGI #2
  EP), 3 references, Portuguese.
- "What grease should I use to relubricate the motor bearings?" →
  Polyrex EM, 2 references, English.
- "Qual é a capital da Austrália?" → refusal in Portuguese, empty
  references.
- "Qual o grau de proteção recomendado para usar o motor em um lavador
  de carros?" → IP55/IP55W and stricter options with the second-digit
  rationale, 3 references from the WEG guide.
- Latency 7–15 s per question (first smoke: 5–9 s). Structured output
  and possible tool rounds are candidates; there is no per-request
  observability yet to attribute it.

The tool-on/off `make eval` runs still wait for the harness's answer
layer; the first answer-eval baseline will be measured over this shape.

[^decision-0009]: 0009 — Structured agent reply, function-derived tools, chunk ids as citation handles: rationale and rejected alternatives for this revision.

[^challenge]: Challenge Brief — the `POST /question` request/response contract and the references semantics.

[^decision-0005]: Decision 0005 — dual-path answering, domain-owned iteration-capped tool loop, `LLM` port vocabulary, tool toggle.

[^arch]: System Architecture — rules 5–7 and 9; adapters in stage packages, one-line swaps at the composition root.

[^llm-evidence]: LLM Adapter Library Evidence — `pydantic_ai.direct` caller-owned single-call API, measured dependency weight, `FallbackModel`, Gemini extras.

[^eval-harness-spec]: Eval Harness — Design & Implementation Plan — read-side slice, in-process runner, coordinated `(question) -> Answer` consumption and `retrieval_source` semantics.

[^eval-spec]: Eval Structure & Golden Dataset — Design — k=5 gates; the harness takes `k` as a parameter.

[^baseline]: Retrieval baseline run 20260901-190240 (commit f518762, dirty tree) — gate numbers, precision@5 0.24, per-case retrieval latency median 342 ms (mean 548 / p95 2518 ms; five cold-connection outliers above 2 s), partial CESTARI corruption.
