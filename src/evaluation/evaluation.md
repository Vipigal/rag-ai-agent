---
type: Module
title: Eval Harness Module
description: How to run the retrieval eval (make eval / make eval-fresh) and what its code cannot say — the eval-collection re-ingestion procedure, the 0.6 token-overlap threshold and the containment subsumption, exclusion rules, the human-readable per-case results schema, and the baseline findings including the partially-broken CESTARI text layer and the cross-lingual failure axis.
tags: [evals, harness, retrieval, metrics, baseline]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-01T19:10:00Z }
verified: { by: human:vinicius, at: 2026-09-01T17:27:00Z }
sources:
  - id: spec
    resource: /specs/eval-harness-design.md
    title: Eval Harness — Design & Implementation Plan
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

The runnable retrieval eval: `dataset.py` loads and validates the
[golden dataset](/evals/golden/golden-dataset.md), `matching.py` decides
chunk↔excerpt relevance, `metrics.py` computes the gates and slices,
`report.py` builds the committed JSON payload and the colored console
report, and `run.py` orchestrates a run end to end. Design rationale and
the full contracts live in the spec;[^spec] metric definitions in
Decision 0006.[^decision-0006]

# How to run

Qdrant must be up (`make up`) and `OPENAI_API_KEY` available (the repo
`.env` has to have it). The Makefile at the repo root is the entry
point — it sources `.env` and sets the paths:

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
  future answer layer); `requires_image` cases run but report in a
  diagnostic row, outside the gates.

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

[^spec]: Eval Harness — Design & Implementation Plan.

[^decision-0006]: 0006 — Eval metrics and golden-dataset shape.

[^golden-dataset]: Golden Dataset — canary roles, page semantics.

[^baseline-json]: Committed eval results — the raw numbers per run.
