---
type: Reference
title: Eval Experiment Findings
description: What each committed eval run taught and why — the 2026-09-02 ingestion chain step by step (font repair, page cleaning, structured chunking, contextualized embeddings) the chunking-core chain that followed (fontTools refactor proven equivalent, page chunks with per-unit vectors at +0.05 recall) and the embedder chain (gemini-embedding-001 at +0.09 recall, six of eleven cross-lingual cases, 8× the token price in cents), with the cases that flipped and the mechanism behind each move, the negative results (standalone tables, boundary variants at the dataset's noise floor), the discoveries made along the way, and the failure axes that remain, so the next experiment starts from evidence instead of intuition.
tags:
  [
    evals,
    experiments,
    findings,
    retrieval,
    ingestion,
    chunking,
    negative-results,
  ]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T06:40:00Z }
verified: { by: human:vinicius, at: 2026-09-02T18:42:00Z }
sources:
  - id: results
    resource: /evals/results/
    title: Committed eval results (the JSON files next to this concept)
  - id: decision-0011
    resource: /docs/decisions/0011-ingestion-font-repair-and-structured-chunking.md
    title: 0011 — Ingestion, second pass
  - id: eval-module
    resource: /src/evaluation/evaluation.md
    title: Eval Harness Module
  - id: golden-dataset
    resource: /evals/golden/golden-dataset.md
    title: Golden Dataset
  - id: corpus-findings
    resource: /research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
  - id: retrieval-evidence
    resource: /research/retrieval-strategy-evidence.md
    title: Retrieval Strategy Evidence
---

# Why this concept exists

The JSON files in this directory are the evidence; this concept is the
reading. Every kept experiment gets a section stating what changed, what
the gates did, **which cases flipped and why**, and what that teaches
about the system — including the experiments that did not pay off. The
[Eval Harness Module](/src/evaluation/evaluation.md)[^eval-module] says
how runs are produced; decisions cite this concept instead of re-deriving
the numbers.

Reading the tables: gates are recall@5 · hit_rate@5 · MRR@5 over the 83
gated cases (k=5, token-overlap threshold 0.6, `text-embedding-3-small`);
precision@5 is diagnostic. A "flip" is a case whose recall changed between
consecutive runs; case ids resolve in `evals/golden/*.yaml`.[^golden-dataset]

# Chain 1 — ingestion second pass (2026-09-02)

Four changes to the write path, one `make eval-fresh` each, in the order
below ([Decision 0011](/docs/decisions/0011-ingestion-font-repair-and-structured-chunking.md)).[^decision-0011]
The baseline was re-run first and reproduced exactly (0.65/0.66/0.60),
so the deltas are the changes, not the environment.

| Run                                 |  recall@5 | hit_rate@5 |     MRR@5 | precision@5 | red cases |
| ----------------------------------- | --------: | ---------: | --------: | ----------: | --------: |
| `20260901-190240-baseline`          |     0.647 |      0.663 |     0.597 |       0.239 |        32 |
| `20260902-035239-font-repair`       |     0.779 |      0.795 |     0.702 |       0.277 |        21 |
| `20260902-035640-page-cleanup`      |     0.803 |      0.807 |     0.714 |       0.267 |        18 |
| `20260902-041707-structured-chunks` |     0.791 |      0.807 |     0.707 |       0.239 |        20 |
| `20260902-041913-embed-context`     | **0.805** |  **0.831** | **0.759** |       0.248 |        20 |

## Step 1 — font repair: +0.13 recall, the whole gain on CESTARI

- **Change**: fonts without a `ToUnicode` map get one built from Arial's
  standard glyph order before extraction; no OCR.
- **Flips**: twelve CESTARI cases went 0 → 1 (`cestari-005, -006, -007,
-009, -010, -011, -012, -013, -014, -015, -016, -020`); one went 1 → 0
  (`cestari-003`, an environmental spec that had been found on a legible
  page and now competes with 50 newly legible pages).
- **Why**: 50 of CESTARI's 84 pages indexed as `�`-runs — 71,618
  replacement characters. Once the text is legible the embedder simply
  works; CESTARI rises from 0.30 to 0.85 and every other document is
  untouched (their chunks did not change). The three CESTARI cases still
  red after this step are not garbled-text cases (see the axes below).
- **Lesson**: the biggest gain of the session came from _reading_ the
  corpus rather than from retrieval technique. The baseline finding
  "broken CMap, needs OCR" was wrong in a way that only a glyph-level
  probe (`page.get_texttrace()`) revealed.[^corpus-findings]

## Step 2 — page cleaning: +0.02, small and clean

- **Change**: running headers, page numbers, dot leaders and
  pymupdf4llm's picture-text markers stripped from the page markdown.
- **Flips**: `lb5001-006` 0.5 → 1, `weg-guia-013` 0 → 1, `weg-guia-031`
  0.5 → 1; no losses.
- **Why**: every chunk had carried `www.weg.net`, `Especificação do Motor
Elétrico 25` or `MN414` — tokens that add nothing to the vector and
  push it toward the document's "average" chunk. Removing them sharpens
  chunks that were marginal (the three flips were all near the top-5
  boundary). Measured on the corpus, the pass removes only furniture.
- **Lesson**: cheap, deterministic, no dependency; the kind of change
  that should always precede retrieval work because it lowers the noise
  floor for everything after it.

## Step 3 — structured chunking: neutral on the gates (−0.01 / = / −0.01)

- **Change**: the fixed 1000/200 character chunker replaced by packing
  markdown blocks (headings, paragraphs, tables, list items) up to 1200
  characters, never splitting a sentence or a table; sections derived
  from headings for the three PDFs without an outline; 570 → 422 chunks.
- **Flips**: gains `mn414-015` 0 → 1 (the `MN417` identifier case — the
  MN414 page that pymupdf4llm emits as one 2,000-character line is now
  split at sentences, so the short "stored more than 6 months" sentence
  gets its own neighbourhood), `weg-guia-027` 0 → 1, `mn414-008` 0 → 0.5.
  Losses `cestari-017` 1 → 0, `weg-guia-016` 1 → 0, `weg-guia-025` 1 → 0,
  `cestari-010` 1 → 0.5 — every one a **table-value lookup** whose table
  now sits inside a larger chunk.
- **Why the gates did not move**: recall@5 is _containment_ — a chunk is
  relevant when it holds ≥ 60 % of the excerpt's tokens. Both chunkers
  contain the excerpts (a per-case check against the indexed chunks found
  overlap 0.85–1.0 for every lost case); what decides recall is whether
  the **embedding** of the containing chunk ranks in the top five. Bigger,
  cleaner chunks embed the _topic_ better (MRR up where sections help)
  and the _specific value_ worse (a 1,090-character maintenance table
  embeds farther from "de quanto em quanto tempo conferir o nível de óleo"
  than a 1,000-character window that happened to start at the table).
  Chunk boundaries therefore trade a few table cases for a few prose
  cases and net to zero on this dataset.
- **Why precision@5 fell** (0.267 → 0.239): with ~1,000-character
  chunks one relevant chunk usually covers the whole excerpt, so fewer of
  the five slots are "relevant". Precision@5 is a function of chunk size
  here, not of quality.
- **Superseded runs, deleted**: step 3 was run three times before its
  number above was fixed — plain packing before the tiny-chunk rules
  (0.80 / 0.81 / 0.71), the standalone-table variant below (0.77), and
  the final chunker with the embedding header already in place (0.81 /
  0.83 / 0.76, re-run without it so step 4 could be attributed). Only the
  attributable run was kept; the numbers live here.
- **Rejected variant — standalone tables**: chunking every table on its
  own (with heading, one-line intro and caption) scored 0.77: it
  recovered `weg-guia-025` but lost `lb5001-007`, `weg-guia-004`,
  `weg-guia-007` and kept `weg-guia-016` red. The pattern was uniform: the
  retriever found the prose chunk that _introduces_ the table ("Maintenance
  Interval for Motors with Baldor Shaft Grounding Brush", score 0.85) and
  missed the table holding the numbers. A table's semantics live in the
  heading and prose right before it; separating them separates the
  question from the answer. (Run deleted as superseded; the numbers are
  recorded here.)
- **Owner's verdict (2026-09-02)**: a red experiment on effort versus
  gain — the chunker grew from 30 to ~200 lines for no perceptible gate
  movement and lower precision. What the structured chunker does change
  is **what the model reads** (no mid-word cuts, tables whole, a section
  on every chunk), which the retrieval gates cannot see and the answer
  eval does not yet measure. Whether to keep it, revert to the simple
  chunker, or try a strategy that differs in its core (page-level parents
  with small embedding units) is open; see "What to try next".
- **Lesson**: on this dataset chunk-boundary variants move 1–3 cases of
  83 in either direction. Chunking cannot be _chosen_ by these gates; it
  can only be _vetoed_ by them. Choose it on structure, code size and
  what the model reads, and spend retrieval effort where the failures
  actually are.

## Step 4 — contextualized embedding input: +0.01 / +0.02 / +0.05

- **Change**: the embedder sees `filename stem > section > heading`, a
  blank line, then the chunk text; the stored chunk is unchanged.
- **Flips**: gains `cestari-019` 0 → 1 (the warranty case — its chunk now
  embeds under the section "8. Termo de Garantia"), `weg-guia-016` 0 → 1
  (Tabela 4.3 — the inertia table returns under "4.4 Momento de
  Inércia"); losses `weg-guia-020` 1 → 0.67 and `weg-guia-031` 1 → 0.5,
  each a multi-excerpt case losing one slot to a same-section neighbour.
- **Why**: section and heading names are the words a question uses when
  it names its _topic_; putting them in the vector pulls the right
  neighbourhood up (MRR +0.05 is a ranking effect: CESTARI MRR 0.74 →
  0.79, guia 0.80 → 0.90) at the cost of making chunks within one section
  more similar to each other (the two partial losses).
- **Lesson**: the cheapest positive change of the chain (six lines in the
  domain), and it needed steps 2–3 first — sections existed for one
  document before the heading breadcrumb.

# Chain 2 — the chunking core (2026-09-02, same day)

The owner judged Step 3 above a red experiment and asked for either the
simple chunker back or a strategy that differs in its core. Two changes
followed; the first needed no run.

| Run                                        |  recall@5 | hit_rate@5 |     MRR@5 | precision@5 | red cases |
| ------------------------------------------ | --------: | ---------: | --------: | ----------: | --------: |
| `20260902-041913-embed-context` (previous) |     0.805 |      0.831 |     0.759 |       0.248 |        20 |
| `20260902-045635-page-multivector`         | **0.855** |  **0.855** | **0.791** |   **0.339** |        12 |

## Font repair on fontTools — a refactor, proven equivalent

The hand-written 257-name glyph table and name→character dictionary
were replaced by fontTools' `standardGlyphOrder` (minus
`nonbreakingspace`) and `agl.toUnicode`; the module shrank from 190 to
111 lines. The two tables were compared entry by entry: identical except
gid 159 (`Ω` U+03A9 became the ohm sign U+2126, AGL's reading) and gid
209 (`apple` gained the private-use logo glyph), neither used by any
CESTARI span. Extraction output is therefore the same and the run was
skipped on purpose.

## Page chunks with per-unit vectors: +0.05 / +0.02 / +0.03, precision +0.09

- **Change**: the chunk is the page (21-line chunker, no packing); the
  embedder sees each page's paragraphs and table rows (header repeated)
  as separate units, prefixed with document and section; Qdrant keeps
  them as a multivector on the chunk's point and scores by the best unit
  (MaxSim). Retriever and agent untouched. 164 chunks, 2,940 units.
- **Flips**: gains `cestari-003`, `cestari-008`, `weg-guia-025` 0 → 1,
  `cestari-010`, `mn414-008`, `weg-guia-031` 0.5 → 1, `mn414-013`,
  `weg-guia-020` 0.67 → 1; one loss, `weg-guia-013` 1 → 0.
- **Why**: this is the dilution problem solved from the other side. The
  unit that matches the question is small and specific (a table row with
  its header, one prohibition sentence, one spec paragraph), so the
  specific-value questions that every larger chunk had lost come back
  (`weg-guia-025`'s two-row rule table, the CESTARI environmental spec);
  and because the _page_ is what comes back, multi-excerpt cases whose
  excerpts share a page are satisfied by one slot (`mn414-013`,
  `weg-guia-020`, `weg-guia-031`). Precision@5 rises for the same reason:
  a retrieved page usually holds every excerpt the case has.
- **The loss**: `weg-guia-013`'s fact ("entre 2 e 30 segundos") sits
  mid-way through a 600-character paragraph unit whose embedding is about
  soft-starters in general; a neighbouring page's unit outranks it. One
  case, the noise floor.
- **Cost**: five pages ≈ 4–5 k tokens of context per question versus
  ≈ 1.2 k before; ingestion embeds 2,940 units (≈ 250 k tokens, half a
  cent). A first attempt failed on Qdrant's 32 MB JSON limit (the guia's
  1,951 units in one upsert) and produced the batched upsert.
- **Lesson**: what moved the gates was not where chunk boundaries fall
  but the **mismatch between the granularity that retrieves well (small)
  and the granularity the model should read (large)**. Decoupling them
  beat every boundary variant, with less code than any of them.

## Where the twelve remaining red cases are

Eleven are Portuguese questions over the English manuals (`lb5001-003,
-004, -008`, `mn414-002, -004, -006, -010, -012, -014, -016` plus the
image-only `mn414-017`) and one is `weg-guia-013`. The cross-lingual axis
is now the whole remaining gap on retrieval.

# Chain 3 — the embedder (2026-09-02, owner's choice)

The owner asked for `gemini-embedding-001` (MTEB multilingual rank 6
against `text-embedding-3-small`'s 44) to be tried on the eleven
cross-lingual red cases. The embedding adapter was first moved onto
pydantic-ai's `Embedder` (already the LLM's library; OpenAI and Google
behind one class, documents embedded as `RETRIEVAL_DOCUMENT` and queries
as `RETRIEVAL_QUERY` for Google, `dimensions` as a setting) so the
provider is one `EMBEDDING_MODEL` value; the OpenAI path is the same API
call as before and was not re-run.

| Run                                | embedder                               |  recall@5 | hit_rate@5 |     MRR@5 | precision@5 | red cases |
| ---------------------------------- | -------------------------------------- | --------: | ---------: | --------: | ----------: | --------: |
| `20260902-045635-page-multivector` | `openai:text-embedding-3-small` (1536) |     0.855 |      0.855 |     0.791 |       0.339 |        12 |
| `20260902-052352-gemini-embedding` | `google:gemini-embedding-001` (3072)   | **0.952** |  **0.952** | **0.908** |   **0.394** |         6 |

- **Flips**: gains `lb5001-003`, `lb5001-004`, `lb5001-008`, `mn414-002`,
  `mn414-006`, `mn414-010` (six of the eleven cross-lingual cases),
  `cestari-017` (the maintenance-schedule table, red since the structured
  chunker) and `weg-guia-013` (the soft-starter ramp). One loss,
  `cestari-009` 1 → 0.5.
- **Why the cross-lingual cases move**: LB5001 goes to 1.00 and MN414 from
  0.56 to 0.75 — "posso ligar o motor antes de parafusar na base?" now
  lands on the English safety notice; `text-embedding-3-small` never
  bridged that. The Portuguese slice rises from 0.83 to 0.94 recall while
  the English slice reaches 1.00.
- **Why `cestari-009` drops**: the same strength cuts the other way. The
  kr-factor table exists three times in CESTARI (PT, ES, EN mirrors); the
  multilingual embedder ranks the Spanish and English copies next to the
  Portuguese one (slots 1, 2 and 4), and the second excerpt (the Dmin
  paragraph) is crowded out of the top five. Trilingual documents pay for
  cross-lingual strength with duplicated slots; a language filter or
  per-document deduplication of mirrored pages would give the slot back.
- **What remains (6)**: `mn414-004`, `-012`, `-014`, `-016` — Portuguese
  operator phrasings far from the manual's words ("parou sozinha" vs
  "trip conditions", "W1 e W2" wires) — the image-only `mn414-017`, and
  `cestari-009`. Exact identifiers (`W1/W2`) are still the sparse
  channel's job.
- **Cost, measured** (tiktoken over the 2,940 embedding inputs, Gemini's
  tokenizer counting 4 % more on a sample): ingestion 270 k tokens ≈
  **$0.005** with `text-embedding-3-small` ($0.02 / M) versus **$0.042**
  with `gemini-embedding-001` ($0.15 / M paid tier; free of charge on the
  free tier; $0.075 / M through the Batch API). A question costs
  $0.0000004 versus $0.0000034. Query latency: the run's mean 498 ms
  against 336–394 ms on the OpenAI runs — roughly +150 ms per embedding
  call. Storage doubles (3072 dimensions): ≈ 36 MB of vectors for the
  corpus.
- **Lesson**: the axis that ingestion could not touch was the embedder's,
  as predicted; one config value moved recall more than every chunking
  experiment combined. The price is a second API key for whoever runs the
  system and mirrored-section crowding on trilingual manuals.

# Reading precision@5 (asked 2026-09-02)

`precision@5` is `relevant slots / 5` per case, averaged; a slot is
relevant when the chunk holds ≥ 60 % of a gold excerpt's tokens. `k` is
fixed, so the metric is bounded by how many relevant chunks _exist_:

| Measured on `20260902-052352-gemini-embedding`           |          |
| -------------------------------------------------------- | -------: |
| Cases with a single gold page                            | 59 of 85 |
| Ceiling if exactly the gold pages were retrieved         |     0.32 |
| Measured precision@5                                     |     0.39 |
| precision@1 (top slot relevant)                          |     0.87 |
| Irrelevant slots that are the right manual, another page |     62 % |

A single-page case caps at 0.20 (one of five slots), which is why
Decision 0006 made the metric diagnostic. The measured value exceeds the
page-count ceiling because repeated text (MN414's warning boxes, CESTARI's
mirrored languages) makes more than one page match an excerpt. Ranking
quality is what precision@1 and MRR (0.91) show. Levers, in order of
cost, none taken yet: a smaller `k` (measure recall@3 against @5), a
score-relative cutoff in `VectorRetriever` instead of a fixed `k`,
deduplicating mirrored CESTARI pages by page language, a reranker (only
useful with a cutoff), and reporting precision@1 next to precision@5.
The precision that matters downstream is citation precision, measured by
the answer eval once it exists.

# Discoveries made along the way

- **CESTARI is not a broken text layer.** Its body fonts are Type0 /
  Identity-H with CID-keyed CFF programs embedded (`CIDFontType0C`, charsets
  of bare `cidNNNNN` entries) and no ToUnicode; the glyph ids are intact
  and follow Arial's standard order (Apple's Macintosh list minus
  `nonbreakingspace` — fontTools' `standardGlyphOrder` has that entry at
  172, Arial does not). The embedded programs carry no glyph names, so the
  order is the only deterministic mapping; Calibri's ids (272–876) lie
  outside it and are left as `�`. `use_glyphs=True` and OCR were
  measured and rejected.[^corpus-findings]
- **pymupdf4llm 1.28.2 facts that shaped the code**: `margins` did not
  remove any header or footer on this corpus at 40, 55, 70 or 90 pt
  (output byte-identical, although the guia's `www.weg.net` sits 28 pt
  from the top edge and its running title 26 pt from the bottom); the version is the latest on PyPI, with no
  header/footer detection; picture text is wrapped in `<!-- Start/End of
picture text -->`; MN414 pages arrive as single 2,000-character lines
  with `**bold**` pseudo-headings; the rotated CESTARI troubleshooting
  table arrives as a three-line table with 1.6–1.7 k-character rows;
  tables of contents arrive as pipe tables full of dot leaders; heading
  levels come from font size, so `3.4.6` sits under a single `#` and the
  TOC breadcrumb is the richer section path where an outline exists.
- **Cross-lingual was the dominant remaining axis** until chain 3. After chain
  2, eleven of the twelve red cases were Portuguese questions over the two English manuals
  (`lb5001-003, -004, -008`, `mn414-002, -004, -006, -008, -010, -012,
-014, -016`); `text-embedding-3-small` does not bridge "posso ligar
  direto na tomada?" to "direct-on-line starting". No ingestion change
  touched them.
- **Table-value lookups are the second axis**: `cestari-017`,
  `weg-guia-025` and (until step 4) `weg-guia-016` contain the answer in a
  markdown table whose numbers embed weakly next to prose. Exact tokens
  (`ISO VG 220`, `10 kW IV`, `MN417`, `W1/W2`) are what a sparse/BM25
  channel matches verbatim, across languages.
- **Multi-excerpt cases lose slots as chunks grow**: `mn414-013`,
  `weg-guia-020`, `weg-guia-031` need two or three distinct chunks in the
  top five; every merge of neighbouring content costs them.
- **Latency numbers are network**: the per-run mean ranged 300–555 ms
  across identical retrieval code; the per-case median ≈ 340 ms is the
  cost, the rest is OpenAI connection tails.
- **Method that paid off**: re-run the baseline before touching anything;
  one change per run; delete a run when the same step supersedes it, so
  `evals/results/` reads as the chain; diagnose every flip by checking
  the gold excerpt's overlap against the chunks indexed for its page
  (Qdrant scroll on `filename` + `page`) — overlap ≥ 0.6 means the loss
  is on the embedding side, below it means extraction or chunking.

# Section-level parents — measured, not built (2026-09-02)

The owner asked whether small-to-big should return the _section_ instead
of the page, out of concern for passages and tables cut by a page break.
Measured on the extracted corpus and the golden dataset before building:

- **Cross-page content is nearly absent.** Prose paragraphs cut by a page
  break: LB5001 0, MN414 0, CESTARI 2 (one paragraph, PT p9→10 and its EN
  mirror p77→78), guia 1 (p60→61). Tables continuing on the next page:
  none — the three candidates in CESTARI (p21→22 and the ES/EN mirrors)
  are two distinct tables meeting at the break.
- **No gold excerpt crosses a page.** Of 163 excerpt variants, none falls
  below the 0.6 containment threshold on its own page because of a break;
  the two cases with slots on consecutive pages (`cestari-009` p12–13,
  `weg-guia-020` p30–31) sit in different sections, so a section chunk
  would not join them either. Recall has nothing to gain.
- **Sections are extractable but not trustworthy units.** Heading-to-
  heading segments across pages: LB5001 11, MN414 19, CESTARI 87, guia
  256; pages without any heading 4/16, 35/84, 7/68; 87 segments under 200
  characters (heading-only or one-liners that would need merging — the
  packing rules of the retired structured chunker). MN414's headings give
  sections such as "February 2024" and "Figure 3-3".
- **Not smaller at the tail.** The median drops (guia 3,629 → 538
  characters) but CESTARI's p90 doubles (2,165 → 4,291) and the largest
  section (8,009 characters, pages 65–70) exceeds any page (6,441). A cap
  at one page is "page split at headings", i.e. Step 3 of chain 1, which
  was neutral.

Decision: keep page chunks. If a future corpus has multi-page tables, the
cheap design is a `Retriever` decorator that appends the neighbouring
page when the matched unit is the first or last block of its page — no
chunker change.

# What to try next, from this evidence

1. **Hybrid sparse + dense retrieval** behind the `Retriever` port for the
   exact-identifier phrasings still red (`W1/W2`, `MN417`-style tokens);
   RRF fusion.[^retrieval-evidence]
2. **Fewer, cleaner slots**: smaller `k` or a score-relative cutoff (see
   the precision reading above), measured on recall and precision together.
3. **Mirrored-page handling** for trilingual manuals (page language at
   ingestion, filter or dedupe at retrieval) — the `cestari-009` slot.
4. ~~A multilingual embedder~~ — done in chain 3. ~~A chunking strategy
   that differs in its core~~ — done in chain 2. Any boundary-only
   chunking variant should still be expected to land within ±0.02.
5. **Answer-layer eval** (spec approved, not built): citation precision
   is the number that decides whether page-level chunks need the model to
   quote the supporting passage instead of citing the whole page.

[^eval-module]: Eval Harness Module — how runs are produced, thresholds, exclusion rules.

[^decision-0011]: 0011 — Ingestion, second pass: the decisions these runs evidence and the rejected alternatives.

[^golden-dataset]: Golden Dataset — case ids, notes, page semantics and canary roles.

[^corpus-findings]: Case Files Corpus Findings — the corrected CESTARI finding and measured pymupdf4llm behavior.

[^retrieval-evidence]: Retrieval Strategy Evidence — hybrid search, small-to-big and chunk-size evidence.
