---
type: Decision
title: 0007 — Naive ingestion baseline: what it is and what it defers
description: The first POST /documents pipeline is deliberately naive — pymupdf4llm without OCR, fixed 1000/200 per-page chunking, OpenAI text-embedding-3-small, sync all-or-nothing route — with deterministic content-addressed IDs for idempotent re-ingestion, kind+metadata extension points on the persisted chunk, and no relational database.
tags: [ingestion, baseline, chunking, embeddings, idempotency, qdrant]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T22:50:49Z }
sources:
  - id: ingestion-spec
    resource: /specs/ingestion-baseline-design.md
    title: Naive Ingestion Baseline — Design
  - id: corpus-findings
    resource: /research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
---

# Context

The golden dataset ([Decision
0006](/docs/decisions/0006-eval-metrics-and-golden-dataset.md)) needs a
system to measure. Eval-first means the first pipeline's job is to be an
honest, measurable baseline whose pieces swap cheaply under eval pressure
([Decision 0004](/docs/decisions/0004-ports-and-adapters-lite.md)) — not
to be good. Full design in the
[spec](/specs/ingestion-baseline-design.md);[^ingestion-spec] this record
distills the durable choices.

# Decision

## The baseline is deliberately naive

- **Extraction**: `pymupdf4llm.to_markdown(page_chunks=True)`, no OCR, no
  quality gate, `write_images=False`. The CESTARI broken text layer
  indexes `�`-runs **on purpose**:[^corpus-findings] the eval must record
  that failure before the OCR gate lands as the first measured
  improvement.
- **Chunking**: fixed-size within each page (~1000 chars, ~200 overlap),
  a pure function — no strategy port until evals demand competing
  strategies.
- **Embeddings**: OpenAI `text-embedding-3-small` — the key is already
  required for the LLM (zero setup burden), multilingual coverage is
  adequate, corpus cost is cents. Evals arbitrate any upgrade (0005 left
  the default open; this fixes only the baseline).
- **Route**: synchronous, all-or-nothing — upfront `%PDF` magic-byte
  validation of every file, `422` naming the offender, nothing partially
  indexed. The challenge contract returns counts and has no per-file
  status, so partial success would invent semantics the API cannot
  express.

## Deterministic, content-addressed identity

`document_id = sha256(file bytes)`; chunk `id = UUID5(document_id:index)`.
Re-uploading the same file upserts the same Qdrant points — re-ingestion
is idempotent and repeated eval runs cannot inflate the index with
duplicates. Accepted limitation: same filename with different content
coexists as two documents.

## The persisted chunk gains extension points

The 0005 payload contract is extended with `kind: str = "text"` and
`metadata: dict` (flows into the schemaless payload untouched). Future
table/image work slots in as `kind="table"` / `kind="image_caption"` +
metadata, no entity or contract redesign. Embeddings are **not** an entity
field: vectors pair with chunks positionally and live only in Qdrant
(hybrid search will make them plural per point).

## No relational database

Qdrant covers everything in scope; even future listing/deletion is a
payload filter. Recorded triggers that would reopen this: transactional
state outside chunks (users, async job status), genuinely relational
metadata queries, or a text source-of-truth separate from the index.
Server-side reindexing without re-upload would need original PDFs
persisted — a blob directory, still not a relational DB.

# Alternatives rejected

- **OCR gate in the baseline** — steals the before/after story of the
  first eval-gated improvement and grows the first session's scope.
- **Discriminated chunk union (`TextChunk | TableChunk | ...`)** — the
  pipeline treats all chunks identically today; architecture rule 4
  demands a real second implementation before abstracting. `kind` promotes
  to real types mechanically when behavior actually diverges.
- **Random chunk UUIDs** — silent duplication on every re-upload;
  eval-corrupting.
- **`write_images=True` in the baseline** — inline `![](path)` refs
  become embedding noise inside `chunk.text`; the image pipeline gets its
  own eval-gated design (sketched in the spec).
- **fastembed / Gemini as baseline embedder** — extra setup or extra key;
  provider-first was already the 0005 direction.

# Consequences

- The eval "before" numbers will be bad on CESTARI questions — that is
  the point; the OCR gate is the first planned experiment.
- `docker-compose.yml` gains the `qdrant` service with a named volume
  (fulfilling the consequence 0005 anticipated).
- Every baseline choice above is an eval-tunable, swapped at the
  composition root or in `src/ingestion/`, gated by before/after runs per
  the [Development Workflow](/docs/development-workflow.md).

[^ingestion-spec]:
    Naive Ingestion Baseline — Design: route contract, entities, ports,
    test plan, deferred image pipeline.

[^corpus-findings]:
    Case Files Corpus Findings — CESTARI broken CMap, measured
    pymupdf4llm 1.28.2 behavior.
