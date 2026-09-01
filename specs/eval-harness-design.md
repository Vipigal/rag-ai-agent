---
type: Spec
title: Eval Harness — Design & Implementation Plan
description: Approved design for the retrieval-eval harness — a pure metric core under src/evaluation/ fed by ranked chunks, matching with a 0.6 token-overlap threshold, the minimal read-side slice (VectorStore.search, Retriever port, VectorRetriever), an in-process runner with skip-if-populated ingestion, committed JSON results, and the ordered TDD implementation plan.
tags: [evals, harness, retrieval, metrics, design, spec]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-01T15:18:00Z }
verified: { by: human:vinicius, at: 2026-09-01T15:58:00Z }
sources:
  - id: eval-spec
    resource: /specs/eval-structure-design.md
    title: Eval Structure & Golden Dataset — Design
  - id: decision-0005
    resource: /docs/decisions/0005-retrieval-architecture.md
    title: 0005 — Retrieval architecture
  - id: decision-0006
    resource: /docs/decisions/0006-eval-metrics-and-golden-dataset.md
    title: 0006 — Eval metrics and golden-dataset shape
  - id: golden-dataset
    resource: /evals/golden/golden-dataset.md
    title: Golden Dataset
---

# Goal

Make the eval layer runnable: compute the retrieval gates (recall@k,
`hit_rate@k`, MRR@k), the precision@k diagnostic, and retrieval latency
over the [golden dataset](/evals/golden/golden-dataset.md), and record the
**baseline** every chunking/embedding/retrieval experiment must compare
against — the before/after discipline [Decision
0005](/docs/decisions/0005-retrieval-architecture.md) mandates. Serves
_Retrieval_ and _Functionality_ directly ([Golden
Rules](/docs/golden-rules.md)). This spec doubles as the implementation
plan: the ordered TDD steps at the end are the work.

# Scope

**In:** the harness core (`src/evaluation/`), the minimal read-side slice
per Decision 0005 (`VectorStore.search`/`count`, the `Retriever` port,
the `VectorRetriever` adapter), the CLI runner with in-process ingestion,
JSON results persistence, and the first committed baseline run.

**Out (deferred to the agent/answer session):** `expected_facts`
containment, citation precision/recall over generated answers, the
refusal check on `unanswerable` cases, LLM-judged diagnostics
(correctness, faithfulness), tokens/$ logging, and graduation of
`requires_image` cases. The core is shaped so this layer plugs in without
redesign: retrieval is evaluated through a ranked-chunks input, answers
will be evaluated through a separate answer input — new functions, same
dataset and report.

# Design decisions

1. **Harness code lives in `src/evaluation/`; data stays in `evals/`.**
   (Package renamed from `src/evals/` in the 2026-09-01 review — three
   directories named "evals" with different roles confused humans, and
   the root-data-vs-package name collision was a namespace footgun.) All
   importable code in this repo lives under `src/` (`pytest`
   `pythonpath=src`, Docker copies `src/`); the golden YAMLs and run
   results stay in `evals/golden/` and `evals/results/`. Amends the
   file-layout note in the eval spec,[^eval-spec] which had sketched the
   harness under `evals/`.
2. **The runner is in-process.** It composes the real adapters directly —
   no API server required to run an eval. Ingestion is
   **skip-if-populated**: a dedicated eval collection (default
   `eval_chunks`, env `EVAL_QDRANT_COLLECTION`) is filled from
   `case_files/` only when empty. After any ingestion-side change
   (chunking, extraction), drop the collection and re-run; the module
   concept documents the one-liner.
3. **Results are committed.** Each run writes
   `evals/results/<UTC yyyymmdd-HHMMSS>-<label>.json`; experiment commits
   include their result file, so the before/after history is visible in
   the repo — concrete evidence of the eval-first workflow.
4. **Token-overlap threshold starts at 0.6**, is configurable per run,
   and is recorded in the results JSON (runs with different thresholds
   are not comparable). Rationale: 0.5 is too loose for short table
   excerpts; above 0.7 punishes the legitimate case of an excerpt split
   by a chunk boundary. Edge-case tests pin the behavior; recalibration
   is a one-line change plus a re-run.
5. **The core never sees Qdrant or OpenAI.** `matching`/`metrics` operate
   on case + ranked chunks; only `run.py` touches adapters, through the
   `Retriever` port. This is what makes the core testable with fabricated
   fixtures and keeps it reusable when the answer layer lands.
6. **The read side lands exactly as Decision 0005 shaped
   it**[^decision-0005] — `search` on the persistence port, `Retriever`
   as the strategy port, `VectorRetriever` as its first adapter.
   `RetrievedChunk` ships with `retrieval_source` from day one (owner
   direction, 2026-09-01, to serve the AgentService spec being designed
   in parallel): retrievers return the default `"seed"`; `AgentService`
   re-tags tool-loop results `"tool"` per Decision 0005 — the retriever
   never knows the calling path. Tagging contract confirmed by the
   AgentService spec session (2026-09-01); `Answer.references` will carry
   full `RetrievedChunk`s, so the future answer layer reads
   `(chunk.filename, chunk.page)` for citation scoring directly.

# Module structure

```
src/
  domain/
    models.py       + RetrievedChunk
    ports.py        VectorStore + search()/count(); + Retriever
  retrieval/
    vector_retriever.py   VectorRetriever (embed query → store.search)
    qdrant_store.py       + search(), count()
  evaluation/
    dataset.py      load evals/golden/*.yaml → GoldenCase, validated
    matching.py     normalize, token_overlap, is_relevant
    metrics.py      per-case metrics + aggregation + slicing
    report.py       results payload (JSON) + console table
    run.py          CLI runner (composition, ingestion, loop, persist)
tests/
  retrieval/        VectorRetriever behavior (fakes);
                    Qdrant search/count integration (:memory:)
  evaluation/       dataset, matching, metrics, report, runner (fakes)
evals/
  golden/           input contract (unchanged)
  results/          committed run outputs
```

# Contracts

Dataset types (evals-owned, `dataset.py`):

```python
@dataclass(frozen=True)
class ExcerptVariant:
    document: str
    page: int
    text: str

@dataclass(frozen=True)
class GoldExcerpt:
    document: str
    page: int
    text: str
    alternates: tuple[ExcerptVariant, ...] = ()

@dataclass(frozen=True)
class GoldenCase:
    id: str
    question: str
    persona: str            # operator | technical
    language: str           # pt | en
    category: str           # spec_lookup | table_lookup | figure | ...
    gold_excerpts: tuple[GoldExcerpt, ...]
    reference_answer: str
    expected_facts: tuple[str, ...] = ()
    requires_image: bool = False
    notes: str | None = None
```

Loader validation (fails loudly, naming the case): unique ids; persona /
language / category in their enums; `category == "unanswerable"` iff
`gold_excerpts` is empty; every excerpt and alternate carries document,
page ≥ 1, and non-empty text. A canary test loads the real
`evals/golden/` and asserts the shipped shape: 93 cases, 8 unanswerable,
2 `requires_image`.

Domain additions (per Decision 0005[^decision-0005]):

```python
@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    retrieval_source: str = "seed"

class VectorStore(Protocol):
    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...
    def search(self, vector: list[float], k: int) -> list[RetrievedChunk]: ...
    def count(self) -> int: ...

class Retriever(Protocol):
    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]: ...
```

`count()` exists for skip-if-populated (a one-call Qdrant count).
`QdrantVectorStore.search` reconstructs the `Chunk` from the persisted
payload — the ingestion↔retrieval contract already carries every field.
`VectorRetriever(embedder, store)` embeds the query with the **same
`EmbeddingModel` instance** as ingestion (architecture rule 8) and
delegates to `store.search`.

# Matching semantics

A retrieved chunk is **relevant to an excerpt slot** when, for the
primary excerpt **or any alternate**:[^eval-spec]

1. **Containment**: `normalize(chunk.text)` contains
   `normalize(excerpt.text)`. `normalize` = casefold → punctuation to
   spaces → collapse whitespace. Enough to survive extraction differences
   (markdown pipes, line breaks, case); pinned by tests.
2. **Token-overlap fallback**: else relevant when
   `|tokens(excerpt) ∩ tokens(chunk)| / |tokens(excerpt)| ≥ threshold`
   (sets of alphanumeric runs of the normalized text; default threshold
   0.6, decision 4 above). This is the only path that can match CESTARI
   excerpts (human transcriptions vs whatever ingestion produced) and
   split excerpts.

Implementation note (learned in TDD, 2026-09-01): containment implies
token overlap = 1.0, so path 1 is subsumed by path 2 for any threshold
≤ 1.0 — `is_relevant` implements the single overlap test, and
containment remains the semantic reading, not a separate branch. No
test can distinguish the two-path version from the one-path version.

# Metrics

Per case, over the top-`k` retrieved chunks (`k` parameterized, default
5, recorded per run):[^decision-0006]

- **recall@k** — fraction of the case's excerpt slots with ≥1 relevant
  chunk in the top-k.
- **hit_rate@k** — 1 if any slot was hit, else 0.
- **mrr@k** — 1/rank of the first relevant chunk (0 if none).
- **precision@k** — fraction of the top-k relevant to some slot
  (diagnostic, never a gate).

Exclusions: `unanswerable` cases are excluded from all retrieval metrics;
`requires_image` cases are computed but reported in a separate diagnostic
row, outside the gates — 83 of the 93 cases gate. Aggregation is the mean
over eligible cases: overall + sliced by `persona`, `language`,
`category`, `document` (the document slice is where the CESTARI canary
shows).

# Runner

`make eval label=baseline [k=5] [threshold=0.6] [args='--no-compare']`
— the Makefile sources `.env`, sets `PYTHONPATH=src` and delegates to
`python -m evaluation.run`; `make eval-fresh` drops the eval collection
first (the post-ingestion-change move).

1. Load and validate the dataset.
2. Compose real adapters via shared builders extracted from
   `api/composition.py` (same `.env`: `OPENAI_API_KEY`, `QDRANT_URL`,
   `EMBEDDING_MODEL`), pointing at the eval collection.
3. If `store.count() == 0`, ingest `case_files/*.pdf` through the
   existing `IngestionPipelineService`.
4. For each non-`unanswerable` case: `retriever.retrieve(question, k)`,
   wall-clock latency recorded per case.
5. Score, aggregate, resolve the compare target, print the console
   report, write the results JSON.

The orchestration is a function taking injected collaborators (dataset
path, retriever, ingest callable, results dir, clock) so tests drive it
with fakes; `main()` wires the real ones.

# Console report

The terminal output is the before/after view (owner request,
2026-09-01): by default the run is compared against the most recent
file in `evals/results/` with the **same `k` and threshold** (runs with
different parameters are not comparable); `--compare <path>` picks an
explicit target, `--no-compare` suppresses deltas. Each gate — overall
and in the document slice — renders its value plus the delta against
the compare target:

```
eval run — ocr-gate · 3ab9f01 (clean) · 2026-09-08T11:02:44Z
k=5 · threshold=0.6 · collection=eval_chunks · text-embedding-3-small
93 cases: 83 gated · 2 image-diagnostic · 8 unanswerable (skipped)
compared against 20260901-154210-baseline.json

GATES (83 cases)         recall@5        hit_rate@5      mrr@5
overall                  0.61 (+0.07)    0.70 (+0.07)    0.55 (+0.04)

BY DOCUMENT              cases   recall@5        hit_rate@5      mrr@5
LB5001.pdf                   8   0.88 (=)        0.88 (=)        0.81 (=)
MN414_0224.pdf              16   0.64 (-0.02)    0.75 (=)        0.62 (=)
WEG-CESTARI IOM             20   0.31 (+0.26)    0.35 (+0.30)    0.24 (+0.21)
WEG guia 50032749           39   0.61 (=)        0.69 (=)        0.58 (=)

DIAGNOSTICS   precision@5 0.34 (+0.03) · requires_image (2): recall@5 0.00 (=)
EFFICIENCY    retrieval latency: mean 44 ms · p95 91 ms

→ evals/results/20260908-110244-ocr-gate.json
```

Coloring is pytest-style ANSI, encoding **deltas, not absolute
values** (there is no universal "good" recall to paint green): positive
deltas green, negative red, `(=)` dim; the header line bold. A yellow
notice replaces the compare line when no comparable run exists (the
baseline case) or when the nearest result has a different `k`/threshold
(deltas suppressed rather than lied about). Plain ANSI escape codes in
`report.py` — no new dependency — disabled automatically when stdout is
not a TTY or `NO_COLOR` is set, so piped output and CI logs stay clean.
Latency is reported uncolored: it varies with the machine, not with
retrieval quality.

# Results JSON

```json
{
  "run": {
    "at": "2026-09-01T15:20:00Z",
    "label": "baseline",
    "git_sha": "f518762",
    "git_dirty": false,
    "k": 5,
    "token_overlap_threshold": 0.6,
    "embedding_model": "text-embedding-3-small",
    "collection": "eval_chunks",
    "cases": {
      "total": 93,
      "gated": 83,
      "image_diagnostic": 2,
      "unanswerable_excluded": 8
    }
  },
  "gates": { "recall_at_k": 0.0, "hit_rate_at_k": 0.0, "mrr_at_k": 0.0 },
  "diagnostics": {
    "precision_at_k": 0.0,
    "requires_image": {
      "recall_at_k": 0.0,
      "hit_rate_at_k": 0.0,
      "mrr_at_k": 0.0
    }
  },
  "efficiency": { "retrieval_latency_ms": { "mean": 0.0, "p95": 0.0 } },
  "slices": { "persona": {}, "language": {}, "category": {}, "document": {} },
  "cases": [
    {
      "id": "weg-guia-012",
      "question": "qual o grau de proteção pra usar o motor no lavador?",
      "category": "table_lookup",
      "persona": "operator",
      "language": "pt",
      "notes": "the trap this case tests, copied from the YAML",
      "recall": 1.0,
      "hit": true,
      "reciprocal_rank": 0.5,
      "precision": 0.5,
      "first_relevant_rank": 2,
      "latency_ms": 38.2,
      "gold_excerpts": [
        {
          "slot": 0,
          "document": "…",
          "page": 34,
          "matched_by_ranks": [2],
          "excerpt": "≤140-char excerpt…"
        }
      ],
      "retrieved": [
        {
          "rank": 1,
          "document": "…",
          "page": 11,
          "score": 0.554,
          "matches_slots": [],
          "preview": "≤140-char chunk preview…"
        },
        {
          "rank": 2,
          "document": "…",
          "page": 34,
          "score": 0.539,
          "matches_slots": [0],
          "preview": "≤140-char chunk preview…"
        }
      ]
    }
  ]
}
```

The per-case block is self-sufficient for a human (owner requirement,
first review round): the question, the case's `notes` (the trap being
tested), every gate metric's per-case contribution explicitly, and the
bidirectional excerpt↔chunk pairing (`matched_by_ranks` per gold slot,
`matches_slots` per retrieved chunk) with truncated previews — a red
case is diagnosable without opening the YAML or Qdrant.

# Testing strategy

- `dataset`, `matching`, `metrics`, `report` are pure — unit tests with
  fabricated cases and chunks, including: threshold edge cases, alternate
  matching, multi-excerpt partial recall (2 slots / 1 hit ⇒ 0.5),
  exclusion rules, deterministic JSON payload.
- Qdrant `search`/`count`: integration tests on
  `QdrantClient(":memory:")`, same style as the existing store tests.
- `VectorRetriever` and the runner orchestration: fakes (fake embedder,
  fake store, fake retriever, tmp results dir).
- The real end-to-end validation is the baseline run itself (step 10).

# Implementation plan (TDD, in order)

Each step starts with its failing test; no production code without one.

1. **`dataset.py`** — parse a fixture YAML into `GoldenCase`; validation
   failures name the offending case; canary test over the real
   `evals/golden/` (93 / 8 unanswerable / 2 requires_image).
2. **`matching.py`** — normalization table cases; containment across
   case/whitespace/punctuation; overlap at, just-below, and just-above
   threshold; alternates satisfying a slot.
3. **`metrics.py` (per case)** — recall/hit/MRR/precision over fabricated
   rankings: relevant-at-1, relevant-at-3, none-relevant, multi-excerpt
   partial, duplicate-relevant chunks counted once per slot.
4. **`metrics.py` (aggregation)** — means over eligible cases only;
   unanswerable excluded; requires_image diverted to the diagnostic row;
   slices by the four dimensions.
5. **Domain + Qdrant read side** — `RetrievedChunk`; `search`/`count` on
   the port; adapter tests on `:memory:`: payload→Chunk round-trip,
   ranking by score, `count` on empty vs populated.
6. **`VectorRetriever`** — with fakes: embeds the query once, passes `k`
   through, returns the store's ranking untouched.
7. **`report.py`** — payload matches the schema above (golden-file
   test); console report renders gates + document slice; delta
   rendering against a compare payload (improved / regressed /
   unchanged / no comparable run / parameter mismatch); ANSI coloring
   off in tests by default (non-TTY), one test forces it on and asserts
   the escape codes.
8. **`run.py` orchestration** — with fakes: skips ingest when populated,
   ingests when empty, writes the JSON to the results dir, filename
   convention, latency captured.
9. **Composition + CLI** — shared builders in `api/composition.py`,
   shape agreed with the AgentService spec session (2026-09-01):
   `get_qdrant_client()` and `get_embedder()` cached singletons,
   `build_vector_store(collection)` parameterizable on top of the shared
   client (vector size resolved from the same `EMBEDDING_MODEL` source),
   cached services composed above them. Whichever session reaches the
   file first implements this shape; the other rebases
   (behavior-preserving; existing tests stay green). Then `main()` with
   `--label/--k/--threshold`.
10. **Baseline run** — against the real corpus; sanity-check the harness
    against expectations (CESTARI near-collapse by design,[^golden-dataset]
    weg-guia table cases mixed); commit
    `evals/results/<ts>-baseline.json`.
11. **Documentation ritual** — module concept `src/evaluation/evaluation.md`
    (created as `src/evals/evals.md`, renamed in the review round)
    (owner-approved 2026-09-01); update the architecture map's tree;
    root `index.md` Modules entry; `log.md` entries. The eval-spec
    file-layout amendment ships with this spec.

# Post-review amendments (2026-09-01, owner review)

1. **Package renamed** `src/evals/` → `src/evaluation/` (tests follow):
   three same-named directories confused humans; the root `evals/` data
   home is unchanged.
2. **Per-case results schema v2** — see the example above: context and
   pairing added, every gate metric kept explicitly per case (the owner
   rejected "derivable fields removed" as hurting readability), no
   subjective verdict labels, scores rounded to 3 decimals and latency
   to 1.
3. **Typecheck gate** — pyright `standard` mode (pinned in
   `requirements-dev.txt`, `pyrightconfig.json`), zero errors as part of
   the definition of done for every task; violations fixed with type
   guards and defensive validation, never blanket ignores.
4. **DX entry point** — a root Makefile (`make eval`, `make eval-fresh`,
   `make test`, `make typecheck`, `make up`) replaces loose terminal
   snippets as the way to run the eval.

# Open questions that stay open

Judge model/temperature pinning and RAGAS-vs-hand-rolled diagnostics
remain deferred to the answer-layer session, as in Decision 0006.[^decision-0006] The token-overlap threshold is settled here
(decision 4).

[^eval-spec]:
    Eval Structure & Golden Dataset — Design: case schema,
    matching semantics, alternates, file layout.

[^decision-0005]:
    0005 — Retrieval architecture: VectorStore vs Retriever
    split, VectorRetriever first, single embedder instance.

[^decision-0006]:
    0006 — Eval metrics and golden-dataset shape: gates vs
    diagnostics, k parameterized, open questions deferred to the harness.

[^golden-dataset]:
    Golden Dataset: CESTARI as OCR-ingestion canary; page
    semantics behind citation scoring.
