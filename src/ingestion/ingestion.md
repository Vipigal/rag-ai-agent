---
type: Module
title: Ingestion Module
description: The write path's extraction and chunking stage — pymupdf4llm behind a font-repair pre-pass (ToUnicode CMaps from fontTools' standard glyph order for fonts that lack one, no OCR) and a page-cleaning post-pass (running headers, page numbers, dot leaders), sections from the PDF outline or from markdown headings, one chunk per page, and the small units (paragraphs, table rows) the embedder sees for each chunk — with the rules the code cannot state, the measured corpus numbers and the experiments that shaped them.
tags: [ingestion, pdf-extraction, font-repair, page-cleaning, chunking, embeddings, multivector, pymupdf4llm]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-03T00:40:00Z }
verified: { by: human:vinicius, at: 2026-09-01T03:18:00Z }
sources:
  - id: decision-0011
    resource: /docs/decisions/0011-ingestion-font-repair-and-structured-chunking.md
    title: 0011 — Ingestion, second pass
  - id: findings
    resource: /evals/results/experiment-findings.md
    title: Eval Experiment Findings
  - id: decision-0007
    resource: /docs/decisions/0007-naive-ingestion-baseline.md
    title: 0007 — Naive ingestion baseline
  - id: corpus-findings
    resource: /docs/research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
  - id: retrieval-evidence
    resource: /docs/research/retrieval-strategy-evidence.md
    title: Retrieval Strategy Evidence
  - id: retrieval-module
    resource: /src/retrieval/retrieval.md
    title: Retrieval Module
---

# What this module is

The adapters of the ingestion stage: `Pymupdf4llmExtractor` (the
`PdfExtractor` port) wrapping `pymupdf4llm.to_markdown` between two
passes — `pdf_font_repair.repair_fonts` before extraction and
`page_cleaning.clean_pages` after it — and `page_chunks`, the `Chunker`
callable that makes **one chunk per page**. `embedding_units`, the
`UnitSplitter` callable injected into the pipeline service like the
chunker, decides what the embedder sees for each chunk: its paragraphs
and table rows, each prefixed with the document and section. The Qdrant
store keeps those unit vectors on the chunk's single point. The extractor
is also where a bad file becomes domain language: bytes pymupdf cannot
open (any `RuntimeError` from `pymupdf.open`, `FileDataError` included), a
document that `needs_pass` and a document with zero pages raise
`domain.errors.UnreadableDocument(filename, reason)`, which the API answers
as a 422 naming the file — the route's `%PDF` header check only catches
files that are not PDFs at all ([Decision 0014](/docs/decisions/0014-error-semantics-and-startup-validation.md)). The baseline this replaced is [Decision
0007](/docs/decisions/0007-naive-ingestion-baseline.md);[^decision-0007]
the runs that shaped every rule below are read in [Eval Experiment
Findings](/evals/results/experiment-findings.md).[^findings]

# Font repair — what qualifies and why the table is Arial's

- A font is repaired when it is `Type0`, encoded `Identity-H`, has **no
  `ToUnicode`**, is not a symbol font by name (Wingdings, Webdings,
  Symbol, Dingbats), and at least **90 % of the glyph occurrences** in the
  document's garbled spans (`page.get_texttrace()`, spaces excluded) fall
  inside the table. Coverage is what keeps Calibri out: its glyph ids sit
  beyond the table, and the few low ids it uses would map to **wrong
  letters**, which is worse than `�`. A qualifying font that no garbled
  span uses is left alone.
- The table comes from fontTools: `standardGlyphOrder` (Apple's 258-name
  Macintosh list) **minus `nonbreakingspace`**, which Arial does not carry
  at index 172, mapped to characters with `agl.toUnicode` — 254 entries.
  Verified on the corpus glyph by glyph: 173 renders `Ã` (`INSTALAÇÃO`),
  207 `Ó` (`Óleo`), 179/180 the curly quotes; with Apple's list intact
  they came out `À`, `Ì`, `—`.[^corpus-findings] The embedded programs
  (`CIDFontType0C`, charsets of bare `cidNNNNN` entries) carry no glyph
  names, so this order is the only deterministic source; AGL's `Omega` is
  the ohm sign U+2126.
- The CMap stream is attached to the in-memory document only; the
  uploaded bytes, and therefore `document_id`, are untouched. Extraction
  proceeds on the same `pymupdf.Document` without reopening.
- The API log shows `repaired N font(s) lacking ToUnicode: …` at INFO per
  file. On CESTARI the residue is 41 `�` (single-glyph Calibri labels,
  Wingdings bullets) down from 71,618, and pymupdf4llm gets faster
  (18.9 s → 13.0 s) because it no longer walks `�`-runs.

# Page cleaning — rules and the accepted risk

Applied to the whole document's page texts, after extraction:

- **Repeated furniture**: a line whose key (digits, whitespace and `*`/`_`
  removed) appears on at least 3 pages **and** half of the document's
  pages is dropped from every page. That catches `www.weg.net` (66 of 68
  guia pages), the running title with a page number on either side, and
  `MN414`. Table lines (`|…`) are never candidates. Accepted risk: two
  content lines that differ only in digits count as repeats — nothing in
  the corpus does. A 2-page document (LB5001) is never touched, by the
  3-page floor.
- **Bare page numbers** (`12`, `1-2`, `**5**`, `– 3 –`) are dropped
  everywhere; **pymupdf4llm markers** (`<!-- Start/End of picture text -->`)
  are removed; **dot leaders** (`. . . .` or `....`) collapse to a space;
  trailing spaces go and runs of blank lines collapse.
- `margins` in pymupdf4llm 1.28.2 was measured as a no-op for text on
  this corpus (40–90 pt, output byte-identical), so geometry is not an
  alternative; measured on the corpus this pass removes only furniture.

# Sections — the outline when there is one, headings otherwise

`page_sections(texts, toc_entries)` (pure, in the extractor module) keeps
two breadcrumbs across pages: the PDF outline's (`toc_items`, level →
title) and the markdown headings' (`#` depth → title, decoration and
inline tags stripped). A page's section is the outline path when any
outline entry has been seen, else the heading path, else `None`. The WEG
guia has an outline (richer than pymupdf4llm's font-size heading levels,
which flatten `3.4.6` under one `#`); LB5001, MN414 and CESTARI have none,
so headings are what give their chunks a section at all.

# Chunking — the page is the chunk

`page_chunks` emits one chunk per page with non-empty text: the cleaned
markdown, the page number, the section, deterministic id. No packing, no
overlap, no size cap — the model reads whole pages (median 1.2–3.6 k
characters on the corpus, max 6.4 k), and `RETRIEVAL_K` bounds the
context. This replaced, on the same day, the 200-line structure-aware
packer of Decision 0011[^decision-0011] that had landed neutral on the gates: chunk boundaries could not
move recall because both variants *contained* the answers and lost them
to embedding dilution.[^findings] Measured with the units below: recall@5
0.81 → 0.86, hit_rate@5 0.83 → 0.86, MRR@5 0.76 → 0.79, precision@5
0.25 → 0.34, 164 chunks for the corpus (baseline: 570).

Consequence to keep in mind: five pages are ≈ 4–5 k tokens of context
per question, three to four times the previous chunks; the answer eval's
cost analysis assumed the old size.

# What the embedder sees — small units on one point

- `embedding_units(chunk)` (`src/ingestion/embedding_units.py`; the domain
  pipeline only regroups its vectors per chunk) splits the page on blank lines; a
  table block becomes one unit **per row, with the header and separator
  rows repeated**, so a row embeds with its column meaning; every unit is
  prefixed with `filename stem > section` and a blank line. The corpus
  yields 2,940 units for 164 chunks (median ≈ 250 characters; a guia page
  can have 96). It lives in ingestion, not the domain, because it reads
  the extractor's markdown (table pipes and separator rows) — adapter
  knowledge the domain must not hold (moved 2026-09-02).
- The pipeline embeds all units of a document through the `EmbeddingModel`
  port, regroups them per chunk, and the store keeps them as **one Qdrant
  multivector point per chunk**, scored by its best-matching unit (MaxSim);
  the query goes in as a one-row multivector. `search`, the retriever and
  the agent are unchanged — small-to-big retrieval without a parent
  index.[^retrieval-evidence] The adapters themselves — task types and
  batching per provider, the 750,000-float upsert bound, the refusal of
  incompatible collections and what switching `EMBEDDING_MODEL` costs —
  are the [Retrieval Module](/src/retrieval/retrieval.md)'s
  knowledge.[^retrieval-module] Recorded as
  [Decision 0012](/docs/decisions/0012-page-chunks-unit-vectors-and-providers.md).

# Reference numbers and operations

- Corpus: 164 chunks / 2,940 units — LB5001 2 / 57, MN414 14 / 152,
  CESTARI 81 / 780, WEG guia 67 / 1,951. Ingestion embeddings ≈ 270 k
  tokens: ≈ $0.005 with `openai:text-embedding-3-small`, ≈ $0.04 with
  `google:gemini-embedding-001`, the default since 2026-09-02 (free on
  Google's free tier).
- Extraction (single process, GIL-bound, per the baseline measurement):
  LB5001 ≈ 0.5 s, MN414 ≈ 3 s, CESTARI ≈ 13 s, WEG guia ≈ 39 s,
  dominated by pymupdf4llm table detection.
- The API log per file: `extracting`, `repaired … font(s)` when it
  happens, `page(s) extracted in`, `N chunk(s) as M unit(s) embedded and
  indexed in`, and a `done:` total.
- Re-ingestion is idempotent by deterministic IDs
  (`chunk_id(document_id, index)`, content-addressed `document_id`).
- **An upload is all-or-nothing.** `IngestionPipelineService.ingest` runs
  two phases — extract and chunk every file, then embed and store each —
  so an unreadable second file aborts the request before the first is
  indexed (Decision 0014). The per-file log lines are therefore grouped:
  all `extracting`/`page(s) extracted` lines first, then the
  `embedded and indexed` lines, then `done:`.

[^decision-0011]:
    0011 — Ingestion, second pass: font repair instead of OCR, page
    cleaning, the (since superseded) structured chunker, contextualized
    embeddings.

[^findings]:
    Eval Experiment Findings — every run behind these rules, the cases
    that flipped and why, including the rejected chunkers.

[^decision-0007]:
    0007 — Naive ingestion baseline: the superseded fixed-size chunker
    and the deliberately indexed `�`.

[^corpus-findings]:
    Case Files Corpus Findings — the CESTARI fonts without ToUnicode and
    the glyph-order verification.

[^retrieval-evidence]:
    Retrieval Strategy Evidence — small-to-big / parent-document evidence
    and chunk-size studies behind page-level chunks with small units.

[^retrieval-module]:
    Retrieval Module — the embedder adapter, the multivector store and the
    retriever that hold what this module produces.
