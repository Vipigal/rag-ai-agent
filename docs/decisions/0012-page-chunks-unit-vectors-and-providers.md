---
type: Decision
title: 0012 — Retrieval granularity and providers: page chunks with unit vectors, Gemini embeddings, LLM fallback, low reasoning effort
description: The chunk is the page and the vector is the unit — each page's paragraphs and table rows are embedded separately and kept as one Qdrant multivector scored by MaxSim (recall@5 0.81 → 0.86, precision@5 0.25 → 0.34) — the embedder is google:gemini-embedding-001 through pydantic-ai's Embedder (recall@5 0.86 → 0.95, six of eleven cross-lingual misses recovered) with the OpenAI models kept as config, the LLM falls back from gpt-5-mini to gemini-3.5-flash through pydantic-ai's FallbackModel, and (amended 2026-09-02) the LLM reasons at low effort through pydantic-ai's unified thinking setting, LLM_THINKING=low, because reasoning tokens were 85–94 % of the output and of the latency (answer mean 16.0 → 5.9 s, cost per run $0.29 → $0.18, gates inside noise, dropped quotes doubled); structured packing, section-level parents, text-embedding-3-large, the other Gemini flash models, the provider default and minimal effort were measured or reasoned out.
tags: [retrieval, chunking, multivector, embeddings, gemini, fallback, pydantic-ai, qdrant, evals, thinking, latency, cost]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T23:55:00Z }
verified: { by: human:vinicius, at: 2026-09-02T18:41:00Z }
sources:
  - id: findings
    resource: /evals/results/experiment-findings.md
    title: Eval Experiment Findings
  - id: decision-0005
    resource: /docs/decisions/0005-retrieval-architecture.md
    title: 0005 — Retrieval architecture
  - id: decision-0008
    resource: /docs/decisions/0008-question-agent-baseline.md
    title: 0008 — Question agent baseline
  - id: decision-0011
    resource: /docs/decisions/0011-ingestion-font-repair-and-structured-chunking.md
    title: 0011 — Ingestion, second pass
  - id: ingestion-module
    resource: /src/ingestion/ingestion.md
    title: Ingestion Module
  - id: retrieval-module
    resource: /src/retrieval/retrieval.md
    title: Retrieval Module
  - id: llm-module
    resource: /src/llm/llm.md
    title: LLM Module
  - id: retrieval-evidence
    resource: /research/retrieval-strategy-evidence.md
    title: Retrieval Strategy Evidence
  - id: challenge
    resource: /docs/challenge.md
    title: Challenge Brief
---

# Context

[Decision 0011](/docs/decisions/0011-ingestion-font-repair-and-structured-chunking.md)
left the corpus legible and clean but its chunker was a red experiment:
packing markdown blocks to 1,200 characters landed neutral on the gates
(recall@5 0.81) because both chunkers _contained_ the gold excerpts and
lost them to embedding dilution — a bigger chunk embeds its topic better
and its specific values worse.[^decision-0011] Two failure axes were
explicit after that step: table-value lookups whose numbers embed weakly
next to prose, and Portuguese questions over the two English manuals,
which `text-embedding-3-small` never bridged (eleven of twelve red cases
after chain 2).[^findings] Separately, the challenge lists "support
multiple LLM providers or fallback behavior" as an optional
deliverable,[^challenge] and [Decision 0008](/docs/decisions/0008-question-agent-baseline.md)
had left pydantic-ai's `FallbackModel` as a recorded, unbuilt
path.[^decision-0008]

Owner decisions taken on 2026-09-02, in conversation: try a chunking
strategy that differs in its core instead of another boundary variant;
try a multilingual Google embedder rather than `text-embedding-3-large`;
make Gemini the default once measured, because the examiners provide any
API keys needed; implement the LLM fallback with pydantic-ai's own logic to
a Gemini model comparable to `gpt-5-mini`.

# Decision

## 1. The chunk is the page; the vector is the unit

`page_chunks` emits one chunk per page with non-empty text — the cleaned
markdown, page number, section, deterministic id — and `embedding_units`
(the `UnitSplitter` callable, in `src/ingestion/`) decides what the
embedder sees for that chunk: one unit per blank-line block, a table
becoming one unit per row with its header and separator repeated, every
unit prefixed with `document stem > section`. The pipeline embeds all
units of a document, regroups them per chunk, and `QdrantVectorStore`
keeps them as **one multivector point per chunk** scored by
`MAX_SIM`: the query is embedded once and sent as a one-row multivector,
so a chunk's score is the cosine of its best unit. `search`, the retriever
and the agent did not change.[^ingestion-module][^retrieval-module]

Why it works: it decouples the granularity that retrieves well (small and
specific — a table row with its column meaning, one prohibition sentence)
from the granularity the model should read (the whole page), which is the
small-to-big evidence[^retrieval-evidence] without a parent index or a
second lookup. The specific-value cases every larger chunk had lost came
back (`weg-guia-025`'s two-row relay table, the CESTARI environmental
spec), and multi-excerpt cases whose excerpts share a page are satisfied
by one slot, which is also why precision@5 rose.[^findings]

## 2. The embedder is `google:gemini-embedding-001`, through pydantic-ai

`PydanticAiEmbeddingModel` wraps pydantic-ai's `Embedder`, the library the
LLM adapter already uses, so OpenAI and Google sit behind one
`EMBEDDING_MODEL` value; documents are embedded as documents and queries
as queries (Google's `RETRIEVAL_DOCUMENT`/`RETRIEVAL_QUERY` task types),
batched per provider, with the dimension fixed by a registry at the
composition root. The default is `google:gemini-embedding-001` (3,072
dimensions); `openai:text-embedding-3-small` and `-large` remain one
config value away and re-indexing is the cost of switching.

Why: the cross-lingual axis was the whole remaining gap and no ingestion
change could touch it. On the eval, the switch recovered six of the eleven
Portuguese-over-English misses plus two others (`cestari-017`,
`weg-guia-013`), LB5001 reached 1.00, and the Portuguese slice rose from
0.83 to 0.94 recall — one config value moved recall more than every
chunking experiment combined.[^findings] The price is a second API key,
which the examiners provide, about 8× the embedding cost per token (cents
for the corpus), roughly +150 ms per query embedding, and doubled vector
storage.

## 3. The LLM falls back from `gpt-5-mini` to `gemini-3.5-flash`

`llm_model()` at the composition root wraps `LLM_MODEL` and
`LLM_FALLBACK_MODEL` (defaults `openai:gpt-5-mini`, then
`google:gemini-3.5-flash`) in pydantic-ai's `FallbackModel`, which moves to
the next model on `ModelAPIError` (4xx, 5xx, connection errors). A blank
`LLM_FALLBACK_MODEL` disables it. When every model fails, pydantic-ai
raises `FallbackExceptionGroup`, which the API maps to 502 naming each
model's error. Nothing in `src/llm/` or the domain moved: Gemini accepts
the same strict tool definitions and native JSON-schema output.[^llm-module]

Why `gemini-3.5-flash`: it is the flash-class model that, probed through
the adapter with a tool offered on 2026-09-02, answered the `AgentReply`
schema and cited correctly, and it took the request end to end when the
primary returned 404. Its latency varied widely in the probe (1.9 s to
45 s), acceptable for a fallback, not for a primary.

## 4. The LLM reasons at `low` effort (amended 2026-09-02)

`build_llm()` at the composition root builds `PydanticAiLLM` with
`ModelSettings(thinking=<LLM_THINKING>)`, default **`low`**
(`minimal`/`low`/`medium`/`high`/`xhigh`/`off`; blank keeps the
provider's default; unknown values are rejected naming the choices). The
route and the eval share `build_llm()`, so a run measures what the API
ships. The unified `thinking` field is chosen over `openai_reasoning_effort`
because pydantic-ai translates it per provider — `reasoning.effort` for
`gpt-5-mini`, `thinking_level` for `gemini-3.5-flash` — so one knob covers
the primary and the fallback, and a model whose profile does not support
thinking ignores it silently.[^llm-module]

Why: the owner's review of the repo found 8–25 s per question too slow for
a demo; the diagnosis (findings chain 6) showed latency correlating 0.92
with output tokens at ≈ 10.6 ms per token, and **reasoning tokens were
85–94 % of the output** at the provider default (medium) — a 23 s answer
spent 1,920 of 2,048 output tokens reasoning. Quotes (≈ 76 tokens),
retrieval (≈ 0.5 s) and the input size were ruled out. `low` on the same
three questions: 6.5 / 12.0 / 23.6 s → 4.4 / 3.1 / 5.2 s.[^findings]

What it cost, measured (`20260903-010828-thinking-low` against the chain
5 run): answer latency mean **16.0 → 5.9 s**, p95 29.0 → 10.2 s; fact
recall 0.92 → 0.91 and citation precision 0.78 → 0.79 (noise); citation
recall **0.90 → 0.86**, because the model quotes fewer pages and copies
less carefully (dropped quotes 7 → 14: passages abridged with `...`, PT/ES
splices on mirrored CESTARI pages); refusals 7/8 unchanged; tool calls
16 → 7; run cost $0.29 (estimated from tokens) → **$0.18** recorded. The
quoting regression is prompt work, queued in the findings, not a reason
to spend three times the tokens on every question.

Rejected: the **provider default** (the latency above, and it was never a
choice — no setting had been sent); **`minimal`** (≈ 3 s in the probe, but
it answered the 440TY oil question with a value not in the table; kept as
a one-run experiment, not the default); **`openai_reasoning_effort`**
(OpenAI-only, the fallback would keep its default); **streaming** (the
contract is one JSON body; it would hide the time, not remove it).

## The measured chain (k=5, threshold 0.6)

| Run                                           | recall@5 | hit_rate@5 |    MRR@5 | precision@5 | red |
| --------------------------------------------- | -------: | ---------: | -------: | ----------: | --: |
| `20260902-041913-embed-context` (end of 0011) |     0.81 |       0.83 |     0.76 |        0.25 |  20 |
| `20260902-045635-page-multivector` (item 1)   |     0.86 |       0.86 |     0.79 |        0.34 |  12 |
| `20260902-052352-gemini-embedding` (item 2)   | **0.95** |   **0.95** | **0.91** |    **0.39** |   6 |

Each row re-ingests the eval collection from scratch; the cases that
flipped and the mechanism behind each are in the
findings.[^findings] The fallback (item 3) is a reliability feature, not a
retrieval change, and has no eval row; it was verified by hand.

# Alternatives rejected

- **Structured packing** (Decision 0011 item 3, and its standalone-table
  variant at 0.77): neutral or worse on the gates, ~200 lines; the
  boundary-only family is expected to land within ±0.02 on this
  dataset.[^findings]
- **Section-level parents** (return the section, not the page, with a page
  fallback): measured before building. No gold excerpt is split by a page
  break (163 variants), three prose paragraphs are cut in 170 pages and no
  table is, and section segments are _larger_ than pages at the tail
  (8,009 characters over six CESTARI pages) while 87 segments are under 200
  characters and would need the packer back.[^findings]
- **A parent-document index** (child chunks in one collection, parents in
  another, a second lookup): Qdrant's multivector gives the same effect on
  one point with no extra collection, no join and no change to `search`.
- **`text-embedding-3-large`**: declined by the owner in favour of a
  multilingual embedder; same provider, same cross-lingual weakness class.
- **Hand-written provider adapters** (the previous `OpenaiEmbeddingModel`
  plus a Google one): pydantic-ai's `Embedder` already carries both, with
  task types and a test model; one library for LLM and embeddings.
- **Other Gemini models as the fallback**: `gemini-2.5-flash` is refused by
  pydantic-ai 2.37.0 for native output together with function tools (a
  `UserError`, hence a 500, not a fallback trigger); `gemini-3.8-flash`
  kept calling the tool instead of answering in the probe;
  `gemini-3.7-flash` and `gemini-3.5-flash-lite` returned 503 at the
  time.[^llm-module]
- **Hybrid sparse + dense now**: still the right tool for the exact
  identifiers left red (`W1/W2`, `MN417`), queued behind the `Retriever`
  port per Decision 0005; not part of this decision.[^decision-0005]

# Consequences

- `GEMINI_API_KEY` is required in every setup path (README, `.env.example`,
  compose, `make check-env`); `OPENAI_API_KEY` stays required for the
  primary LLM. Switching `EMBEDDING_MODEL` means deleting the collection —
  the store refuses an incompatible one with the fix in the message.
- Five pages are ≈ 4–5 k tokens of context per question, three to four
  times before, and `POST /question` now returns whole pages as
  `references` while the challenge shows short excerpts — the open problem
  in [Next Steps](/docs/next-steps.md), section 4. Retrieval improved; the
  wire contract must catch up.
- The multilingual embedder ranks CESTARI's PT/ES/EN mirrors together, so
  one multi-excerpt case (`cestari-009`) lost a slot; mirrored-page
  handling is queued.[^findings]
- What stands: the two read-side ports, the seed-plus-tool answering and
  Qdrant from Decision 0005; deterministic ids and the `kind`/`metadata`
  extension points from 0007; font repair and page cleaning from 0011. The
  `EmbeddingModel` port gained `embed_documents`/`embed_query`, and
  `VectorStore.add` takes one vector group per chunk.
- Rules served: **Retrieval** (recall@5 0.81 → 0.95), **Functionality**
  (a provider outage no longer fails the question; answers in ≈ 6 s
  instead of 16 s), **Developer UX** (one env value per choice, refusals
  that name the fix, a demo that does not wait 20 s per question),
  **Code Quality** (a 21-line chunker and an 18-line embedder adapter
  replaced ~250 lines).
- Item 4 trades citation recall −0.04 and twice the dropped quotes for
  −63 % latency and −39 % cost; `Usage` now carries `reasoning_tokens` and
  a genai-prices `cost_usd`, so every later answer run reports what it
  cost and how much of its output was thinking.

[^findings]: Eval Experiment Findings — chains 2 and 3, the section-parent measurement and the remaining axes.

[^decision-0005]: 0005 — Retrieval architecture: the two read-side ports and Qdrant, which this decision keeps.

[^decision-0008]: 0008 — Question agent baseline: the `FallbackModel` path this decision closes.

[^decision-0011]: 0011 — Ingestion, second pass: the structured chunker this decision replaces; font repair and page cleaning stand.

[^ingestion-module]: Ingestion Module — the page chunker and the unit splitter rules.

[^retrieval-module]: Retrieval Module — the embedder adapter, the multivector store and the retriever.

[^llm-module]: LLM Module — the fallback wiring, the 502 mapping and the model probe.

[^retrieval-evidence]: Retrieval Strategy Evidence — small-to-big / parent-document retrieval and chunk-size studies.

[^challenge]: Challenge Brief — the optional "multiple LLM providers or fallback behavior" deliverable.
