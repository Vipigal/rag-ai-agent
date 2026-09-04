---
type: Playbook
title: Next Steps — Handoff from the 2026-09-02 session
description: The ordered work for the sessions after 2026-09-02 — the reading path to review what landed, the five-step story of the retrieval gains (recall@5 0.65 → 0.95) with the why behind each for the oral exam, the code-review checklist with the open design questions, the citation-excerpt problem that page-level chunks created against the challenge's reference contract, the end-to-end test procedure, and the decisions and experiments still pending.
tags: [handoff, next-steps, review, oral-exam, citations, evals]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T23:55:00Z }
verified: { by: human:vinicius, at: 2026-09-02T18:41:00Z }
sources:
  - id: findings
    resource: /evals/results/experiment-findings.md
    title: Eval Experiment Findings
  - id: decision-0011
    resource: /docs/decisions/0011-ingestion-font-repair-and-structured-chunking.md
    title: 0011 — Ingestion, second pass
  - id: ingestion-module
    resource: /src/ingestion/ingestion.md
    title: Ingestion Module
  - id: challenge
    resource: /docs/challenge.md
    title: Challenge Brief
  - id: answer-eval-spec
    resource: /specs/answer-eval-design.md
    title: Answer Eval — Design & Implementation Plan
---

# Why this concept exists

One session (2026-09-02) moved retrieval recall@5 from 0.65 to 0.95 in
seven committed runs and rewrote most of `src/ingestion/` and the
embedding side of `src/retrieval/`. The owner reviews every line before
committing, will refactor, and must be able to explain each gain to the
examiner. This playbook is the single list to walk; it is deleted or
rewritten when its items are done.

# 1. Reading path (30 minutes)

1. [Eval Experiment Findings](/evals/results/experiment-findings.md) —
   every run, what flipped, why.[^findings]
2. [Decision 0011](/docs/decisions/0011-ingestion-font-repair-and-structured-chunking.md)
   and its same-day amendment note.[^decision-0011]
3. [Ingestion Module](/src/ingestion/ingestion.md) — the rules of each
   pass as they stand now.[^ingestion-module]
4. The code, in pipeline order: `src/ingestion/pdf_font_repair.py`,
   `page_cleaning.py`, `pymupdf4llm_extractor.py`, `chunking.py`,
   `embedding_units.py`, `src/domain/services/ingestion_pipeline.py`,
   `src/retrieval/pydantic_ai_embedder.py`, `qdrant_store.py`,
   `src/api/composition.py`.

# 2. The story for the oral exam

Baseline: pymupdf4llm, fixed 1000/200 chunks, `text-embedding-3-small`,
top-5 vector search — recall@5 0.65 · hit_rate@5 0.66 · MRR@5 0.60.

| #   | Change                                                                                                                                                           | Gates after            | Why it worked (or not)                                                                                                                                                        |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Font repair** — CESTARI's fonts have no ToUnicode map; glyph ids are intact in Arial's standard order; a CMap is attached in memory before extraction. No OCR. | 0.78 · 0.80 · 0.70     | 50 of 84 pages had indexed as `�`; legible text lets the embedder work. Found by probing glyph ids, not by technique. CESTARI 0.30 → 0.85.                                    |
| 2   | **Page cleaning** — running headers, page numbers, dot leaders, pymupdf4llm markers stripped by repetition rules.                                                | 0.80 · 0.81 · 0.71     | Furniture tokens in every chunk pulled vectors toward the document's average; three marginal cases crossed the line.                                                          |
| 3   | **Structured chunker** (packing markdown blocks to 1200 chars) — later replaced.                                                                                 | 0.79 · 0.81 · 0.71     | Neutral: recall is containment and both chunkers contained the answers; losses were embedding dilution. Judged red on effort versus gain; kept as a recorded negative result. |
| 4   | **Contextualized embedding input** — `document > section` prefixed to what the embedder sees.                                                                    | 0.81 · 0.83 · 0.76     | Topic words in the vector; a ranking effect (MRR). Six lines.                                                                                                                 |
| 5   | **Page chunks with unit vectors** — the chunk is the page; its paragraphs and table rows are embedded separately as a Qdrant multivector scored by MaxSim.       | 0.86 · 0.86 · 0.79     | Decouples the granularity that retrieves well (small) from the one the model reads (large): table-value and multi-excerpt cases return. 21-line chunker.                      |
| 6   | **Multilingual embedder** — `google:gemini-embedding-001` via pydantic-ai's `Embedder`.                                                                          | **0.95 · 0.95 · 0.91** | Six of eleven Portuguese-over-English misses recovered; the axis ingestion could never touch. Costs 8× per token (cents) and a second API key.                                |

Two sentences worth saying out loud: _the largest gain came from reading
the corpus at glyph level, not from retrieval technique_; and _chunk
boundaries could not move the gates on this dataset — what moved them was
decoupling retrieval granularity from reading granularity, then the
embedder_. precision@5 (0.39) is bounded by `k`: 59 of 85 cases have one
relevant page (cap 0.20); precision@1 is 0.87 (see the findings).

# 3. Code review checklist (the owner refactors)

- `pdf_font_repair.py` (111 lines): the coverage heuristic scans
  `get_texttrace()` of every page once per document; the symbol-font
  exclusion is by name; `_ARIAL_GLYPH_ORDER` drops one Apple name. Is the
  90 % threshold worth a constant, or should the whole thing be a class?
- `page_cleaning.py` (62 lines): five regexes and two thresholds; the
  digit-blind repetition key is the accepted risk. Consider whether
  `_normalize_lines` and `_repeated_furniture` read well enough.
- `pymupdf4llm_extractor.py` (109 lines): `page_sections` and
  `_Breadcrumb` are pure and tested; the `TypeError` validation of
  pymupdf4llm's dict is verbose — a small typed parser may be cleaner.
- `chunking.py` (21 lines): as small as it gets; `Chunk.kind` and
  `metadata` are now always default — keep the extension points or drop
  them (Decision 0007 reserved them).
- ~~`ingestion_pipeline.py`: where `embedding_units` belongs~~ — **done
  2026-09-02**: moved to `src/ingestion/embedding_units.py` behind the
  `UnitSplitter` callable alias, injected at the composition root like the
  chunker; the domain pipeline only regroups vectors. The log line is
  `N chunk(s) as M unit(s)`.
- `qdrant_store.py`: multivector config, `_require_compatible`, batching
  by floats (`MAX_FLOATS_PER_UPSERT`); the query is a one-row
  multivector. Review the error messages an examiner might hit.
- `pydantic_ai_embedder.py` (17 lines) and `composition.py`: the
  `EMBEDDING_DIMENSIONS`/`EMBEDDING_BATCH_SIZES` registries and the
  `provider = model.split(":")` line; unprefixed names are rejected.
- Ports: `EmbeddingModel.embed_documents/embed_query`, `VectorStore.add`
  takes one vector group per chunk. Fakes in five test files follow.
- Tests: 146; `tests/ingestion/test_pdf_font_repair.py` reads the real
  CESTARI PDF (one-page slices) — the only tests touching `case_files/`.
- **Added 2026-09-02 (answer eval, review pending):** `src/evaluation/answers.py`
  (fact matching, per-case scoring, aggregation — ~190 lines), the
  `answers` block and per-case `answer` block in `report.py`, the
  `--answers`/`--workers` path in `run.py` (thread pool, per-case error
  capture, progress logs, compare preferring a run with answers),
  `make eval-answers`; domain `Usage` (+ `Completion.usage`,
  `Answer.has_answer`/`usage`), `PydanticAiLLM` usage mapping,
  `AgentService` summing usage and counting tool calls,
  `build_agent_service(k=)`. **Production fix found by the harness:**
  `pydantic_ai_embedder.py` now takes a factory and keeps one `Embedder`
  per thread — the shared Google client failed under concurrent per-thread
  event loops (1 in 12 calls; see the [Retrieval Module](/src/retrieval/retrieval.md)).
  197 tests, pyright zero.
- **Added 2026-09-02 (citations as quotes, Decision 0013, review pending):**
  `src/domain/services/quotes.py` (normalize + line-wise `contains`, ~20
  lines), `Reference(chunk, quote, retrieval_source)` and
  `Answer.unmatched_citations: list[str]` in `models.py`, the resolution in
  `agent_service.py` (`_unique`, `_quoted_from`; the seed fallback is
  gone), `prompts.py` (no `id` attribute; the quoting rule), the route
  returning `reference.quote`, `quotes`/`unmatched_citations` in the eval
  JSON. **Production fix found while recapturing the README:**
  `api/routes/documents.py` is now a plain `def` — as `async def` it ran the
  sync pipeline on uvicorn's loop and pydantic-ai's `embed_sync` failed
  with `this event loop is already running`, so `POST /documents` had been
  broken in Docker since the embedder switch (architecture rule 5 now says
  routes are plain `def`). 215 tests, pyright zero.
- **Added 2026-09-02 (reasoning effort, Decision 0012 §4, review pending):**
  `build_llm()`, `llm_thinking_name()`, `llm_settings()` and the
  `THINKING_EFFORTS` registry in `composition.py` (`LLM_THINKING`, default
  `low`); `PydanticAiLLM(model, settings=)` forwarding `model_settings` and
  exposing `.settings`; `Usage.reasoning_tokens`/`cost_usd` in `models.py`
  with the adapter's `_to_usage`/`_cost_usd` (genai-prices via
  `ModelResponse.cost()`, `LookupError` → 0.0); `AnswerSettings.thinking`,
  `_usage_dict`/`per_question` and the compared `_efficiency_lines`
  (`_cost_cell`, lower is green) in the eval; `run.py` builds the LLM
  through `build_llm()`. Review question: should `_cost_cell` and
  `_delta_cell` be one helper with a direction flag? 232 tests, pyright
  zero.
- **Added 2026-09-02 (error semantics, Decision 0014, review pending):**
  `domain/errors.py` (`UnreadableDocument`, `ToolRoundsExhausted`);
  `api/errors.py` (`ErrorResponse`, `ERROR_DESCRIPTIONS`,
  `error_responses()`, `register_exception_handlers` with one handler per
  class and the catch-all); `api/routes/health.py`; `validate_configuration`,
  `_settings_using`, `PROVIDER_KEYS`/`PROVIDER_PREFIXES`, `qdrant_url` in
  `composition.py`; the lifespan in `main.py`; `_open` in the extractor;
  `_extract`/`_index` in the pipeline; `MAX_REPLY_ATTEMPTS` loop in the
  LLM adapter; `IncompatibleCollection`; the route metadata and model
  examples. Review questions: is the catch-all's exception name on the
  wire acceptable for the submission, and should `ERROR_DESCRIPTIONS`
  live next to the routes instead? 261 tests, pyright zero.

# 4. Citations must be excerpts, not pages — ~~the open problem~~ done 2026-09-02

**Resolved by [Decision 0013](/docs/decisions/0013-citations-as-quotes.md)**:
the model quotes passages verbatim (no chunk id to copy), the service
resolves each quote by normalized containment over the chunks it saw and
drops what it cannot find, `references` on the wire are the quotes, and
the answer eval reports the quotes and an `unmatched_citations` count per
case. Before/after numbers in the findings (chain 5). The sketch below is
kept as the record of the design as it was posed.

The challenge's example response carries a **short excerpt** as the
reference ("the motor xxx has requires 2.3kw to operate…"), and the brief
says `references` "carries the retrieved source excerpts that ground the
answer".[^challenge] Since page-level chunks, `POST /question` returns
**whole pages** (up to 6 k characters each) as references. Retrieval
improved; the wire contract got worse. **Measured 2026-09-02** by the
answer layer (chain 4 of the findings): citation precision 0.70 (tool on)
/ 0.73 (tool off) against citation recall 0.92 / 0.91 — the model cites
about two pages per answer and one of them is not a gold page (mostly
another page of the right manual). Sketch to design and eval-gate:

- `AgentReply.citations` becomes a list of `{chunk_id, quote}` where
  `quote` is a verbatim passage of the cited chunk; the service validates
  containment (normalized whitespace/case) and drops or flags quotes that
  are not in the chunk — same structured-output mechanism as Decision 0009,
  so no regex protocol.
- `Answer.references` carries the quotes (plus chunk provenance for the
  eval); the route renders quotes, not `chunk.text`.
- The answer eval's citation gates then measure quote containment
  (deterministic) and `(document, page)` precision/recall as specified.[^answer-eval-spec]
- Prompt: instruct the model to quote the minimal passage that supports
  each claim; the seed context already renders `<chunk id document page>`.
- Decide what a valid quote is for tables (a row with its header?).

# 5. End-to-end test procedure

1. ~~The Docker stack's `chunks` collection predates multivectors~~ — done
   2026-09-02: deleted and re-ingested (164 chunks) through the fixed
   `/documents` route; the image was rebuilt (`fonttools`, `[google]`).
   The store still refuses incompatible collections with a message naming
   the fix.
2. `.env`: keep `EMBEDDING_MODEL` unset for OpenAI, or set
   `EMBEDDING_MODEL=google:gemini-embedding-001` with `GEMINI_API_KEY` for
   the measured best. Switching means re-indexing (dimensions differ).
3. `make up` (rebuilds: `fonttools` and the `[google]` extra were added),
   upload `case_files/*.pdf`, watch the log lines `repaired N font(s)`,
   `N chunk(s) as M unit(s)`.
4. Ask the challenge's question and a Portuguese one over MN414; inspect
   `references` — today they are pages (section 4).
5. `make eval` (no re-ingestion) to confirm the eval collection matches
   the committed run; `make eval-answers label=<name> workers=8` for the
   answer layer (≈ 5 minutes, LLM calls).

# 6. Decisions pending with the owner

- ~~Default embedder~~ — **decided 2026-09-02: `google:gemini-embedding-001`**
  (the examiners provide any keys needed). `GEMINI_API_KEY` is required,
  and the LLM gained a fallback to `google:gemini-3.5-flash`
  (`LLM_FALLBACK_MODEL`, the challenge's optional multi-provider item).
- ~~Decision records `0012`/`0013`~~ — **done 2026-09-02, merged into one**:
  [Decision 0012](/docs/decisions/0012-page-chunks-unit-vectors-and-providers.md) (page chunks with unit vectors, Gemini
  embeddings, LLM fallback), `status: draft` until the owner reviews.
- ~~A `src/retrieval/retrieval.md` Module concept~~ — **done 2026-09-02**:
  [Retrieval Module](/src/retrieval/retrieval.md), `status: draft` until the owner reviews;
  `ingestion.md` now points at it for the store and embedder knowledge.
- Whether `Chunk.kind`/`metadata` stay.

# 7. Experiments queued (see the findings' "What to try next")

Hybrid sparse + dense for exact identifiers; fewer or score-cut slots
(precision); mirrored-page handling for CESTARI; ~~the answer-layer eval
(spec approved, not built)~~ — **built 2026-09-02** (`make eval-answers`,
first tool-on/off pair read in the [findings](/evals/results/experiment-findings.md)).

Measured headroom per queued item (2026-09-02 probe against
`eval_chunks`, recorded in the findings under "Cross-lingual residue —
measured, not built"):

- **Query translation / cross-lingual expansion** (not on the list before):
  translating the Portuguese question to English brings 3 of the 4
  answerable MN414 reds into the top five and half of the fourth — the
  largest remaining lever. Fusion must be RRF over two searches, not a
  two-row MaxSim query (which loses one case to Portuguese-page affinity).
- **k = 4** costs no recall (recall@4 = recall@5 = 0.946) and lifts
  precision@k 0.39 → 0.46; k = 3 loses one case for 0.54. Zero code.
- **Hybrid sparse**: one case (`mn414-016`, `W1`/`W2`), partially.
- **Mirrored pages**: one slot (`cestari-009`).
- **Prompt iteration**, now measurable: ~~quotes abridged with `...` or
  spliced across the mirrored PT/ES text of CESTARI pages (14 dropped
  instead of 7)~~ — **done 2026-09-04 (findings chain 7)**: three rules read
  off the dropped passages took them to 8, citation recall 0.863 → 0.900
  and answers citing nothing 3 → 1, with `fact_recall` held at 0.912; the
  same chain pinned the **answer's language to the question's** (it had
  been following the chunks — 4 of 5 live English questions answered in
  Portuguese), which only held once the rule was restated *after* the
  chunks. Still open: the retrieval reds becoming confident wrong answers
  cited from the wrong manual (no tool call), two false refusals on
  formula/figure cases, one cross-document hallucination on a negative,
  `neg-008`'s seal-grease trap, and the table rows containment still drops
  (`weg-guia-018`).
- ~~**Latency**~~ — diagnosed and fixed 2026-09-02 (findings chain 6):
  reasoning tokens at the provider default were 85–94 % of the output;
  `LLM_THINKING=low` took the mean from 16.0 to 5.9 s and the run from
  ≈ $0.29 to $0.18. Still open: `minimal` on the eval (≈ 3 s, one wrong
  table value in the probe); ~~the quote-discipline prompt line above~~ —
  done in chain 7.

[^findings]: Eval Experiment Findings — the runs, flips, mechanisms and negative results behind sections 2 and 7.

[^decision-0011]: 0011 — Ingestion, second pass, with the amendment note pointing at the page-chunk shape.

[^ingestion-module]: Ingestion Module — the current rules of every pass.

[^challenge]: Challenge Brief — the `references` contract and its excerpt example.

[^answer-eval-spec]: Answer Eval — Design & Implementation Plan — citation precision/recall gates over `(document, page)`.
