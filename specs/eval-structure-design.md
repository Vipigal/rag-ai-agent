---
type: Spec
title: Eval Structure & Golden Dataset — Design
description: Approved design for the eval layer — adopted metrics split into deterministic gates and LLM-judged diagnostics, the golden-dataset case schema with chunking-independent ground truth, case taxonomy and per-document distribution, file layout, and the authoring process.
tags: [evals, golden-dataset, metrics, design, spec]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T22:05:00Z }
verified: { by: human:vinicius, at: 2026-08-31T22:13:00Z }
sources:
  - id: eval-metrics
    resource: /research/rag-eval-metrics-evidence.md
    title: RAG Eval Metrics Evidence
  - id: corpus-findings
    resource: /research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
  - id: decision-0005
    resource: /docs/decisions/0005-retrieval-architecture.md
    title: 0005 — Retrieval architecture
---

# Goal

Give the repo its eval layer as demanded by the
[Development Workflow](/docs/development-workflow.md): a golden dataset over
`case_files/` plus a defined metric set, so that every chunking / embedding /
retrieval / prompting change can show a before/after delta. Serves the two
crux [Golden Rules](/docs/golden-rules.md): _Retrieval_ ("relevant document
chunks are correctly retrieved") and _Functionality_ ("the system works as
described and returns accurate answers").

# Scope

**In this design:** the metric set, the golden-dataset schema, the matching
semantics the harness must implement, the case taxonomy/distribution, file
layout, and the dataset itself (authored by hand in-session).

**Out:** the eval harness implementation (the code that computes metrics).
It is the next task, planned separately and built TDD like any module. This
spec fixes its input contract.

# Metrics

Central rule, from the gathered evidence:[^eval-metrics] **deterministic
metrics gate experiments; LLM-judged metrics only diagnose.** LLM judges
carry position/verbosity/self-enhancement bias and per-sample cost, so no
experiment is accepted or rejected on a judged score alone.

| Layer      | Gates (block/accept an experiment)                                                                                                                   | Diagnostics (report only)                                                               |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Retrieval  | recall@5, hit_rate@5, MRR@5 — computed by gold-excerpt ↔ chunk matching (below)                                                                      | precision@5 (prompt-noise signal)                                                       |
| Answer     | `expected_facts` containment (deterministic string checks, normalized); citation precision/recall as cited (doc, page) vs gold (doc, page) set match | answer correctness vs `reference_answer` and faithfulness, via pinned LLM judge         |
| Efficiency | —                                                                                                                                                    | retrieval latency, end-to-end latency, tokens in/out, $ per question — logged every run |

Rejected with rationale recorded in
[Decision 0006](/docs/decisions/0006-eval-metrics-and-golden-dataset.md):
NDCG (needs graded labels), MAP (needs many multi-passage questions),
chunk-ID ground truth (breaks on every re-chunk).

`k = 5` is the initial cut for all @k metrics; the harness must take `k` as
a parameter so the choice can itself be evaluated.

# Golden-dataset case schema

YAML, one list per file. Every case:

```yaml
- id: weg-guia-012 # <doc-slug>-<seq>, stable forever
  question: "qual o grau de proteção pra usar o motor no lavador?"
  persona: operator # operator | technical
  language: pt # language of the question (pt | en)
  category:
    table_lookup # spec_lookup | table_lookup | figure | image_content
    # | procedure | safety | conceptual | unanswerable
  gold_excerpts: # empty list iff category == unanswerable
    - document: WEG-motores-eletricos-guia-de-especificacao-50032749-brochure-portuguese-web.pdf
      page:
        34 # 1-based physical page index in the PDF file
        # (NOT the number printed on the page)
      text: "verbatim excerpt from the PDF..."
  reference_answer: "Full ideal answer, in the question's language."
  expected_facts: ["IP55"] # optional; strings that MUST appear in the answer
  requires_image: false # true ⇒ diagnostic track, never a gate
  notes: "optional: why the case exists / what trap it tests"
```

Field semantics:

- **`gold_excerpts`** is the retrieval ground truth. Never a chunk ID: a
  retrieved chunk counts as relevant when it contains the excerpt under
  whitespace/case normalization, or exceeds a token-overlap threshold when a
  chunk boundary splits the excerpt. This is the RAGAS
  `NonLLMContextRecall` / promptfoo `contains` pattern.[^eval-metrics] The
  exact threshold is an open harness question — it gets a value and a test
  once real chunking exists.
- **CESTARI caveat**: the CESTARI manual's text layer is broken (CMap
  corruption),[^corpus-findings] so its excerpts are transcriptions from the
  rendered pages. Matching for that document relies on the token-overlap
  path against OCR output by construction.
- **`alternates`** (optional, per excerpt): a list of `{document, page,
  text}` entries that are *equivalent* to the primary excerpt — the same
  fact stated elsewhere, e.g. the ES/EN sections of the trilingual CESTARI
  manual, or a caution the manual repeats verbatim on another page. The
  excerpt slot counts as retrieved when the primary **or any alternate**
  matches a retrieved chunk, and any alternate's (doc, page) is accepted by
  citation scoring. Without this, recall@k would punish the retriever for
  returning a legitimate equivalent passage.
- **`page`** doubles as citation ground truth (Decision 0005's chunk
  payload already carries `document_id` + `page`[^decision-0005]).
- **`expected_facts`** are matched with normalization (case, unit spacing:
  "2.2 kW" ≡ "2,2kW" for pt decimal comma). Mostly for the technical
  persona.
- **`unanswerable` cases** have no excerpts and a `reference_answer` that is
  a grounded refusal; the harness checks the system refused instead of
  hallucinating, and excludes these from retrieval metrics.
- **`requires_image` cases** need visual content (wiring diagrams, exploded
  views) that caption-level ingestion cannot answer. They measure the
  multimodal gap and are excluded from gates until multimodal ingestion
  lands — then they graduate.

# Case taxonomy and distribution (93 cases as authored)

| File                             | Cases | Notes                                                                                                            |
| -------------------------------- | ----- | ---------------------------------------------------------------------------------------------------------------- |
| `lb5001.yaml` (2 p., EN)         | 8     | includes cross-lingual pt→EN cases                                                                               |
| `mn414.yaml` (16 p., EN)         | 17    | includes cross-lingual pt→EN cases and 1 diagnostic image case                                                   |
| `cestari.yaml` (84 p., PT/ES/EN) | 20    | **OCR-ingestion canary** — if ingestion indexes garbage, recall dies here                                        |
| `weg-guia.yaml` (68 p., PT)      | 40    | main source of table and figure cases                                                                            |
| `negatives.yaml`                 | 8     | `unanswerable`: nonexistent models, out-of-corpus WEG products, generic motor questions the corpus doesn't cover |

Cross-cutting quotas the dataset must satisfy:

- personas ≈ 50/50 overall. Operator questions are colloquial pt-BR
  ("posso ligar direto na tomada?"); technical questions name exact models,
  units, standards.
- **≥ 15 `table_lookup`** cases — the tables-ingested-correctly guarantee.
- **~8 `figure`** cases (answerable from caption + surrounding text — these
  gate) and `image_content` cases (`requires_image: true` — diagnostic).
  The original target was ~5 image cases; authoring shipped **2** (6
  figure), because reading the whole corpus showed its figures are
  consistently caption-anchored — nearly every visual fact is also stated
  in text. The only honest image-only questions found were a graph value
  (tE curve) and a photo detail (receptacle contacts); inventing more
  would have required unverifiable reference answers, which poisons a
  golden dataset. Grow this slice when multimodal ingestion work starts.
- **≥ 10 cross-lingual** cases (question language ≠ document language;
  derivable from `language` + `document`, no extra tag).
- **~8 multi-excerpt** cases (>1 gold excerpt) so recall@k is not always
  trivially equal to hit rate.

# Language policy

Operator persona: always pt-BR. Technical persona: pt and en mixed.
Cross-lingual coverage is deliberate: pt questions over the EN-only manuals
(LB5001, MN414) and en questions over the PT-only guide. Metrics are sliced
by `language` and by document to expose cross-lingual embedding failures.

# File layout

```
evals/
  golden/
    lb5001.yaml
    mn414.yaml
    cestari.yaml
    weg-guia.yaml
    negatives.yaml
```

The harness code lives in `src/evaluation/` — where all importable code in
this repo lives — and treats the YAML files as its input contract; run
results land in `evals/results/` (see the
[Eval Harness spec](/specs/eval-harness-design.md)). Dataset grows per
the Development Workflow rule: every wrong answer found in manual use
becomes a case before it is fixed.

# Authoring process (this session)

Hand-authored: the author reads each PDF page-by-page (rendered, not text
layer — mandatory for CESTARI) and writes each case. LLM test-set
generation was rejected: generated questions parrot source phrasing, which
inflates retrieval scores, and the broken CESTARI text layer would poison
generation input. Calibration checkpoint: after the first ~8 cases
(LB5001), the owner reviews tone/difficulty before the remaining ~84 are
written.

Question style rules, calibrated with the owner on the first batch:

1. **Questions never reference the manual or its structure** ("according
   to the relubrication table", "in section 5.1"). Someone with the manual
   in hand would read it, not ask the chatbot. Source anchoring lives in
   `gold_excerpts`, never in the question.
2. Operator questions never reuse the manual's vocabulary (say "parafusar
   na base", not "securely mounted by its mounting holes") — lexical
   overlap with the source inflates retrieval scores.
3. Table excerpts include table title + header row + data row, so
   overlap matching survives a chunker rendering the table as markdown.
4. `expected_facts` stay minimal and numeric; the case's `notes` flags
   normalization traps (decimal comma, digit grouping).
5. `notes` states the trap each case tests, for whoever debugs a red eval.

# Open questions (deferred to the harness task)

1. Token-overlap threshold for split excerpts — needs a value + test.
2. Judge model + temperature pinning for the diagnostic metrics; optional
   hand-verified calibration sample (ARES-style).[^eval-metrics]
3. Build diagnostics on RAGAS vs hand-rolled — gates are trivially
   hand-rolled either way.

[^eval-metrics]:
    RAG Eval Metrics Evidence — adopted/rejected metric
    verdicts, ground-truth encoding practices, LLM-as-judge pitfalls.

[^corpus-findings]:
    Case Files Corpus Findings — CESTARI broken CMap,
    pymupdf4llm behavior, table/figure survey.

[^decision-0005]:
    Decision 0005 — chunk payload carries
    `{document_id, filename, text, page, section, index_in_doc}`.
