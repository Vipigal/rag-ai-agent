---
type: Module
title: Ingestion Module
description: The write path's extraction and chunking stage — pymupdf4llm adapter with TOC-breadcrumb sections and the fixed-size chunker, deliberately naive per Decision 0007, with the CESTARI broken-text behavior indexed on purpose as the eval baseline.
tags: [ingestion, pdf-extraction, chunking, pymupdf4llm, baseline]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T02:55:04Z }
verified: { by: human:vinicius, at: 2026-09-01T03:18:00Z }
sources:
  - id: ingestion-spec
    resource: /specs/ingestion-baseline-design.md
    title: Naive Ingestion Baseline — Design
  - id: decision-0007
    resource: /docs/decisions/0007-naive-ingestion-baseline.md
    title: 0007 — Naive ingestion baseline
  - id: corpus-findings
    resource: /research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
---

# What this module is

The adapters of the ingestion stage: `Pymupdf4llmExtractor` (the
`PdfExtractor` port) and `fixed_size_chunks` (a plain function, injected
into `IngestionPipelineService` as a callable — deliberately **not** a
port until evals demand competing strategies; see the
[spec](/specs/ingestion-baseline-design.md)[^ingestion-spec]). The
pipeline service itself lives in `src/domain/services/`; the embedder and
vector-store adapters live in `src/retrieval/`. Everything here is the
naive baseline defined in [Decision
0007](/docs/decisions/0007-naive-ingestion-baseline.md).[^decision-0007]

# Behavior that the code cannot say

- **Section breadcrumbs carry forward across pages.** The extractor
  folds each page's `toc_items` into a level→title map and joins the
  levels in order; pages between headings inherit the last seen
  breadcrumb. Observed on the WEG guia: 306 of 323 chunks carry a
  section, but a breadcrumb can go stale when the document's TOC levels
  are inconsistent (e.g. `2. Características da Rede de Alimentação >
3.4.3 Partida com chave compensadora`). Known naive-baseline
  limitation; evals arbitrate whether it matters.
- **CESTARI indexes garbage on purpose.** The broken CMap produces
  `�`-runs (83,751 replacement characters across its 186 chunks on the
  first full-corpus run).[^corpus-findings] This is the documented
  baseline failure the OCR quality gate must beat, with before/after
  evals.
- **Reference corpus baseline numbers** (2026-08-31, first full run):
  570 chunks total — LB5001 9, MN414 52, CESTARI 186, WEG guia 323;
  ~51 s end-to-end for the 4-file upload, dominated by pymupdf4llm table
  detection.
- **Ingestion stays sequential — measured, not assumed** (2026-09-01).
  Per-stage timing on the full corpus: extraction 63.3 s (LB5001 0.8,
  MN414 4.2, CESTARI 18.9, WEG guia 39.4) vs embedding 7.3 s. Extraction
  is GIL-bound Python (4 threads: 65.4 s — no gain); embedding is I/O and
  does parallelize (7.3 → 2.1 s in 4 threads), but that caps the win at
  ~5 s of ~70, so the threading complexity was declined. A real
  extraction speedup means processes (`ProcessPoolExecutor`, ~4× memory)
  or touching table detection — the latter is a retrieval-quality
  decision (the golden dataset's `table_lookup` cases depend on it),
  eval-gated, never a perf freebie.
- **The upload is visibly alive** (2026-09-02, [Decision
  0010](/docs/decisions/0010-examiner-developer-ux.md)). With `make up` in
  the foreground, the API log shows one INFO line per stage per file —
  `extracting`, `page(s) extracted in`, `chunk(s) embedded and indexed
  in` — plus a start line and a `done:` total, so the ~60 s corpus upload
  can be followed. The one silent stretch is inside pymupdf4llm on the
  WEG guia (~39 s of the extraction above); per-page logging would need
  per-page extraction calls, an eval-gated ingestion change.
- **Re-ingestion is idempotent** by deterministic IDs
  (`chunk_id(document_id, index)`, content-addressed `document_id`) —
  verified live: re-uploading a file leaves the point count unchanged.

[^ingestion-spec]:
    Naive Ingestion Baseline — Design: entities, ports, pipeline, test
    plan.

[^decision-0007]:
    0007 — Naive ingestion baseline: the durable choices and their
    rejected alternatives.

[^corpus-findings]:
    Case Files Corpus Findings — the CESTARI broken-CMap trap and
    measured pymupdf4llm behavior.
