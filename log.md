# Bundle Update Log

## 2026-09-04

- **Update**: two prompt rules, no new code. Quote discipline — never
  abridge a passage, never continue one into the translation printed beside
  it on a mirrored page, copy words, numbers, units and spacing exactly —
  was read off the passages the low reasoning effort had cost. A third rule
  pins the answer's language to the question's, and only held once it was
  restated *after* the chunks, as the last thing before the user turn.
  Dropped quotes 14 → 8, citation precision 0.79 → 0.81, citation recall
  0.86 → 0.90, fact recall held at 0.91, run cost $0.18 → $0.14. Recorded
  as chain 7 of the
  [Eval Experiment Findings](/evals/results/experiment-findings.md), with
  an amendment note on
  [Decision 0013](/docs/decisions/0013-citations-as-quotes.md); the README
  examples were recaptured from the running stack.

## 2026-09-02

- **Creation**: [Decision 0014](/docs/decisions/0014-error-semantics-and-startup-validation.md)
  — every API error is one `{"detail": "…"}` sentence whose status says who
  is at fault: 422 the request, 502 a provider or an unusable reply, 503 a
  dependency or the configuration, 500 only as a named catch-all. Adapters
  translate infrastructure failures into domain errors and `api/errors.py`
  is the only place that knows statuses. Configuration and the vector store
  are validated in the FastAPI lifespan, so a wrong `.env` fails `make up`
  rather than the first request; `GET /health` reports readiness; every
  route and model carries summaries, descriptions, real examples and its
  declared error statuses.
- **Update**: the LLM reasons at `low` effort by default (`LLM_THINKING`),
  wired at the composition root and shared by the route and the eval runner.
  The diagnosis came before the fix: latency correlated 0.92 with output
  tokens, and reasoning tokens were 85–94 % of the output at the provider
  default. Mean answer time 16.0 → 5.9 s, run cost ≈ $0.29 → $0.18. `Usage`
  gained `reasoning_tokens` and `cost_usd`, and the eval's efficiency lines
  now compare latency and cost against the previous run.
- **Creation**: [Decision 0013](/docs/decisions/0013-citations-as-quotes.md)
  — citations are passages quoted verbatim, not chunk ids. The service
  resolves each quote by normalized line-wise containment over the chunks
  the model saw, drops what it cannot find and counts it, and
  `POST /question` returns the quotes as `references`. Citation precision
  0.70 → 0.78.
- **Update**: the eval harness gained its **answer layer** —
  `make eval-answers` runs every case through `AgentService.answer()` in a
  worker pool and scores fact recall, citation precision/recall and refusal
  rate deterministically, with latency, tokens and priced cost per run.
  There is no LLM judge: the per-case JSON is written to be read by hand.
  Recorded in the [Eval Harness Module](/src/evaluation/evaluation.md).
- **Creation**: [Decision 0012](/docs/decisions/0012-page-chunks-unit-vectors-and-providers.md)
  — the chunk is the page and the vector is the unit (Qdrant multivector
  scored by MaxSim, recall@5 0.81 → 0.86); the embedder is
  `google:gemini-embedding-001` (0.86 → **0.95**, six of eleven
  cross-lingual misses recovered); the LLM falls back from `gpt-5-mini` to
  `gemini-3.5-flash`. Structured packing, section-level parents,
  `text-embedding-3-large` and the other Gemini flash models were measured
  or reasoned out.
- **Creation**: [Retrieval Module](/src/retrieval/retrieval.md) — the
  embedder adapter (task types, per-provider batching, the dimension
  registry), the multivector store (point shape, the upsert bound and the
  32 MB reason behind it, incompatible collections refused with the fix
  named), the retriever, and how to test all of it without Docker.
- **Creation**: [Decision 0011](/docs/decisions/0011-ingestion-font-repair-and-structured-chunking.md)
  — the ingestion second pass, one eval run per step: **font repair**
  (fonts lacking a ToUnicode map get a CMap from Arial's standard glyph
  order, no OCR) took recall@5 0.65 → 0.78 with CESTARI 0.30 → 0.85; **page
  cleaning** → 0.80; **structure-aware chunking** → 0.79, judged a red
  experiment on effort versus gain and kept as a recorded negative result;
  **contextualized embedding input** → 0.81. OCR, `use_glyphs`, standalone
  table chunks and character overlap were measured and rejected.
- **Creation**: [Eval Experiment Findings](/evals/results/experiment-findings.md)
  — co-located with the results JSONs it interprets: every run, which cases
  flipped and why, the negative results, and the probes taken before
  building anything (section-level parents, the cross-lingual residue).
- **Creation**: the repo-root `README.md` — the curated five-minute path: a
  Docker-only quickstart, the API contract with real captured examples, a
  map of the two flows, the eval-first method with a living scoreboard, and
  the configuration table.
- **Creation**: [Project Glossary](/docs/glossary.md) — one word per
  concept across code, bundle and evals, with the words to avoid: **chunk**
  for what the model reads, **gold excerpt** for a transcribed truth
  passage, **reply** vs **answer** vs **reference**.
- **Creation**: [Decision 0010](/docs/decisions/0010-developer-ux-setup-path.md)
  — the setup path is a product surface: a committed `.env.example` with
  every knob, a guarded Makefile whose every failure names the next command,
  `make install` with a Python 3.12 floor, `make up` in the foreground
  behind a Qdrant healthcheck, and per-file ingestion progress logs so the
  ~60 s corpus upload is visibly alive. Suite and pyright verified green on
  CPython 3.12, 3.13 and 3.14.
- **Creation**: [Decision 0009](/docs/decisions/0009-structured-reply-function-tools.md)
  — the agent's final answer becomes a provider-enforced structured output,
  replacing the `[i]`/`NO_ANSWER` text protocol whose regex parsing failed
  probabilistically; tools become Python functions whose schema the adapter
  derives; retrieved chunks reach the model as an XML-rendered system
  message rather than inside the user turn.
- **Update** (moves out of the repo root): the OKF specification and the
  challenge brief moved into `docs/`. The root keeps `index.md`, `log.md`,
  `README.md`, `CLAUDE.md` and the build files.

## 2026-09-01

- **Creation**: [LLM Module](/src/llm/llm.md) — what the adapter's code
  cannot say: why the question route must stay a sync `def`, that `openai:`
  resolves to the Responses API, message grouping and `tool_name`-by-id
  resolution, which exceptions reach the edge as 502 versus 500, and the
  `FunctionModel` testing recipe.
- **Update**: `POST /question` landed — the domain LLM vocabulary and port,
  `AgentService` with its bounded `query_knowledge` loop, the deliberate
  prompt in `src/domain/services/prompts.py`, the PydanticAI direct adapter
  and the thin sync route, all TDD-first.
- **Creation**: [Decision 0008](/docs/decisions/0008-question-agent-baseline.md)
  — the LLM port's first adapter is PydanticAI's direct API (caller-owned
  single call, `FallbackModel` path open); `references` are the chunks the
  model actually cites; the eval harness consumes `AgentService.answer()`
  in-process.
- **Update**: the harness package became `src/evaluation/` (data stays in
  `/evals`), the per-case results JSON became human-readable, and a
  **typecheck gate** joined the
  [Development Workflow](/docs/development-workflow.md) — pyright
  `standard`, zero errors — with the 21 pre-existing errors fixed by type
  guards and defensive validation, never blanket ignores. A root Makefile
  replaced loose terminal snippets as the eval DX.
- **Update**: [Development Workflow](/docs/development-workflow.md) records
  the owner's norm as its first working agreement: **agents never commit**.
  The owner reviews every change in the editor and makes every commit.
- **Creation**: [Eval Harness Module](/src/evaluation/evaluation.md) and
  the first committed baseline run (recall@5 0.65 · hit_rate@5 0.66 ·
  MRR@5 0.60), with the finding that CESTARI's CMap corruption is
  *partial* — early pages legible, middle pages `�`.
- **Creation**: [LLM Adapter Library Evidence](/docs/research/llm-adapter-library-evidence.md)
  — primary-source comparison of the candidate adapter libraries against
  the domain-owned tool loop, with measured dependency and import weight.

## 2026-08-31

- **Creation**: [Ingestion Module](/src/ingestion/ingestion.md) — the first
  co-located module concept: breadcrumb carry-forward and its stale-level
  caveat, CESTARI's `�` indexed on purpose so the evals capture the failure
  before the fix lands, and the first full-corpus numbers.
- **Update**: `POST /documents` landed per
  [Decision 0007](/docs/decisions/0007-naive-ingestion-baseline.md) —
  domain entities, ports and service plus the four baseline adapters, all
  TDD, verified end to end through the container with the full corpus.
- **Creation**: [Golden Dataset](/evals/golden/golden-dataset.md) and the
  dataset itself — 93 hand-authored cases over the four corpus PDFs,
  including 8 unanswerable controls. Page-numbering semantics, transcription
  caveats and the rules a case is written by live in the concept; the YAML
  files are comment-free.
- **Creation**: [Decision 0007](/docs/decisions/0007-naive-ingestion-baseline.md)
  — a deliberately naive ingestion baseline (no OCR, fixed-size chunking,
  `text-embedding-3-small`) with deterministic content-addressed ids for
  idempotent re-ingestion, extension points on the persisted chunk, and no
  relational database.
- **Creation**: [Decision 0006](/docs/decisions/0006-eval-metrics-and-golden-dataset.md)
  — deterministic metrics gate experiments while LLM-judged ones only
  diagnose; retrieval ground truth is verbatim excerpts plus (document,
  page), never chunk ids, so it survives any change in chunking.
- **Creation**: [Decision 0005](/docs/decisions/0005-retrieval-architecture.md)
  — the read side splits into a persistence port (`VectorStore`) and a
  strategy port (`Retriever`) so retrieval experiments are adapter swaps;
  answering is dual-path, a deterministic seed retrieval plus a
  `query_knowledge` tool over the same retriever.
- **Creation**: [System Architecture](/docs/architecture.md) and
  [Decision 0004](/docs/decisions/0004-ports-and-adapters-lite.md) — a
  minimal hexagonal architecture: a framework-free domain, adapters per
  pipeline stage, ports only at real seams, one composition root, and the
  supremacy clause — the architecture yields to the evals.
- **Creation**: [Decision 0003](/docs/decisions/0003-toolchain-plain-pip-docker-first.md)
  — classic pip and venv with pinned requirements, docker-first delivery.
  First code landed with it: the `src/api` scaffold, built test-first.
- **Update**: research concepts moved into their own area as a backlink
  source, and the [Authoring Guide](/docs/authoring-guide.md) gained the
  rule that every new concept needs the owner's approval first, plus the
  norm that code and configuration files carry no comments — what would
  have been a comment becomes a co-located concept.
- **Creation**: [Case Files Corpus Findings](/docs/research/case-files-corpus-findings.md)
  and [Retrieval Strategy Evidence](/docs/research/retrieval-strategy-evidence.md)
  — the empirical survey of the four corpus PDFs, and cited external
  evidence on hybrid search, small-to-big retrieval, chunk sizing and PDF
  parsers.
- **Update**: the bundle was re-rooted at the repo root so module knowledge
  can sit next to module code —
  [Decision 0002](/docs/decisions/0002-colocate-docs-with-code.md),
  superseding [Decision 0001](/docs/decisions/0001-okf-bundle-at-docs.md).
- **Initialization**: the knowledge bundle was established with the
  [Golden Rules](/docs/golden-rules.md),
  [Development Workflow](/docs/development-workflow.md) and
  [Authoring Guide](/docs/authoring-guide.md).
