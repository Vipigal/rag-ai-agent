---
type: Reference
title: Eval Experiment Findings
description: What every committed eval run taught and why — seven measured chains that took recall@5 from 0.65 to 0.95 and reshaped the answer layer, which cases flipped at each step and the mechanism behind each move, the negative results kept on the record, and the probes run before building anything.
tags:
  [
    evals,
    experiments,
    findings,
    retrieval,
    ingestion,
    chunking,
    answers,
    negative-results,
  ]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T23:55:00Z }
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
    resource: /docs/research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
  - id: retrieval-evidence
    resource: /docs/research/retrieval-strategy-evidence.md
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

## Where the red cases concentrate after chain 2

Twelve remain. Eleven are Portuguese questions over the English manuals (`lb5001-003,
-004, -008`, `mn414-002, -004, -006, -010, -012, -014, -016` plus the
image-only `mn414-017`) and one is `weg-guia-013`. Ingestion had exhausted
what it could reach: the gap was now a single axis, cross-lingual
embedding, and chain 3 went straight at it.

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

# Chain 4 — the answer layer (2026-09-02)

The harness's answer layer landed and ran twice
over the chain-3 collection: `openai:gpt-5-mini` behind its
`google:gemini-3.5-flash` fallback (never triggered), k = 5, 8 workers,
zero errors in both runs. The retrieval gates are unchanged (0.95 · 0.95 ·
0.91 — same seed retriever); the rows below are the whole `/question`
path, scored deterministically.

| Run                              | tool |   fact_recall (57) | cit. precision | cit. recall | refusal_rate (8) | false refusal | latency mean · p95 · median | LLM calls · tool calls | tokens in (cached) · out | per question in · out |
| -------------------------------- | ---- | -----------------: | -------------: | ----------: | ---------------: | ------------: | --------------------------- | ---------------------- | ------------------------ | --------------------- |
| `20260902-202721-agent-tool-on`  | on   |           **0.93** |           0.70 |    **0.92** |       0.75 (6/8) |          0.02 | 11.7 s · 23.7 s · 10.2 s    | 111 · 18               | 711 k (524 k) · 78.6 k   | 7.6 k · 845           |
| `20260902-203011-agent-tool-off` | off  |               0.92 |       **0.73** |        0.91 |   **0.88** (7/8) |          0.04 | 10.5 s · 19.2 s · 9.7 s     | 93 · 0                 | 459 k (347 k) · 69.5 k   | 4.9 k · 747           |

**Run-to-run noise first.** A first tool-on pass with the same code minus
the dash folding in the fact matcher (superseded, deleted) read 0.89 ·
0.72 · 0.94 · 0.88. The model's own variance is therefore ≈ ±0.03 on the
fact and citation gates and one case (0.125) on the refusal rate; nothing
between the two rows above is a difference. Single-run deltas under that
are not evidence.

## What `query_knowledge` buys — nothing on the gates

- It fires on 11 of 93 cases: five negatives before refusing (the intended
  behaviour), the refusals `mn414-016`, `mn414-017`, `weg-guia-026`,
  `weg-guia-040`, the multi-excerpt `weg-guia-020`, and `cestari-009` —
  the one case it rescues: the English mirror of the Dmin paragraph
  (p64) comes back, citation recall 0.5 → 1.0, while the tool-off run
  refused the question.
- It **never fires on the three cross-lingual retrieval reds**
  (`mn414-004`, `-012`, `-014`). The Portuguese chunks from CESTARI and the
  guia look plausible, so the model answers from them: "Pode, mas só com
  restrições" to a dry-run question whose manual says _never_; a list of
  trip causes taken from the gearbox manual; lifting instructions for the
  wrong product — every citation non-gold, in both runs. **A retrieval
  miss is a confident wrong answer with wrong references, and the tool does
  not compensate.** The fix belongs to the seed retriever (see the
  cross-lingual residue below).
- Cost: +1.2 s mean (+0.5 s median), 18 more LLM calls, 55 % more input
  tokens — three quarters of them reported as cached in both runs (74–76
  % cache hits, higher than the spec's estimate; read the provider's
  number with care) — ≈ $0.22 against $0.18 per run at gpt-5-mini list
  prices.
- Decision left to the owner: on this dataset the tool is a reliability
  feature for negatives and mirrored manuals, not a gate mover.

## Where the reds are (both runs)

Thirteen cases are red in both runs; two more flip with the model's
randomness. By cause:

1. **Retrieval** (the largest group, citation recall 0 on all): the three
   cross-lingual wrong answers above; `mn414-016` (`W1`/`W2`), refused
   after two tool rounds; `mn414-017`, image-only, refused.
2. **Model imprecision on numbers**: `cestari-009` states the Dmin
   equation without its constant 2000 (tool on; tool off refused);
   `weg-guia-002` converts 100 cv with 0.75 instead of 0.736 and lands on
   19.09 kvar instead of 18.735.
3. **False refusals with retrieval recall 1.0**: `weg-guia-026` (the Pt-100
   formula reaches the model flattened by extraction and it declares it
   absent) and `weg-guia-040` (the tE value lives in a curve; a legitimate
   refusal, kept as the image diagnostic). Prompt-iteration candidates,
   one change per run.
4. **Negatives answered**: `neg-007` in both runs — the pump-motor warranty
   answered with the gearbox manual's 12 months (CESTARI p76), the
   cross-document bait; `neg-008` with the tool on — grease for CESTARI
   bearings answered with the storage grease from p60 (Texaco Multifak
   EP2), exactly the plausible-wrong-identifier trap the case was authored
   for.
5. **Fact-authoring artifacts**, correct answers scored red:
   `cestari-017` (`semanal`/`mensal` against the model's
   `semanalmente`/`mensalmente` — word boundaries are exact) and
   `weg-guia-016` (`1,8` against `1,80 kgm²`; trailing zeros cannot be
   stripped without breaking `1.800`). Author facts as the manual prints
   them. `cestari-011` was the same class — a U+2011 hyphen in `Molykote
   G‑Rapid Plus` — and the harness now folds dashes.
6. **Citation-set noise**: `mn414-013` (three excerpts, two pages cited →
   0.67); `weg-guia-007` and `weg-guia-014` flip between runs on which of
   two equally valid pages the model cites (the guia prints the class-F
   table on pages 16 and 35; the fact is right both times).

## Reading citation precision 0.70

The 81 answered gated cases cite 1.8 pages each; 44 cite more than one.
Of the 58 cited pages that are not gold, 40 are another page of the right
manual (adjacent content, a second table with the same fact) and 18
another manual — most of them the three cross-lingual reds. This is the
number chain 5 moves by making each citation a quoted passage: a quote
cannot repair a wrong-manual citation, but it turns the forty "right
manual, extra page" references into passages a reader can check.

**Lessons**: the answer layer's reds are dominated by retrieval, then by
dataset authoring, then by the model; a retrieval red is a wrong answer
with wrong references, and the agentic path does not mitigate it; and the
model's run-to-run variance (±0.03) sets the floor under which an
answer-layer delta means nothing.

# Chain 5 — citations as quotes (2026-09-02)

[Decision 0013](/docs/decisions/0013-citations-as-quotes.md) replaced
chunk-id citations with passages the model copies verbatim, resolved by
normalized containment over the chunks it saw; `references` on the wire
became those quotes. Gate: `make eval-answers` against the ids baseline
`20260902-202721-agent-tool-on`, same configuration (gpt-5-mini behind the
Gemini fallback, tool on, k = 5, 8 workers).

| Run                                          | fact_recall | cit. precision | cit. recall | refusal_rate | unmatched quotes | pages cited per answer | latency mean | tokens out per question |
| -------------------------------------------- | ----------: | -------------: | ----------: | -----------: | ---------------: | ---------------------: | -----------: | ----------------------: |
| `20260902-202721-agent-tool-on` (chunk ids)  |        0.93 |           0.70 |        0.92 |         0.75 |              n/a |                   1.81 |       11.7 s |                     845 |
| `20260902-221750-citations-as-quotes` (quotes)                            |     0.92 |        **0.78** |      0.90 |       0.88 |        7 |               1.39 |      16.0 s |                  1,255 |

Two passes were run on the way and superseded (deleted): the first, with
only a count of dropped quotes, read 0.91 · 0.77 · 0.91 · 0.75 with 6
unmatched quotes; the second, which recorded the dropped quotes
themselves, read 0.93 · 0.77 · 0.90 · 0.62 with 18 — and showed why they
were dropped. The row above is the third pass, with the normalizer
folding what those 18 taught.

## What quoting changed

- **Citation precision rose by 0.08 (0.70 → 0.78)**, above the ±0.03 noise, and for
  a visible reason: the model cites fewer pages when it must quote them —
  1.39 pages per answer against 1.81, and the cited pages that are not
  gold fell from 58 to 31 (19 another page of the right manual,
  12 another manual). A chunk id was free to cite; a quote is a
  commitment.
- **Fact recall and citation recall did not move** beyond noise: the
  passages the model quotes are the ones it was already reading.
- **Cost**: 1,255 output tokens per question against 845 — the quotes are
  written out — and 16.0 s mean latency against 11.7 s.
- **Unmatched quotes**: 7 of ≈ 200 quoted passages
  (96 % verified). The second pass's 18 dropped quotes taught the
  normalizer two rules: the model wraps passages in straight or curly
  quotation marks (`"…"`, `“…”`, `«…»`) and writes `its’` for the source's
  `its'`; and table cells carry HTML tags beyond `<br>` — a `<sup>` broke a
  header row. With quotation marks and any HTML tag folded, 16 of those 18
  resolved offline against the indexed pages; the two that did not were a
  Portuguese rendering of an English passage and a sentence that continues
  past what the page holds — exactly what should be dropped.
  The final pass's seven are list items quoted with their markers, a
  table row whose cells begin with comparison signs, and sentences the
  page does not hold verbatim — a residue of 3.5 %.
- **Answers with no reference**: 1 answered gated case whose only
  quote failed (`cestari-015`).
- **One error in the final pass**: `mn414-016`, a second malformed
  structured reply (invalid JSON, trailing characters — see the incidents
  below); recorded as the worst outcome, as designed.
  Invalid JSON: trailing characters at line 1 column 157`; recorded as the worst outcome, as designed.

## Incidents worth recording

- **A malformed structured output.** In the second pass `neg-006` returned
  after 617 s with invalid JSON — trailing characters after a complete
  `{"answer":"","citations":[],"has_answer":false}`. The adapter's
  validation raised, the harness recorded the `error`, and in production
  the same reply is the 500 Decision 0009 chose for schema violations. The
  third pass produced a second one (`mn414-016`, trailing characters after
  a complete refusal object): two replies in ≈ 650 answers across the seven
  answer runs of the day, both refusals, both in the quotes era. The run
  info does not record which model — the primary or the Gemini fallback —
  produced a reply, so the provider is not named here. The
  617 s reply also inflated that pass's mean latency to 21.7 s (15.2 s
  without it).
- **Answer language on the challenge's question.** Three consecutive live
  runs of "What is the power consumption of the motor?" over the four
  manuals produced a Portuguese answer, an English answer and a refusal
  asking which motor was meant. The question is underspecified for this
  corpus, and the language rule slipped once. The harness has no language
  gate, so this was read by hand — and it is what chain 7's language rule
  was written against.
- **An `async def` route driving a synchronous pipeline.** Recapturing the
  README examples surfaced it: on uvicorn's loop `embed_sync` refuses with
  `this event loop is already running`. The route became a plain `def`,
  which also keeps the CPU-bound extraction off the loop, and the rule is
  now architecture rule 5. Verified by re-ingesting the four manuals
  (164 chunks) through it.

## Live captures

The README's grease question now returns three references, each the
sentence that grounds one claim, from two manuals in two languages. The
dry-run question (`mn414-004`) reproduced its red live: verbatim quotes
from the wrong passage (operation in gases and vapours, MN414 p7) support
a wrong "yes, with restrictions". Quoting makes wrong grounding
_visible_; only retrieval can fix it.

**Lessons**: quotes raise citation precision by making citation costly;
the containment normalizer is where the model's typography meets the
extractor's markup, and both rules were learned from dropped quotes, not
guessed; a retrieval miss stays a wrong answer — now with verifiable wrong
quotes.

# Chain 6 — reasoning effort, the latency chain (2026-09-02)

The owner's review found the `/question` latency (8–25 s live, 16.0 s
mean in chain 5) too high for a demo and asked where it came from before
anything was changed. Diagnosis first, from the chain 5 JSON, then a live
probe, then one eval run.

**Where the time went.** Over the 84 single-request cases of chain 5,
answer latency correlates **0.92 with output tokens** (0.25 with input
tokens, 0.58 with quote characters): 10.6 ms per output token with a 1.5 s
intercept. The output was 1,275 tokens per question, but the visible
answer and quotes account for ≈ 130 of them — the rest was reasoning.
A probe through the adapter with `usage.details` printed showed it: the
23 s question (`lb5001-001`) spent **1,920 of its 2,048 output tokens
reasoning** at the provider's default effort (medium for `gpt-5-mini`);
the fastest answers had 300–450 output tokens. Retrieval is a fixed
≈ 0.5 s (Gemini query embedding 0.35–0.5 s, Qdrant 0.01 s); the
`query_knowledge` rounds only stretch the tail (8 of 92 cases; a 4-request
case took 55 s); quotes cost ≈ 76 tokens ≈ 0.8 s. Same three questions,
one variable: default 6.5 / 12.0 / 23.6 s → `low` 4.4 / 3.1 / 5.2 s →
`minimal` 2.6 / 2.6 / 5.1 s, reasoning tokens 384–1,920 → 128–320 → 0.
`minimal` answered the 440TY oil question with a "1.5" that is not in the
table, so `low` became the default and the eval decided (Decision 0012
§4; the knob is `LLM_THINKING`, the LLM module says how it reaches both
providers). The adapter now records `reasoning_tokens` and prices each
response with genai-prices (`cost_usd`), so this chain is the first with
a cost column that is measured, not estimated.

| Run                                        | thinking | fact_recall | cit. precision | cit. recall | refusal | false refusal | errors | unmatched quotes | pages / answer | quotes / answer | latency mean / median / p95 | out tokens per q. | reasoning per q. | tool calls | cost (LLM) |
| ------------------------------------------ | -------- | ----------: | -------------: | ----------: | ------: | ------------: | -----: | ---------------: | -------------: | --------------: | --------------------------: | ----------------: | ---------------: | ---------: | ---------: |
| `20260902-221750-citations-as-quotes`      | default (medium) | 0.92 | 0.78 | 0.90 | 7/8 | 0.02 | 1 | 7 | 1.38 | 2.48 | 16.0 / 13.7 / 29.0 s | 1,255 | not recorded | 16 | ≈ $0.29 (from tokens) |
| `20260903-010828-thinking-low`             | **low**  | 0.91 (−0.01) | 0.79 (+0.01) | **0.86 (−0.04)** | 7/8 (=) | 0.02 (=) | 0 | **14** | 1.22 | 2.06 | **5.9 / 5.7 / 10.2 s** | 389 | 184 | 7 | **$0.18** |

Same collection, same k, same tool settings, 8 workers; the retrieval
gates are identical by construction (`=` on every row).

## What low effort changed

- **Latency −63 % on the mean, −65 % on p95, the whole distribution
  moved**: slowest case 89 s → 15 s, fastest 4.7 → 2.2 s. Output tokens
  per question 1,255 → 389, of which 184 are still reasoning: `low` is not
  zero thinking, it is a third of the budget.
- **Fact recall and citation precision are inside the ±0.03 noise.**
  Three cases flipped: `cestari-009` (the chain-3 loser) is now answered
  with half its facts instead of refused; `mn414-015` (storage over six
  months) lost its fact — the answer names the procedure without the
  number; `mn414-016` went from the chain-5 malformed-JSON error to a
  clean refusal (not attributable to the setting; the error was a
  provider incident).
- **Citation recall −0.04 is the cost, and it has a mechanism.** The
  model cites fewer pages (1.38 → 1.22 per answer) and copies less
  carefully: **unmatched quotes doubled, 7 → 14**. Read one by one, the
  new failures are of two kinds the chain-5 normalizer does not forgive:
  passages **abridged with `...`** in the middle (`weg-guia-039`, whose
  only quote was dropped, so the case scores 0/0), and passages that
  **blend the mirrored PT/ES text** of a CESTARI page into one sentence
  ("Para períodos de 6 meses até 9 meses sem operação, es recomendado
  llenar…", `cestari-004`, `mn414-007`, `mn414-014`). Two cases lost every
  quote (`cestari-015`, `weg-guia-039`); the by-document deltas show it as
  LB5001 precision −0.12 and the guia's recall −0.08 on single cases.
- **The tool fires less: 16 → 7 calls.** Less deliberation means fewer
  reformulated searches; `cestari-009` was nonetheless rescued, so the
  seed context, not the tool, carried it this time.
- **Cost −39 %**: $0.29 (estimated from the recorded tokens of chain 5
  with the same price table) → $0.18 recorded, $0.0019 per question;
  input tokens also fell (689 k → 529 k) because fewer tool rounds re-send
  the prefix. Embedding calls are outside both numbers.

## What this located

The two gates the change touched are the quoting ones, and their failures
were copy discipline, not knowledge — which made them a prompt problem
rather than a model-capability one, and therefore a one-run experiment now
that the efficiency lines compare latency and cost against the previous
run. Chain 7 is that run.

# Chain 7 — quote discipline and answer language (2026-09-04)

Chain 6 left a debt: `low` effort doubled the dropped quotes (7 → 14) and
citation recall fell 0.04. A pre-delivery review of the running stack
added a second symptom the eval cannot see — **the answer's language was
following the chunks, not the question**: over five live runs of the
challenge brief's own English example question, four came back in
Portuguese, because every retrieved chunk was Portuguese. Two prompt
changes, one run each, no code outside `prompts.py`.

| Run                                        | fact_recall | cit. precision | cit. recall | refusals | unmatched quotes | answers citing nothing | latency mean | cost |
| ------------------------------------------ | ----------: | -------------: | ----------: | -------: | ---------------: | ---------------------: | -----------: | ---: |
| `20260903-010828-thinking-low` (chain 6)    |   **0.912** |          0.793 |       0.863 |      7/8 |               14 |                      3 |        5.9 s | $0.18 |
| `20260904-033017-prompt-language-quotes`    |       0.868 |      **0.818** |   **0.900** |      6/8 |               10 |                  **0** |        6.4 s | $0.18 |
| `20260904-033639-prompt-language-reminder`  |   **0.912** |          0.807 |   **0.900** |      6/8 |            **8** |                      1 |        6.4 s | **$0.14** |

## Step 1 — the rules came from reading the 14 dropped quotes

Not from intuition. The dropped passages of chain 6 fall into three
mechanisms, and each got one clause:

- **Cross-language splices (7 of 14)** — CESTARI and MN414 print the same
  content in Portuguese, English and Spanish down the same page, and the
  model walked from one column into the next mid-sentence:
  `"Para períodos de 6 meses até 9 meses sem operação, es recomendado
  llenar todo interior del reductor…"`. Rule: _where a page prints the
  same content in several languages, one passage covers one language;
  never continue a passage into its translation_.
- **Abridgement (`weg-guia-039`)** — `"As dimensões dos motores elétricos
  WEG são padronizadas ... a dimensão básica para a padronização…"`. Rule:
  _never abridged (no "..." and no omitted middle)_.
- **Transcription noise inside a line (`weg-guia-015`)** — a wrapped table
  cell copied as `de óleoparapoços`, which fails the line-wise containment
  check even though every other line matches. Rule: _the exact words,
  numbers, units and spacing, character for character_.

**Result**: dropped quotes 14 → 10, citation precision 0.793 → 0.818,
citation recall 0.863 → 0.900, and the three answers that had cited
nothing at all went to **zero**. `fact_recall` read 0.868 (−0.044), which
was **noise, not the change**: four cases lost facts against one gained,
and the largest single loss (`lb5001-001`, a relubrication table answered
`7,400` instead of `9,500` hours) reproduced correctly 4 times out of 4
against the live stack with the same prompt. Step 2 confirmed it by
returning to 0.912 with the quote rules still in place.

## Step 2 — the language rule had to come after the chunks

The first attempt stated the rule in the opening system message, ahead of
everything: _answer in the language of the user's question … the chunks are
a multilingual corpus_. It moved live adherence from 1 in 5 to 2 in 4 —
better, not fixed. The chunks are the **last thing the model reads** before
the question, and they were all Portuguese.

Restating the rule as a closing line of the context message, after the
`<chunks>` element and the tool follow-up, took live adherence to **7 of 8**
English answers on the same English-question-over-Portuguese-chunks probe,
with Portuguese questions still answered in Portuguese. The mechanism is
position, not wording: the same sentence earlier in the prompt did not
hold.

**Gates**: `fact_recall` back to 0.912 (=, chain 6), citation precision
0.807 (+0.014), citation recall 0.900 (+0.037), dropped quotes 8 (−6),
answers citing nothing 1 (−2), tool calls 5, cost **$0.14** (−$0.04 —
input caching rose from 131 k to 343 k tokens because the prompt prefix is
now longer and stable), latency +0.5 s.

## What it cost

- **One unanswerable control flipped**: `neg-008` ("Which grease should I
  use when regreasing the bearings of the CESTARI gearbox?") is answered
  with the seal-protection grease (`NLGI#2EP Texaco Multifak EP2`) instead
  of refused — refusals 7/8 → 6/8. Worth recording precisely: the refusal
  it replaced was itself **written in Portuguese for an English question**,
  so the baseline scored the gate on a reply that was wrong in another
  dimension the gate does not measure. One case on a population of eight;
  `refusal_rate` moves in steps of 0.125 and cannot resolve less.
- **`false_refusal_rate` 0.024 → 0.036**, one gated case.
- **The last answer citing nothing** is `weg-guia-018`, a table row
  (`|> 6,3<25|> 8,6<34|12|8,8|`) the model reshapes as it copies. Table
  rows are the residual failure mode of containment-verified citations, as
  Decision 0013 anticipated. A second LLM pass to repair an empty
  `references` list was weighed and **rejected**: it would spend a call on
  a 1-in-83 path and rebuild exactly the fallback that decision removed —
  a citation the model did not actually write.

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

# Section-level parents — measured before building (2026-09-02)

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

# Cross-lingual residue — measured (2026-09-02)

After chain 3, the answerable red cases are four Portuguese questions over
MN414 (`mn414-004`, `-012`, `-014`, `-016`) plus the image-only
`mn414-017` and the mirrored-page slot of `cestari-009`. Their retrieved
lists show the mechanism: **language affinity** — the Portuguese question
pulls Portuguese pages of the _other_ manuals (CESTARI, the guia) above the
English MN414 page that holds the answer. Probed against `eval_chunks`
with the question hand-translated to English (what an LLM translation step
would produce); rank of the gold page in the top 50:

| Case                   | PT question | EN question | PT + EN as a two-row MaxSim query |
| ---------------------- | ----------: | ----------: | --------------------------------: |
| `mn414-004`            |          13 |       **3** |                                 3 |
| `mn414-012`            |          25 |       **1** |                                 2 |
| `mn414-014`            |           7 |       **1** |                                 1 |
| `mn414-016` (p8 / p10) |      — / 42 |   **2** / 6 |                           12 / 14 |
| `mn414-017` (image)    |           — |          19 |                                38 |

- **Translating the question recovers 3 of the 4 answerable cases into the
  top five and half of the fourth** — ≈ +0.04 recall@5, the whole
  remaining non-image gap except the `cestari-009` slot — measured against
  the committed collection, not estimated.
- **Two query rows summed by MaxSim are worse than the English row alone**
  on `mn414-016` (12 / 14 against 2 / 6): the Portuguese row adds its
  affinity for Portuguese pages. Fusion should be RRF over two searches,
  as the [retrieval evidence](/docs/research/retrieval-strategy-evidence.md)
  already recommends, not a multi-row query.[^retrieval-evidence]
- **Cost**: one LLM call per question to translate, before the seed
  retrieval. The agent's `query_knowledge` tool could do the same
  reformulation, but chain 4 shows it does not call the tool on these
  cases — the Portuguese chunks it receives look plausible enough to
  answer from.
- **`k` recomputed from the committed run** (truncating the stored top
  five, so exact): recall@k 0.873 · 0.910 · 0.934 · 0.946 · 0.946 and
  precision@k 0.88 · 0.65 · 0.54 · 0.46 · 0.39 for k = 1…5. `k = 4` costs
  no recall and drops one page of context per question; `k = 3` loses one
  case.

[^eval-module]: Eval Harness Module — how runs are produced, thresholds, exclusion rules.

[^decision-0011]: 0011 — Ingestion, second pass: the decisions these runs evidence and the rejected alternatives.

[^golden-dataset]: Golden Dataset — case ids, notes, page semantics and canary roles.

[^corpus-findings]: Case Files Corpus Findings — the corrected CESTARI finding and measured pymupdf4llm behavior.

[^retrieval-evidence]: Retrieval Strategy Evidence — hybrid search, small-to-big and chunk-size evidence.
