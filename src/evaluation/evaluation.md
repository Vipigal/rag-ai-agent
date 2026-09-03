---
type: Module
title: Eval Harness Module
description: How to run the retrieval eval (make eval / make eval-fresh) and the answer layer (make eval-answers), and what the code cannot say — the eval-collection re-ingestion procedure, the 0.6 token-overlap threshold and the containment subsumption, exclusion rules, the human-readable per-case results schema, the answer gates (fact recall, citation precision/recall, refusal rate) with their normalization caveat, error semantics, worker concurrency and the owner-as-judge workflow, the baseline findings (CESTARI text layer, cross-lingual axis), and where every later run's reading lives (evals/results/experiment-findings.md).
tags: [evals, harness, retrieval, answers, metrics, baseline]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T23:40:00Z }
verified: { by: human:vinicius, at: 2026-09-01T17:27:00Z }
sources:
  - id: spec
    resource: /specs/eval-harness-design.md
    title: Eval Harness — Design & Implementation Plan
  - id: answer-spec
    resource: /specs/answer-eval-design.md
    title: Answer Eval — Design & Implementation Plan
  - id: decision-0006
    resource: /docs/decisions/0006-eval-metrics-and-golden-dataset.md
    title: 0006 — Eval metrics and golden-dataset shape
  - id: golden-dataset
    resource: /evals/golden/golden-dataset.md
    title: Golden Dataset
  - id: baseline-json
    resource: /evals/results/
    title: Committed eval results
---

# What this module is

The runnable eval, two layers over one golden dataset: `dataset.py`
loads and validates the [golden dataset](/evals/golden/golden-dataset.md),
`matching.py` decides chunk↔excerpt relevance, `metrics.py` computes the
retrieval gates and slices, `answers.py` scores the answer layer (fact
containment, citation precision/recall over `(document, page)`, refusals,
usage), `report.py` builds the committed JSON payload and the colored
console report, and `run.py` orchestrates a run end to end. Design
rationale and the full contracts live in the specs;[^spec][^answer-spec]
metric definitions in Decision 0006.[^decision-0006]

# How to run

Qdrant must be up — `make up` in another terminal, since it runs the
stack in the foreground — and `OPENAI_API_KEY` set in the repo `.env`
(`cp .env.example .env` first). The Makefile at the repo root is the
entry point — it checks for `.venv` and `.env`, sources `.env` and sets
the paths:

```
make eval label=<label>
make eval label=<label> k=10 threshold=0.7 args='--no-compare'
```

`args` passes anything else through to the CLI (`--compare
<results.json>`, `--no-compare`). By default the report shows deltas
against the latest result in `evals/results/` with the same
`k`/threshold. Env: `EVAL_QDRANT_COLLECTION` (default `eval_chunks`),
`QDRANT_URL`, `EMBEDDING_MODEL`, `NO_COLOR`. Results are **committed by
the owner** with the experiment that produced them — that is the
before/after evidence chain.

The answer layer is opt-in, because it costs LLM calls and minutes:

```
make eval-answers label=<label> [k=5] [threshold=0.6] [workers=4] [args='--no-compare']
```

Every case — the `unanswerable` ones included — goes through
`AgentService.answer()` in-process, in a thread pool of `workers`, with
the production wiring: `LLM_MODEL` behind its `LLM_FALLBACK_MODEL`,
`QUERY_KNOWLEDGE_ENABLED` and `AGENT_MAX_TOOL_ROUNDS` from `.env` or the
environment, `k` shared with the retrieval gates. The tool-off variant is
one variable away: `QUERY_KNOWLEDGE_ENABLED=false make eval-answers
label=agent-tool-off`. Progress is logged per case (`<id>: answered in
N s (M request(s))`), so a slow provider is distinguishable from a hang.

# Re-ingestion procedure

The runner ingests `case_files/` only when the eval collection is empty
(`store.count() == 0`). After **any ingestion-side change** (chunking,
extraction, OCR), the collection is stale — drop it and re-run in one
step:

```
make eval-fresh label=<label>
```

# What the code cannot say

- **Threshold 0.6** balances short table excerpts (0.5 too loose)
  against boundary-split excerpts (0.7+ too strict); runs with different
  thresholds are not comparable, so it is recorded in every results
  JSON.[^spec]
- **Containment is subsumed by overlap**: normalized containment implies
  overlap 1.0, so `is_relevant` has a single code path. The two-path
  description in Decision 0006 remains the semantic reading.[^spec]
- **The per-case results block is written for eyeballs**: each case
  carries its question, `notes` (the trap it tests), every gate metric's
  per-case contribution, and the bidirectional excerpt↔chunk pairing
  (`matched_by_ranks` / `matches_slots`) with 140-char previews — a red
  case should be diagnosable without opening the YAML or Qdrant. Owner
  requirement from the first review round.
- **`unanswerable` cases** are skipped before retrieval (they gate the
  answer layer's `refusal_rate`); `requires_image` cases run but report in
  a diagnostic row, outside the gates.

# The answer layer — what the code cannot say

- **Opt-in, additive payload.** Without `--answers` the payload is the
  retrieval one plus `"answers": null`, so retrieval experiments stay
  cheap and their results comparable. With it, the `answers` block
  (settings, gates, diagnostics, efficiency, slices), `run.cases.answered`
  and a per-case `answer` block appear; `unanswerable` cases enter the
  case list with `null` retrieval fields and empty `gold_excerpts`.
- **Gates follow Decision 0006 verbatim.**[^decision-0006] `fact_recall`
  over the gated cases that carry `expected_facts`; `citation_precision`
  and `citation_recall` over the unique `(document, page)` pairs of
  `Answer.references` against every gold excerpt and alternate, so a
  CESTARI mirror page counts; `refusal_rate` over the `unanswerable`
  cases, where only a structured `has_answer == false` is a refusal.
  `false_refusal_rate` (gated cases refused) and `errors` are
  diagnostics; `requires_image` cases keep their own row.
- **Fact matching normalizes both sides the same way**: casefold, the
  typographic dashes models like to emit folded to `-` (the first run's
  `Molykote G‑Rapid Plus` carried a U+2011), the `.` or `,` between digits
  deleted (`7,36` ≡ `7.36`), the space between a digit and a unit deleted
  (`2,2 kW` ≡ `2,2kW`, `4 %` ≡ `4%`), whitespace collapsed; then a boundary
  search (`127` matches `127/220 V`, not `1270 V`; `IP55` matches `ip55.`,
  not `IP555`). Accepted limits, pinned by tests so a tightening is
  deliberate: `7,36` also matches a bare `736`; `1,8` does not match
  `1,80` (trailing zeros cannot be stripped without breaking the `1.800`
  digit-grouping case — author the fact as the manual prints it); and word
  boundaries are exact, so `semanal` does not match `semanalmente`.
- **A case exception never kills the run.** `answer()` raising (the
  tool-cap `RuntimeError`, a provider 429/5xx) is recorded as `error` on
  that case and scored as the worst outcome — not answered, facts 0,
  citations 0/0 — and is neither a refusal nor a false refusal. `errors N`
  is painted red; on a 429 the fix is fewer `--workers`.
- **Usage is what the provider reports, plus its price.** `output_tokens`
  include the gpt-5 family's reasoning tokens, and since 2026-09-02
  `reasoning_tokens` names that share (the console prints `out 112.0k
  (reasoning 98.0k)`), because the latency investigation found it was
  85–94 % of the output at the provider's default effort and invisible in
  the totals; `cache_read_tokens` are carried because every tool round
  re-sends the prompt prefix and OpenAI discounts cached input, so tool-on
  cost would otherwise be overstated. **`cost_usd`** is the LLM spend of
  the run priced by genai-prices through the adapter (see the
  [LLM Module](/src/llm/llm.md)) — the `cost:` line shows the run total
  and the per-question mean, so a row of the scoreboard says what it cost
  to produce; embedding calls are not included (three orders of magnitude
  smaller). Per-question means divide by the answered (non-errored) cases.
- **The thinking level is recorded and compared.** `answers.thinking` in
  the JSON and `thinking <level>` on the progress line carry
  `LLM_THINKING` as the run saw it, because two runs at different levels
  are a different experiment; the `EFFICIENCY` lines paint the answer
  latency (mean, p95) and the cost against the compared run — **lower is
  green** there, the opposite of the gates — so a latency experiment reads
  its result on the same screen as the gates it must not move.
- **Latency is measured under concurrency**, so `workers` is recorded
  with the run and answer latencies are comparable only at the same
  value. Each worker thread runs its own event loop; the embedding
  adapter therefore builds one pydantic-ai `Embedder` per thread (see the
  [Retrieval Module](/src/retrieval/retrieval.md)) — the shared-client
  failure was measured on 2026-09-02 before the first run. Each LLM call
  still opens a cold connection (an open question of the spec).
- **Comparison prefers a like run.** An `--answers` run compares against
  the latest result with the same `k`/threshold that also carries an
  `answers` block; if none exists, the retrieval deltas come from the
  latest retrieval-only run and a yellow notice replaces the answer
  deltas.
- **The owner is the judge.** There is no LLM judge (owner decision
  2026-09-01). The per-case `answer` block carries `text` next to
  `reference_answer`, each fact with its verdict, each cited page with
  `in_gold` and its retrieval source, the quoted passages (`quotes`, 140
  characters each) and `unmatched_citations` — the passages the model
  quoted that no chunk contained, dropped by the service (Decision 0013);
  their run total sits in `diagnostics` and on the `ANSWER DIAG` line as
  `unmatched quotes N` — plus usage and latency: filter the red gates,
  read those cases, open the YAML only when the case itself looks wrong.

# Baseline findings (2026-09-01)

First recorded run (`baseline`): recall@5 0.65 · hit_rate@5 0.66 ·
mrr@5 0.60 overall; WEG guia 0.94/0.95/0.85, LB5001 0.56/0.62/0.50,
MN414 0.42/0.44/0.44, CESTARI 0.30/0.30/0.30; precision@5 0.24;
retrieval latency: median ≈ 340 ms, dominated by the per-query
embedding API call — the recorded mean 548 ms / p95 2518 ms carry a
handful of 2.5–3.3 s cold-connection outliers, so read the median as
the typical cost. Interpretations the numbers alone don't carry:

- **The CESTARI CMap corruption is partial**, refining the corpus
  finding of a fully broken text layer: pages ≈ 6–8 extract as clean
  Portuguese, while the manual's middle (e.g. physical pages 18, 40) is
  `�`-runs. The 6 CESTARI hits all resolve to the legible region — the
  0.30 recall is the canary measuring the legible fraction, verified
  against the indexed chunks, not a matching false positive.
- **Cross-lingual retrieval is the second failure axis, not tables**:
  `table_lookup` scores 0.88 (the excerpt authoring rules work), while
  pt questions over the EN manuals hit only 4/16 —
  `text-embedding-3-small` does not bridge "posso ligar direto na
  tomada?" to "direct-on-line starting". Every non-CESTARI LB5001/MN414
  miss is cross-lingual, and `safety` at 0.14 is the intersection of
  the two axes (broken CESTARI middle ∪ cross-lingual), not an
  independent failure. Candidate experiments: stronger multilingual
  embeddings, query translation, hybrid sparse+dense (identifiers cross
  languages verbatim).

# Where the findings live

Every committed run in `evals/results/` is interpreted in [Eval
Experiment Findings](/evals/results/experiment-findings.md): per step,
the gate movement, the cases that flipped and the mechanism behind them,
the negative results, and the failure axes that remain. The answer
layer's first runs are chain 4 there. This concept stays about *how* to
run and read the harness; that one is about *what the runs taught*.

[^spec]: Eval Harness — Design & Implementation Plan.

[^answer-spec]: Answer Eval — Design & Implementation Plan: the answer layer's contracts, populations, normalization rules, error semantics and cost analysis.

[^decision-0006]: 0006 — Eval metrics and golden-dataset shape.

[^golden-dataset]: Golden Dataset — canary roles, page semantics.

[^baseline-json]: Committed eval results — the raw numbers per run.
