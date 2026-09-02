---
type: Decision
title: 0011 — Ingestion, second pass: font repair instead of OCR, page cleaning, structure-aware chunking, contextualized embedding input
description: The naive baseline's four ingestion shortcuts are replaced, one eval run each — fonts lacking a ToUnicode map are repaired in memory from Arial's standard glyph order (CESTARI recall@5 0.30 → 0.85, no Tesseract), running headers, page numbers and dot leaders are stripped, the fixed 1000/200 chunker gives way to packing markdown blocks up to 1200 characters without splitting sentences or tables, sections come from headings where the PDF has no outline, and the embedder sees document, section and heading ahead of the text while the stored chunk stays clean.
tags: [ingestion, font-repair, chunking, page-cleaning, embeddings, sections, evals]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T04:35:00Z }
verified: { by: human:vinicius, at: 2026-09-02T18:41:00Z }
sources:
  - id: decision-0007
    resource: /docs/decisions/0007-naive-ingestion-baseline.md
    title: 0007 — Naive ingestion baseline
  - id: corpus-findings
    resource: /research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
  - id: retrieval-evidence
    resource: /research/retrieval-strategy-evidence.md
    title: Retrieval Strategy Evidence
  - id: ingestion-module
    resource: /src/ingestion/ingestion.md
    title: Ingestion Module
  - id: eval-module
    resource: /src/evaluation/evaluation.md
    title: Eval Harness Module
  - id: results
    resource: /evals/results/
    title: Committed eval results (baseline → embed-context, 2026-09-01/02)
  - id: findings
    resource: /evals/results/experiment-findings.md
    title: Eval Experiment Findings
---

> **Amended the same day (2026-09-02, owner-approved).** Items 3 and 4
> below stand only as history: the structured chunker was judged a red
> experiment on effort versus gain and replaced by **one chunk per page
> whose paragraphs and table rows are embedded as separate unit vectors**
> (Qdrant multivector, MaxSim), which lifted recall@5 0.81 → 0.86 and
> precision@5 0.25 → 0.34; the font-repair tables now come from fontTools
> (`standardGlyphOrder` minus `nonbreakingspace`, `agl.toUnicode`). The
> evidence is in [Eval Experiment Findings](/evals/results/experiment-findings.md),
> chain 2; the decision is recorded as [Decision 0012](/docs/decisions/0012-page-chunks-unit-vectors-and-providers.md)
> and the current rules are in the [Ingestion
> Module](/src/ingestion/ingestion.md). Items 1 and 2 (font repair instead
> of OCR, page cleaning) stand unchanged.

# Context

[Decision 0007](/docs/decisions/0007-naive-ingestion-baseline.md)[^decision-0007]
shipped a deliberately naive pipeline so the golden dataset had something
honest to measure: recall@5 0.65, hit_rate@5 0.66, MRR@5 0.60, with
CESTARI at 0.30 because its text indexed as `�`, and MN414/LB5001 low on
cross-lingual questions.[^eval-module] On 2026-09-02 the owner asked for
the low-cost improvements to be mapped and landed one at a time, each
gated by `make eval-fresh`, replacing everything that existed only to
produce the baseline. Probing the corpus first changed the plan's
centrepiece: the CESTARI "broken CMap" is fonts with **no `ToUnicode`
map and glyph ids intact**, so the OCR gate that 0007 planned as the
first improvement was never needed.[^corpus-findings]

Owner decisions taken in that conversation: repair the fonts instead of
shipping Tesseract; skip the `text-embedding-3-large` experiment (a
multilingual Google embedder is planned instead); chunker without
overlap for now, ~1200 characters, tables whole; the section context
goes into the **embedding input only**, not into `chunk.text`, with the
structured section data kept on the chunk for the prompt.

# Decision

## 1. Fonts lacking a ToUnicode map are repaired before extraction

`pdf_font_repair.repair_fonts` attaches a `ToUnicode` CMap to every
`Type0`/`Identity-H` font without one whose garbled glyph occurrences
fall ≥ 90 % inside the table (spaces excluded) and whose name is not a
symbol font. The table is the standard Macintosh glyph order **as Arial
ships it** (Apple's list minus `nonbreakingspace`), verified on the
corpus glyph by glyph (`Ã`, `Ó`, `Í`, curly quotes). The repair lives in
the extractor adapter, mutates only the in-memory document, and is logged
per file. CESTARI goes from 71,618 replacement characters to 41 and
extracts faster (18.9 s → 13.0 s). No OCR, no new dependency, no change to
the Docker image; the qualification rules in full are in the [Ingestion
Module](/src/ingestion/ingestion.md).[^ingestion-module]

## 2. Page furniture is stripped after extraction

`page_cleaning.clean_pages` removes lines repeated on ≥ 3 pages and half
the document (digit-, whitespace- and emphasis-insensitive; table lines
exempt), bare page numbers, pymupdf4llm's `<!-- picture text -->`
markers and dot leaders, then normalizes whitespace. Measured on the
corpus it removes only `www.weg.net`, the guia's running title, `MN414`,
page numbers and the MN414 table of contents' leader dots.

## 3. Chunks follow the markdown structure

`structured_chunks` replaces `fixed_size_chunks`: blocks (headings, bold
pseudo-headings, tables, list items, paragraphs) are packed in order up
to a 1200-character target; a heading opens the chunk of what it
introduces; oversize paragraphs split at sentence then word boundaries;
oversize tables split by rows repeating the header; a row is atomic; tiny
tails merge; heading-only, near-empty, symbol-only and garbled groups are
dropped; `kind="table"` marks chunks carrying a table. **No overlap.**
Sections come from the TOC breadcrumb where the PDF has an outline and
from the heading breadcrumb otherwise, so every chunk of every corpus
document now carries one (the baseline had sections on the WEG guia
only); `metadata["heading"]` records the nearest heading title.

## 4. The embedder sees the context, the prompt sees the clean text

`embedding_input(chunk)` (domain) is `filename stem > section > heading`,
a blank line, then the text. `chunk.text` is unchanged, so the eval's
excerpt matching and the XML rendered to the model are unaffected; the
query is embedded raw.

## The measured chain (k=5, threshold 0.6, `text-embedding-3-small`)

| Step                        | Results file                             | recall@5 | hit_rate@5 |    MRR@5 | What moved                                                                                                                                                     |
| --------------------------- | ---------------------------------------- | -------: | ---------: | -------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Baseline (0007)             | `20260901-190240-baseline.json`          |     0.65 |       0.66 |     0.60 | —                                                                                                                                                              |
| 1. Font repair              | `20260902-035239-font-repair.json`       |     0.78 |       0.80 |     0.70 | CESTARI 0.30 → 0.85; others unchanged                                                                                                                          |
| 2. Page cleaning            | `20260902-035640-page-cleanup.json`      |     0.80 |       0.81 |     0.71 | guia +0.04, LB5001 +0.06                                                                                                                                       |
| 3. Structured chunks        | `20260902-041707-structured-chunks.json` |     0.79 |       0.81 |     0.71 | MN414 0.42 → 0.51; CESTARI −0.07, guia −0.03 (table-value lookups whose numbers now sit in bigger chunks); 570 → 422 chunks; precision@5 lower by construction |
| 4. Contextualized embedding | `20260902-041913-embed-context.json`     | **0.81** |   **0.83** | **0.76** | CESTARI +0.05 on every gate, guia MRR 0.80 → 0.90; the inércia table (`weg-guia-016`) and the warranty case return, two multi-excerpt guia cases lose one slot |

Each row compares against the previous row's collection, re-ingested
from scratch; the flipped cases and the mechanism behind every move are
in [Eval Experiment Findings](/evals/results/experiment-findings.md).[^findings] Step 3 is kept although neutral on the gates: it removes
mid-word cuts and split tables from what the model reads, gives every
chunk a section, and is the shape the next retrieval experiments assume.

# Alternatives rejected

- **OCR with Tesseract in the image** (0007's plan) — unnecessary once the
  glyph ids proved intact; heavier image, slower ingestion, OCR errors on
  the rotated table. Kept as the fallback for a genuinely rasterized PDF.
- **`use_glyphs=True`** in pymupdf4llm — yields the shifted characters
  `pdftotext` emits; ambiguous with healthy text on the same page, so it
  cannot be repaired downstream.
- **Mapping every Identity-H font**, Calibri included — Calibri's low glyph
  ids map to wrong letters, which is worse than `�`; hence the coverage
  rule.
- **`margins` in pymupdf4llm** for headers/footers — geometric and blind;
  the repetition rule removes only what actually repeats.
- **Standalone table chunks** (each table alone with heading, one-line
  intro and caption) — measured at recall@5 0.77 against 0.80 for plain
  packing: the semantics of a table live in the prose right before it,
  as the small-to-big evidence predicts.[^retrieval-evidence]
- **Character overlap** — kept off; the lost cases in every run were
  embedding dilution, never a boundary split. A one-sentence overlap is
  the first thing to try if that changes.
- **Heading-derived sections for the guia too** — pymupdf4llm's
  font-size levels flatten `3.4.6` under a single `#`; the TOC path is
  richer where it exists.
- **Context inside `chunk.text`** — would duplicate what the XML already
  renders as attributes and `<section>` elements and would count toward
  the excerpt-overlap metric.
- **`text-embedding-3-large`** — declined by the owner in favour of a
  multilingual Google embedder as the next experiment.

# Consequences

- The eval collection had to be re-ingested at every step
  (`make eval-fresh`); the API collection is idempotent but stale
  documents carry the old chunking until re-uploaded.
- The two remaining failure axes are explicit: **cross-lingual**
  questions on the English manuals (MN414 0.51, LB5001 0.62 — the
  embedder's problem) and **table-value lookups** whose numbers embed
  weakly next to prose (`inércia 10 kW IV polos`, oil-change intervals).
  The planned answers are the multilingual embedder and a hybrid
  sparse+dense retriever behind the `Retriever` port (Decision 0005);
  neither is an ingestion change.
- `kind` and `metadata["heading"]` are populated for the first time; the
  prompt renderer can show `<heading>` once the answer eval exists to
  measure it.
- 0007 is amended, not deprecated: deterministic IDs, the embedder, the
  sync route and "no relational database" stand.

[^decision-0007]: 0007 — Naive ingestion baseline: the shortcuts this decision replaces and what it keeps.

[^corpus-findings]: Case Files Corpus Findings — the corrected CESTARI finding and the glyph-order verification.

[^retrieval-evidence]: Retrieval Strategy Evidence — medium/page-level chunks best on average; hybrid search for exact identifiers.

[^ingestion-module]: Ingestion Module — the rules of each pass in detail.

[^eval-module]: Eval Harness Module — baseline findings and how the runs above are produced.

[^findings]: Eval Experiment Findings — per-step flips, mechanisms, negative results and remaining axes.
