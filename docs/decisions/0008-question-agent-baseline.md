---
type: Decision
title: 0008 — Question agent baseline: PydanticAI direct, LLM-cited references, in-process eval surface
description: The LLM port's first adapter uses pydantic-ai-slim's direct API (caller-owned single-call, FallbackModel path open); references are the chunks the LLM actually cites via an [i] protocol with a NO_ANSWER refusal sentinel and seed fallback; the eval harness consumes the domain in-process; config knobs with defaults (k=5, 3 tool rounds, tool toggle on).
tags: [agent, llm, pydantic-ai, citations, references, evals, config]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T02:18:30Z }
verified: { by: human:vinicius, at: 2026-09-01T17:22:00Z }
sources:
  - id: llm-evidence
    resource: /research/llm-adapter-library-evidence.md
    title: LLM Adapter Library Evidence
  - id: spec
    resource: /specs/question-agent-design.md
    title: Question Agent — Design
  - id: decision-0005
    resource: /docs/decisions/0005-retrieval-architecture.md
    title: "0005 — Retrieval architecture"
  - id: eval-harness-spec
    resource: /specs/eval-harness-design.md
    title: Eval Harness — Design & Implementation Plan
  - id: baseline
    resource: /evals/results/20260901-190240-baseline.json
    title: Retrieval baseline run (2026-09-01, commit f518762, dirty tree)
---

# Context

> **Amended by [Decision 0009](/docs/decisions/0009-structured-reply-function-tools.md)**
> (2026-09-02): the `[i]` citation markers, the `NO_ANSWER` sentinel and the
> `ToolSpec` vocabulary below are superseded — the reply is a structured
> output citing chunk ids, and tools are Python functions. Everything else in
> this record stands.

[Decision 0005](/docs/decisions/0005-retrieval-architecture.md) fixed the
macro shape of answering — seed retrieval plus a bounded `query_knowledge`
tool loop in the domain, an `LLM` port speaking
`Message`/`ToolSpec`/`ToolCall` — but left open which library implements
the port, which retrieved chunks become the challenge's `references`, and
how the eval harness invokes the system.[^decision-0005] Evidence on five
candidate libraries was gathered against primary sources,[^llm-evidence]
and the read side landed with a measured retrieval
baseline.[^baseline] Full design in the spec.[^spec]

# Decision

## The adapter is PydanticAI's direct API (`pydantic-ai-slim[openai]`)

`PydanticAiLLM` wraps `pydantic_ai.direct.model_request_sync` — the only
framework candidate that **documents** a caller-owned, single-call,
tools-in/tool-calls-out path ("the only abstraction is input and output
schema translation"), so the domain keeps its loop.[^llm-evidence] Cost is
the smallest real addition measured (+10 packages / 4.2 MB, `openai>=3.0.0`
aligned with the repo pin).[^llm-evidence] The owner weighed it over the
zero-dependency OpenAI-SDK option for developer UX: the model abstraction
and `FallbackModel` make the challenge's optional multi-provider/fallback
enhancement a composition-root swap — native Gemini costs one more extra
(`google`), or none at all via Google's OpenAI-compatible
endpoint.[^llm-evidence]

## References are what the LLM cites

The prompt numbers every context block; the model cites load-bearing
excerpts as `[i]`; `Answer.references` = the cited chunks (from either
path, `seed` or `tool`), first-citation order, deduplicated. Refusals use
a `NO_ANSWER` sentinel and carry **empty** references; an answer with zero
citations falls back to the seed top-k. Rationale: baseline precision@5 is
0.24,[^baseline] so returning everything retrieved would drown the
challenge's references contract in noise and floor the citation-precision
gate; citation forces selectivity.

## The eval harness consumes the domain in-process

Answer evals call `AgentService.answer(question) -> Answer` directly
(references structured: full `Chunk` + score + source), matching the
harness's runner and giving citation scoring `(chunk.filename,
chunk.page)` with no string parsing.[^eval-harness-spec] The HTTP route
stays byte-compatible with the challenge (references as verbatim excerpt
strings) and is covered by TDD integration tests instead.

## Config knobs, all defaulted

`LLM_MODEL=openai:gpt-5-mini`, `RETRIEVAL_K=5` (single source, matching
the eval gates' k), `AGENT_MAX_TOOL_ROUNDS=3` (each round costs a
retrieval — ~340 ms median[^baseline] — plus an LLM call),
`QUERY_KNOWLEDGE_ENABLED=true` (the 0005 toggle; first eval to run is
on-vs-off[^decision-0005]).

# Alternatives rejected

- **OpenAI SDK direct** — fully viable (zero new deps, vendor-documented
  developer-owned loop); lost on owner preference for PydanticAI's model
  abstraction and built-in fallback; the port keeps it one adapter away.[^llm-evidence]
- **Strands Agents / LangChain deepagents** — loop-owning harnesses at the
  wrong layer for a port whose loop lives in the domain; Strands' extra
  additionally downgrades the pinned `openai` SDK.[^llm-evidence]
- **LiteLLM** — right stateless shape, but pins `openai<3.0` (hard
  conflict) and is the heaviest option measured.[^llm-evidence]
- **References = all retrieved chunks** — floors citation precision at
  baseline noise levels (precision@5 0.24[^baseline]) and bloats responses.
- **References = seed top-k only** — hides the tool path's contribution,
  which 0005 explicitly wants measured.[^decision-0005]
- **Eval via HTTP end-to-end** — would force `(doc, page)` to be parsed
  out of contract strings; structure already exists in the domain.

# Consequences

- `src/llm/` is born with `PydanticAiLLM`; `requirements.txt` gains
  `pydantic-ai-slim[openai]`; [architecture.md](/docs/architecture.md)'s
  module map now names PydanticAI direct as the current LLM adapter.
- The fallback enhancement has a recorded, cheap path: add the `google`
  extra, wrap in `FallbackModel` at the composition root when
  `GEMINI_API_KEY` is present.[^llm-evidence] Done in
  [Decision 0012](/docs/decisions/0012-page-chunks-unit-vectors-and-providers.md) (2026-09-02):
  `gpt-5-mini` falls back to `gemini-3.5-flash`.
- Prompt text is a deliberate artifact in
  `src/domain/services/prompts.py`, iterated under evals only.
- Serves _LLM Use_ (deliberate prompt + citation protocol), _Functionality_
  and _API Design_ (exact contract), _Retrieval_ (dual-path contribution
  stays measurable), _Developer UX_ (one key, all knobs defaulted).

[^llm-evidence]: LLM Adapter Library Evidence — measured dependency weight, documented caller-owned APIs, `FallbackModel` and Gemini extras, conflict pins.

[^spec]: Question Agent — Design: vocabulary, service flow, prompt requirements, route, config, test and eval plans.

[^decision-0005]: Decision 0005 — dual-path answering, domain-owned tool loop, tool toggle, per-path reference measurement.

[^eval-harness-spec]: Eval Harness — Design & Implementation Plan — in-process runner and the coordinated `(question) -> Answer` contract.

[^baseline]: Retrieval baseline run 20260901-190240 (f518762, dirty tree) — precision@5 0.24, per-case retrieval latency median 342 ms (mean 548 / p95 2518 ms, five cold-connection outliers above 2 s).
