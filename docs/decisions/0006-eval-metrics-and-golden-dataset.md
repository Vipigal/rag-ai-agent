---
type: Decision
title: 0006 — Eval metrics and golden-dataset shape
description: Deterministic metrics (recall@5, hit rate, MRR, fact/citation checks) gate experiments while LLM-judged metrics only diagnose; retrieval ground truth is verbatim excerpts + (doc, page), never chunk IDs; the golden dataset is hand-authored YAML in evals/golden/ covering personas, tables, figures, cross-lingual and unanswerable cases.
tags: [evals, metrics, golden-dataset, retrieval, llm-as-judge]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T20:19:48Z }
verified: { by: human:vinicius, at: 2026-08-31T22:15:00Z }
sources:
  - id: eval-metrics
    resource: /docs/research/rag-eval-metrics-evidence.md
    title: RAG Eval Metrics Evidence
  - id: corpus-findings
    resource: /docs/research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
---

# Context

The [Development Workflow](/docs/development-workflow.md) demands that eval
metric and dataset decisions be recorded, and [Decision
0005](/docs/decisions/0005-retrieval-architecture.md) gates every retrieval
experiment on before/after evals — but no metrics or dataset existed. The
evidence gathered on RAG evaluation[^eval-metrics] and the corpus
survey[^corpus-findings] (4 trilingual manuals, exact identifiers, heavy
tables, meaningful figures, one broken text layer, and no fixed chunking
yet) constrain what ground truth can even look like.

# Decision

## Gates are deterministic; LLM judges only diagnose

- **Retrieval gates**: recall@5, hit_rate@5, MRR@5. **Answer gates**:
  `expected_facts` containment (normalized string checks) and citation
  precision/recall as cited-(doc, page) vs gold-(doc, page) set match.
- **Diagnostics (report, never block)**: precision@5, answer correctness vs
  the reference answer, faithfulness, both via a pinned judge model.
- **Efficiency logged every run**: retrieval and end-to-end latency, tokens
  in/out, $ per question.
- Rationale: judged metrics carry position/verbosity/self-enhancement bias,
  variance, and per-sample cost;[^eval-metrics] experiment accept/reject
  must be reproducible for free.

## Ground truth survives re-chunking: excerpts, never chunk IDs

Each case stores `gold_excerpts` — verbatim spans with `document` +
`page`. A retrieved chunk is relevant iff it contains the excerpt under
normalization, or exceeds a token-overlap threshold when a boundary splits
it (the RAGAS `NonLLMContextRecall` / promptfoo `contains`
pattern[^eval-metrics]). `(doc, page)` doubles as citation ground truth via
Decision 0005's chunk payload. CESTARI excerpts are transcriptions from
rendered pages (broken CMap[^corpus-findings]), matched via the
token-overlap path against OCR output.

## The dataset is hand-authored, curated YAML

`evals/golden/{lb5001,mn414,cestari,weg-guia,negatives}.yaml`, ~92 cases:
8/16/20/40 per document (CESTARI is the OCR-ingestion canary) + 8
`unanswerable` negatives. Quotas: personas (`operator` colloquial pt-BR /
`technical`) ≈ 50/50, ≥15 `table_lookup`, ~8 `figure` (gate) + ~5
`image_content` (`requires_image: true`, diagnostic-only until multimodal
ingestion lands), ≥10 cross-lingual, ~8 multi-excerpt. The case schema is
the YAML itself; the rules a case is written by live with the
[Golden Dataset](/evals/golden/golden-dataset.md).

# Alternatives rejected

- **NDCG@k** — needs graded relevance labels; ours are binary by
  construction, and NDCG's advantage only exists with graded
  judgments.[^eval-metrics]
- **MAP** — pays off only with many multi-passage questions; recall@k + MRR
  cover this corpus.[^eval-metrics]
- **Chunk-ID relevance labels** (LlamaIndex expected-ids mode) — every
  chunking experiment would invalidate the dataset, the exact opposite of
  an experiment gate.[^eval-metrics]
- **LLM-generated test set** (RAGAS TestsetGenerator style) — generated
  questions parrot source phrasing and inflate retrieval scores; the
  CESTARI text layer would feed garbage into generation.
- **Page-only labels** — over-credit (a page holds many chunks); kept only
  as the citation-scoring granularity and coarse fallback.
- **JSONL dataset** — YAML wins for a hand-curated set: reviewable diffs,
  block scalars for excerpts.

# Consequences

- The eval harness (next task, TDD) takes `evals/golden/*.yaml` as its
  input contract, computes gates deterministically, takes `k` as a
  parameter, and slices metrics by `persona`, `language`, `category`,
  `document`.
- The token-overlap threshold is **0.6**, chosen against the real corpus
  once chunking existed and recorded in every results JSON. The answer
  gates are hand-rolled and deterministic; there is **no LLM judge** —
  red cases are read from the per-case results JSON, which is written for
  exactly that (owner decision 2026-09-01).
- Every wrong answer found in manual use becomes a case before it is fixed
  (per the [Development Workflow](/docs/development-workflow.md)).
- Serves _Retrieval_ and _Functionality_ (the two crux Golden Rules)
  directly; _LLM Use_ indirectly via faithfulness/correctness diagnostics.

[^eval-metrics]:
    RAG Eval Metrics Evidence — metric definitions, ground
    truth requirements, fit verdicts, judge pitfalls.

[^corpus-findings]:
    Case Files Corpus Findings — CESTARI broken CMap text
    layer; tables/figures survey.
