---
type: Spec
title: Answer Eval — Design & Implementation Plan
description: Approved design for the harness's answer layer — the minimal increment that makes the tool-on/off and model-choice evals runnable. Deterministic gates (fact recall, citation precision/recall, refusal rate) and efficiency (end-to-end latency, token usage) over AgentService.answer() in-process behind an opt-in --answers flag with a thread-pool of workers; the per-case results JSON doubles as the owner's judging panel in place of an LLM judge. Records the measured cost analysis, the fact-normalization rules, the error semantics, the Usage/has_answer additions to the domain, and the ordered TDD plan.
tags: [evals, harness, answers, citations, facts, refusal, usage, cost, design, spec]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T23:55:00Z }
sources:
  - id: harness-spec
    resource: /specs/eval-harness-design.md
    title: Eval Harness — Design & Implementation Plan
  - id: eval-spec
    resource: /specs/eval-structure-design.md
    title: Eval Structure & Golden Dataset — Design
  - id: decision-0006
    resource: /docs/decisions/0006-eval-metrics-and-golden-dataset.md
    title: 0006 — Eval metrics and golden-dataset shape
  - id: decision-0008
    resource: /docs/decisions/0008-question-agent-baseline.md
    title: 0008 — Question agent baseline
  - id: decision-0009
    resource: /docs/decisions/0009-structured-reply-function-tools.md
    title: 0009 — Structured agent reply, function-derived tools, chunk ids as citation handles
  - id: agent-spec
    resource: /specs/question-agent-design.md
    title: Question Agent — Design & Implementation Plan
  - id: golden-dataset
    resource: /evals/golden/golden-dataset.md
    title: Golden Dataset
  - id: baseline
    resource: /evals/results/20260901-190240-baseline.json
    title: Retrieval baseline run (2026-09-01)
  - id: openai-pricing
    resource: https://developers.openai.com/api/docs/pricing
    title: OpenAI API pricing (consulted 2026-09-02)
---

# Goal

Make the answer layer of the eval runnable with the least machinery that
still produces before/after evidence: run `AgentService.answer()` over
the [golden dataset](/evals/golden/golden-dataset.md), compute the
deterministic answer gates [Decision
0006](/docs/decisions/0006-eval-metrics-and-golden-dataset.md) already
defines, and log what each question cost in time and tokens — so the
tool-on/off question from [Decision
0005](/docs/decisions/0005-retrieval-architecture.md), the prompt
iteration the live smoke demanded,[^agent-spec] and the choice of the
default `LLM_MODEL` are all decided on measured numbers. Serves
_Functionality_ and _LLM Use_ directly, _Retrieval_ through citation
scoring ([Golden Rules](/docs/golden-rules.md)). This spec doubles as the
implementation plan (house pattern): the ordered TDD steps at the end are
the work.

# Scope

**In:** the `--answers` opt-in path of the existing runner with a
thread-pool of workers, the deterministic answer metrics
(`fact_recall`, `citation_precision`, `citation_recall`,
`refusal_rate`), the diagnostics (`false_refusal_rate`, `errors`,
`requires_image` row), efficiency (end-to-end latency, token usage), the
domain additions that make usage and the refusal signal visible to the
harness (`Usage`, `Answer.has_answer`), the results JSON and console
additions, `make eval-answers`, the first tool-on/off runs, and the
measured cost analysis.

**Out, deliberately (owner decision, 2026-09-01 — time-boxed challenge):**
the LLM judge for correctness/faithfulness — **the owner is the judge**,
reading the per-case JSON (answer next to `reference_answer`) for the
cases the gates paint red; `$` in the report (price tables rot — tokens ×
the current price is one multiplication); reasoning tokens as a separate
field (`output_tokens` already includes them for reasoning models);
dataset additions (owner-curated — the cross-lingual refusal case from the
live smoke[^agent-spec] is the first candidate). The judge returns to the
table only if red cases become disputable ("right, but phrased
differently"), which Decision 0006 already classifies as diagnostic
territory.[^decision-0006]

# Design decisions

1. **Answer evaluation is opt-in (`--answers`).** Without the flag the
   runner's behavior and payload are byte-identical to today's, so
   chunking/embedding experiments keep paying ~1 minute and ~$0, and the
   committed retrieval baselines stay comparable. With the flag, **all 93
   cases** are answered — the 8 `unanswerable` cases enter the per-case
   list with retrieval fields `null`, because they gate the answer layer.
2. **In-process, through the domain, in a thread pool.** The harness calls
   `AgentService.answer(question) -> Answer` directly, as Decision 0008
   fixed,[^decision-0008] via `build_agent_service()` over the eval
   collection. Concurrency is a `ThreadPoolExecutor(max_workers=N)`
   (`--workers`, default 4; `executor.map` preserves dataset order). It is
   the same mechanism FastAPI uses for the sync route — worker threads
   blocking on I/O — with none of the surrounding machinery (no server,
   no ingestion into the API collection, no string parsing of
   references). Safety was verified on 2026-09-02 against the installed
   `pydantic-ai-slim` 2.37.0: `model_request_sync` creates or reuses a
   per-thread event loop (`_utils.get_event_loop`), `infer_model` is
   uncached so every `complete()` builds its own model, provider and
   httpx client, and `AgentService` keeps all per-question state in
   locals — a spike of 8 concurrent `PydanticAiLLM.complete()` calls
   through the real adapter returned 8 correct structured replies in
   7.9 s total (≈ 4 s each sequentially). The bound is now the provider's
   rate limit: a 429 surfaces as `ModelHTTPError`, is recorded as a case
   `error`, and shows in the report as `errors N` — the signal to lower
   `--workers`. Retrieval scoring stays sequential (≈ 28 s) so retrieval
   latency remains comparable with earlier runs. `workers` is recorded
   in the run info because per-case latency is measured under
   concurrency.
3. **An exception in one case never kills the run.** `answer()` can raise
   — the agent raises `RuntimeError` when the model keeps requesting
   tools past the cap,[^decision-0009] providers raise on 429/5xx. The
   runner catches `Exception` per case, records `error: str` in that
   case's block, and scores it as the **worst outcome**: not answered,
   `fact_recall` 0, citations 0/0, and — on an `unanswerable` case — not
   a refusal. Errors are counted in `answers.diagnostics.errors` and
   painted red when > 0.
4. **The refusal signal is structural.** `AgentReply.has_answer` exists
   since Decision 0009[^decision-0009] but was dropped on the way to
   `Answer`; `Answer` gains `has_answer: bool = True` so the harness
   never infers a refusal from empty references. Same name, no new
   concept.
5. **Usage is a domain value with industry names.** `Usage(requests,
   tool_calls, input_tokens, cache_read_tokens, output_tokens)` — the
   field names of pydantic-ai's `RunUsage`/`RequestUsage` and OpenAI's
   usage object. `Completion.usage` is what one provider call cost (the
   adapter copies it from `ModelResponse.usage`); `Answer.usage` is the
   sum over the tool loop plus the number of dispatched tool calls.
   Defaults are all zero so existing fakes and tests compile unchanged.
   `cache_read_tokens` is carried because OpenAI's automatic prompt
   caching discounts repeated prefixes by 90 % on the gpt-5 family, and
   within a tool loop every call after the first repeats the previous
   prompt — without it the tool-on cost would be overstated.
6. **Gates are deterministic and cheap; the human diagnoses.** The four
   gates follow Decision 0006 verbatim.[^decision-0006] The per-case
   block carries everything a reader needs to judge correctness without
   opening the YAML: question, `answer`, `reference_answer`, each
   expected fact with its verdict, each cited `(document, page)` with
   whether it is gold, usage and latency. Reading order for the owner:
   filter red gates → read those cases → open the YAML only when the
   case itself looks wrong.
7. **One `k` per run.** The agent's seed and tool retrieval use
   `RETRIEVAL_K`; the retrieval gates use `--k`. The runner passes its
   `--k` into the agent (`build_agent_service(..., k=)`), so a run's
   retrieval and answer numbers describe the same system; the value is
   recorded once in the run info.

# Contracts

Domain additions (`src/domain/models.py`; frozen, stdlib-only):

```python
@dataclass(frozen=True)
class Usage:
    requests: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage": ...   # field-wise sum

@dataclass(frozen=True)
class Completion:
    message: Message
    reply: AgentReply | None
    usage: Usage = Usage()

@dataclass(frozen=True)
class Answer:
    text: str
    references: list[RetrievedChunk]
    has_answer: bool = True
    usage: Usage = Usage()
```

Adapter: `PydanticAiLLM.complete` sets `usage=Usage(requests=1,
input_tokens=u.input_tokens, cache_read_tokens=u.cache_read_tokens,
output_tokens=u.output_tokens)` from `response.usage`. Service:
`AgentService.answer` sums every `completion.usage`, adds one
`tool_calls` per dispatched call, and propagates `reply.has_answer`.

Composition: `build_agent_service(retriever, llm, k: int | None = None)`
— `k` overrides `RETRIEVAL_K` (the runner passes `--k`); the production
`get_agent_service()` keeps calling it without `k`.

Harness types (`src/evaluation/answers.py`):

```python
@dataclass(frozen=True)
class AnswerRun:
    answer: Answer | None          # None when the case errored
    latency_ms: float
    error: str | None = None

@dataclass(frozen=True)
class AnswerResult:
    case_id: str
    has_answer: bool
    fact_hits: tuple[bool, ...]            # one per expected_fact
    fact_recall: float | None              # None when the case has no facts
    cited: tuple[tuple[str, int], ...]     # ordered unique (document, page)
    cited_in_gold: tuple[bool, ...]        # parallel to cited
    citation_precision: float | None       # None for unanswerable cases
    citation_recall: float | None
```

# Answer metrics

Over the case populations the retrieval layer already
defines:[^harness-spec] **gated** = answerable ∧ ¬`requires_image` (83);
**image diagnostic** (2); **unanswerable** (8). Per Decision 0006:[^decision-0006]

| Metric | Population | Definition |
| --- | --- | --- |
| `fact_recall` (gate) | gated cases with `expected_facts` (57) | per case, fraction of expected facts found in `answer.text` (matching below); refusal or error ⇒ 0; mean over the population |
| `citation_precision` (gate) | gated (83) | `|cited ∩ gold| / |cited|` where `cited` = unique `(chunk.filename, chunk.page)` of `answer.references` and `gold` = every excerpt's and alternate's `(document, page)`; empty `cited` ⇒ 0 |
| `citation_recall` (gate) | gated (83) | fraction of excerpt slots whose `(document, page)` — primary or any alternate — appears in `cited` |
| `refusal_rate` (gate) | unanswerable (8) | fraction with `has_answer == False` (a genuine structured refusal; an error is not one) |
| `false_refusal_rate` (diagnostic) | gated (83) | fraction with `has_answer == False` |
| `errors` (diagnostic) | all 93 | count of cases whose `answer()` raised |
| `requires_image` (diagnostic row) | image (2) | `fact_recall`, `citation_precision`, `citation_recall` |

Slices: `fact_recall`, `citation_precision`, `citation_recall`,
`false_refusal_rate` by `persona`, `language`, `category`, `document`
over the gated population — the same four dimensions and the same
document-slice reading (CESTARI, cross-lingual) as retrieval.
Unanswerable cases have no document and appear only in `refusal_rate`.

Efficiency, every run: end-to-end latency (mean, p95, measured under
`workers` concurrency) and usage — run totals of `requests`,
`tool_calls`, `input_tokens`, `cache_read_tokens`, `output_tokens`, plus
per-question means of `input_tokens`, `output_tokens`, `requests`. The
per-question means are the column that decides the default model.

# Fact matching semantics

Both sides — `answer.text` and each expected fact — pass through the
same `normalize`:

1. casefold;
2. delete `.` and `,` sitting between two digits (`(?<=\d)[.,](?=\d)`),
   so `7,36` ≡ `7.36` ≡ `736`, and `1.800` ≡ `1,800` ≡ `1800` — the
   pt-BR decimal comma and both digit-grouping conventions collapse
   without the harness having to guess which one the author meant;
3. delete whitespace between a digit and a following letter, `%` or `°`
   (`2,2 kW` ≡ `2,2kW`, `4 %` ≡ `4%`);
4. collapse whitespace.

`contains_fact(answer, fact)` then searches the normalized fact in the
normalized answer with **boundaries**: `(?<!\d)`/`(?!\d)` when the fact
starts/ends with a digit, `(?<!\w)`/`(?!\w)` otherwise. So `127` matches
`127 V`, `127V` and `127/220 V` but not `1270 V`; `4%` matches `4 %` but
not `14%`; `IP55` matches `ip55.` but not `IP555`. Known limit, accepted:
step 2 makes `7,36` also match a bare `736`; the golden dataset's `notes`
flag such traps and the owner reads red — not green — cases. Pinned by a
table test.

# Runner

```
make eval-answers label=<label> [k=5] [threshold=0.6] [workers=4] [args='--no-compare']
```

expands to `make eval … args="--answers --workers $(workers) $(args)"`;
the tool toggle and model come from `.env` (`QUERY_KNOWLEDGE_ENABLED`,
`LLM_MODEL`, `AGENT_MAX_TOOL_ROUNDS`), which `make eval` sources. The
orchestration in `run.py` gains one optional collaborator, `answerer:
Callable[[str], Answer] | None`, and `workers: int`:

1. Load and validate the dataset; ingest if the eval collection is empty
   (unchanged).
2. Retrieval scoring, sequential, over non-unanswerable cases
   (unchanged).
3. If `answerer` is set: `ThreadPoolExecutor(max_workers=workers).map`
   over **all** cases; each task times `answerer(case.question)`,
   catching `Exception` into `AnswerRun(error=repr(exc))`.
4. Score, aggregate, resolve the compare target, render, write JSON
   (unchanged shape plus the `answers` block).

`main()` builds `PydanticAiLLM(llm_model_name())` and
`build_agent_service(VectorRetriever(get_embedder(), store), llm,
k=args.k)` only when `--answers` is given. The run info records
`llm_model`, `tool_enabled`, `max_tool_rounds`, `workers`.

**Compare resolution**: with `--answers`, the default target is the most
recent result with the same `k`/threshold **that also carries an
`answers` block**; if none exists, the most recent comparable
retrieval-only run is used for the retrieval deltas and a yellow notice
replaces the answer deltas. Without `--answers` the rule is unchanged.

# Console report

Appended after the retrieval sections; same delta and coloring rules
(deltas colored, absolutes not; latency and tokens uncolored):

```
ANSWER GATES (83 cases)  fact_recall(57)  cit_precision    cit_recall       refusal_rate(8)
overall                  0.72 (+0.05)     0.61 (=)         0.79 (-0.02)     0.88 (+0.13)

ANSWERS BY DOCUMENT      cases   fact_recall      cit_precision    cit_recall
LB5001.pdf                   8   0.75 (=)         0.70 (+0.10)     0.88 (=)
MN414_0224.pdf              16   0.58 (+0.08)     0.55 (=)         0.62 (-0.06)
WEG-CESTARI IOM             20   0.30 (=)         0.41 (=)         0.35 (=)
WEG guia 50032749           39   0.86 (+0.05)     0.68 (=)         0.92 (=)

ANSWER DIAG   false_refusal 0.06 (+0.01) · errors 0 · requires_image (2): fact_recall 0.00 (=)
EFFICIENCY    answer latency: mean 6.8 s · p95 14.2 s (4 workers) · llm calls 158 · tool calls 65
              tokens: in 498k (cached 121k) · out 112k · per question in 5.4k / out 1.2k
```

`errors` is red when > 0. When the compare target has no `answers` block
the four gate cells render without deltas and the line
`previous run has no answer layer — answer deltas omitted` appears in
yellow.

# Results JSON

Additions to the payload defined by the harness spec.[^harness-spec]
`"answers": null` when the run did not pass `--answers`; otherwise:

```json
{
  "run": { "...unchanged...", "cases": { "total": 93, "gated": 83, "image_diagnostic": 2, "unanswerable_excluded": 8, "answered": 93 } },
  "answers": {
    "llm_model": "openai:gpt-5-mini",
    "tool_enabled": true,
    "max_tool_rounds": 3,
    "workers": 4,
    "gates": {
      "fact_recall": 0.0, "fact_cases": 57,
      "citation_precision": 0.0, "citation_recall": 0.0,
      "refusal_rate": 0.0, "unanswerable_cases": 8
    },
    "diagnostics": {
      "false_refusal_rate": 0.0,
      "errors": 0,
      "requires_image": { "fact_recall": 0.0, "citation_precision": 0.0, "citation_recall": 0.0 }
    },
    "efficiency": {
      "latency_ms": { "mean": 0.0, "p95": 0.0 },
      "usage": { "requests": 0, "tool_calls": 0, "input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0 },
      "per_question": { "requests": 0.0, "input_tokens": 0.0, "output_tokens": 0.0 }
    },
    "slices": { "persona": {}, "language": {}, "category": {}, "document": {} }
  },
  "cases": [
    {
      "id": "weg-guia-012", "question": "…", "category": "…", "persona": "…", "language": "…", "notes": "…",
      "recall": 1.0, "hit": true, "reciprocal_rank": 0.5, "precision": 0.5, "first_relevant_rank": 2, "latency_ms": 38.2,
      "gold_excerpts": ["…unchanged…"], "retrieved": ["…unchanged…"],
      "answer": {
        "text": "O grau de proteção indicado é IP55.",
        "has_answer": true,
        "reference_answer": "…",
        "facts": [{ "fact": "IP55", "found": true }],
        "fact_recall": 1.0,
        "cited": [{ "document": "…", "page": 34, "in_gold": true, "source": "seed" }],
        "citation_precision": 1.0,
        "citation_recall": 1.0,
        "latency_ms": 6821.4,
        "usage": { "requests": 2, "tool_calls": 1, "input_tokens": 6412, "cache_read_tokens": 2304, "output_tokens": 812 },
        "error": null
      }
    }
  ]
}
```

Slice blocks carry `cases`, `fact_recall`, `citation_precision`,
`citation_recall`, `false_refusal_rate`. For an `unanswerable` case the
retrieval fields (`recall` … `retrieved`) are `null`, `gold_excerpts` is
`[]`, and `answer.facts` is `[]` with `fact_recall`/`citation_*` `null`.
An errored case has `"answer": { "text": null, "has_answer": false, …,
"error": "RuntimeError(...)" }`. Rounding as today (scores 3 decimals,
latency 1).

# Cost analysis (measured 2026-09-02)

Token counts measured with `tiktoken` (`o200k_base`) over the real
`eval_chunks` collection (570 chunks) and the current prompt
templates:[^decision-0009]

| Component | Tokens |
| --- | --- |
| Chunk text | mean 230 · median 230 · p95 476 · max 845 (WEG guia 268, MN414 257, LB5001 222, CESTARI 157) |
| XML rendering overhead per chunk (id, document, page, sections) | ≈ 100 |
| 5-chunk rendered context | ≈ 1 700–2 200 |
| `SYSTEM_PROMPT` | 224 |
| Question | mean 22 |
| **First call, input** | **≈ 2 300** (with tool + output schema) |
| Each tool round adds to the next call's input | ≈ 1 800 (tool result ≈ 1 750 + tool-call turn), and every later call re-sends the whole conversation |
| Visible output (structured reply: answer ≈ 60 + UUID citations ≈ 25 each) | ≈ 140 |
| Reasoning tokens (gpt-5 family, default effort) | ≈ 300–1 500 per call — **the dominant uncertainty**; 600 assumed below |

Prices per 1M tokens (input / output), OpenAI pricing page consulted
2026-09-02:[^openai-pricing] gpt-5 $1.25 / $10 · gpt-5-mini $0.25 / $2 ·
gpt-5-nano $0.05 / $0.40 · gpt-5.4-mini $0.75 / $4.50 · gpt-4.1-mini
$0.40 / $1.60 · gpt-4o-mini $0.15 / $0.60 · text-embedding-3-small $0.02.
Cached input is 10 % of the input price on the gpt-5 family.

Estimated cost of **one 93-question run**, three scenarios — tool-off (1
call per case), tool-on typical (40 % one call, 50 % two, 10 % three),
tool-on worst (four calls on every case) — without the caching discount:

| Model | tool-off | tool-on typical | tool-on worst | Wall clock, sequential |
| --- | --- | --- | --- | --- |
| gpt-5-mini (current default) | $0.19 | $0.35 | $0.99 | 8–11 min |
| gpt-5 | $0.96 | $1.73 | $4.90 | 10–15 min |
| gpt-5-nano | $0.04 | $0.07 | $0.20 | 5–8 min |
| gpt-5.4-mini | $0.47 | $0.87 | $2.60 | 8–11 min |
| gpt-4.1-mini (no reasoning) | $0.11 | $0.23 | $0.80 | 4–6 min |
| gpt-4o-mini (no reasoning) | $0.04 | $0.09 | $0.30 | 4–6 min |

- Embeddings: ≈ $0.0001 per run (queries); `make eval-fresh` re-ingestion
  ≈ 131k tokens ≈ $0.003. `make test` costs $0 (fakes). Retrieval-only
  eval: ≈ 1 min, ≈ $0.
- Prompt caching cuts the tool-on marginal cost by roughly 30–40 % in
  practice (the repeated prefix is ≥ 1 024 tokens from the first call).
- With `--workers 4` the wall clock divides by ≈ 4 (2–3 min for
  gpt-5-mini); at 16 workers the run is rate-limit bound, under a minute
  on a tier that allows it.
- A sweep of 4 models × tool on/off ≈ $3–4. Money is not the constraint;
  wall clock and rate limits are — hence the workers.
- The report prints measured usage, so this table is superseded by the
  first run. That is its purpose.

# Testing strategy

- `answers.py` is pure: table tests for `normalize`/`contains_fact`;
  `evaluate_answer` over fabricated cases and `Answer`s (facts found /
  missing / refused / errored; citations with alternates; empty
  references; unanswerable with and without refusal); aggregation with
  the three populations, slices, usage sums and per-question means.
- Domain: `Usage.__add__`; `AgentService` sums usage across a scripted
  tool loop and counts dispatched tool calls; `has_answer=False`
  propagates. Adapter: `Completion.usage` mapped from a `ModelResponse`
  carrying `RequestUsage` (through `FunctionModel` if it passes usage
  through — verify in step 1; otherwise test the mapping on a
  `ModelResponse` directly).
- `report.py`: golden-file test of an `--answers` payload; **regression
  test that a retrieval-only payload is unchanged**; console rendering
  with and without a comparable answer run; `errors` painted red.
- `run.py` with fakes: `answerer=None` reproduces today's behavior;
  a fake answerer records every question including unanswerable ones;
  a raising fake yields an `error` block and the run completes; `workers`
  > 1 preserves dataset order; compare prefers a target with `answers`.
- Typecheck gate: pyright `standard`, zero errors; fakes satisfy the
  `LLM`/`Retriever` Protocols in full.
- The real validation is the first `agent-tool-on` / `agent-tool-off`
  pair (step 8).

# Implementation plan (TDD, in order)

Each step starts with its failing test; no production code without one.
`Makefile` and `src/evaluation/evaluation.md` carry uncommitted edits
from a parallel session — rebase onto the working tree, touch only what a
step names.

1. **Domain `Usage` + `has_answer`** — `Usage` with field-wise `__add__`
   and zero defaults; `Completion.usage`, `Answer.has_answer`,
   `Answer.usage`. Adapter maps `response.usage` (requests = 1).
   `AgentService` sums completions, counts dispatched tool calls,
   propagates `reply.has_answer`. `build_agent_service` gains `k: int |
   None = None`. Existing tests stay green (defaults); `make typecheck`
   clean.
2. **`answers.py` — fact matching** — the normalization table above:
   decimal comma, digit grouping, unit spacing, `%`, digit and word
   boundaries, casefold, the accepted `736` false positive documented
   by a test that asserts it (so a future tightening is deliberate).
3. **`answers.py` — per case** — `evaluate_answer(case, run) ->
   AnswerResult`: fact hits and recall (None without facts), `cited`
   deduplicated in reference order, precision/recall against
   gold ∪ alternates, refusal ⇒ zeros, unanswerable ⇒ citation `None`,
   error ⇒ worst outcome.
4. **`answers.py` — aggregation** — `aggregate_answers(...)`: gates over
   the gated population, `fact_recall` over the facts subpopulation with
   its count, `refusal_rate` over unanswerable, `false_refusal_rate`,
   `errors`, image row, the four slices, usage totals and per-question
   means, latency mean/p95.
5. **`report.py`** — payload `answers` block and per-case `answer` block
   (golden-file); retrieval-only payload regression; console sections
   `ANSWER GATES`, `ANSWERS BY DOCUMENT`, `ANSWER DIAG`, efficiency
   lines; deltas only against a target carrying `answers`, yellow notice
   otherwise; red `errors`.
6. **`run.py`** — optional `answerer` and `workers`; all cases answered in
   a thread pool with per-case exception capture and latency;
   unanswerable cases enter the case list with `null` retrieval fields;
   `--answers` / `--workers` flags; compare resolution prefers a target
   with `answers`; run info gains the four answer fields.
7. **Composition + Makefile** — `main()` wires `PydanticAiLLM` and
   `build_agent_service(..., k=args.k)` under `--answers`; `make
   eval-answers` with `workers ?= 4`; `make help` line.
8. **First runs** — `make eval-answers label=agent-tool-on`, flip
   `QUERY_KNOWLEDGE_ENABLED=false` in `.env`, `make eval-answers
   label=agent-tool-off`. Sanity: negatives mostly refused, WEG-guia
   facts high, CESTARI low, `errors` explained. The owner reads the red
   cases (the judging pass) and decides the model sweep — one run per
   candidate `LLM_MODEL`, compared on gates, per-question tokens and
   latency. Result files are committed by the owner with the change they
   evidence.
9. **Documentation ritual** — update the [Eval Harness
   Module](/src/evaluation/evaluation.md) concept (how to run
   `eval-answers`, workers and the 429 signal, the judging workflow,
   error semantics, the normalization caveat, "output tokens include
   reasoning", one cold connection per LLM call); Decision 0006's open
   questions (judge deferred — owner judges); the agent spec's eval plan
   (`make eval-answers`) and its "not yet runnable" note; the
   architecture map's tree (`answers.py`); `specs/index.md`, root
   `index.md` if needed, `log.md`. Then **propose** a decision record
   with the measured baseline (deterministic answer gates, owner as
   judge, `Usage`/`has_answer` in the domain, one `k` per run) through
   the approval gate.

# Implementation notes (2026-09-02, as built)

The plan above was executed in order, TDD-first (195 tests green, pyright
zero). Where the built system differs from the design, the difference and
its reason:

- **`"answers": null` is always present** in a retrieval-only payload
  rather than the key being absent, so the schema is explicit and the
  compare rule reads one field. The committed retrieval runs that predate
  the key are read with `.get("answers")`. Every other retrieval-only
  field is byte-identical to before.
- **Thread safety needed one production change.** The safety argument in
  design decision 2 held for a `str` model (a client per call). Since the
  `FallbackModel` and the pydantic-ai `Embedder` landed, both are built
  once and shared across worker threads, each with its own event loop. A
  spike before the first run (6 threads × 2 rounds) failed one embedding
  call in twelve with `RuntimeError: <asyncio.locks.Event> is bound to a
  different event loop`; the LLM side passed 12 of 12 and 24 of 24. The
  embedding adapter now takes a factory and keeps one `Embedder` per
  thread (`threading.local`); the production `/question` route runs in the
  same thread-pool shape, so the fix is not eval-only. The LLM adapter is
  unchanged until a failure is measured. See the [Retrieval
  Module](/src/retrieval/retrieval.md).
- **The runner mirrors production wiring**: since 2026-09-02 through the
  composition root's `build_llm()` — `LLM_MODEL` behind
  `LLM_FALLBACK_MODEL` with the `LLM_THINKING` settings — not the bare
  model name. The run info records `llm_model` and `thinking`; a run in
  which the fallback actually answered would show its provider's latency,
  not an `error`.
- **`Usage` gained `reasoning_tokens` and `cost_usd`** (2026-09-02, the
  latency investigation): the adapter names the reasoning share of
  `output_tokens` from the provider's `usage.details` and prices each
  response with genai-prices through `ModelResponse.cost()`; the console's
  `tokens:` line shows `out … (reasoning …)`, a `cost:` line shows the run
  total and the per-question mean, and the `EFFICIENCY` lines compare
  latency and cost against the previous run with lower painted green.
  The design's cost analysis (≈ $0.19–0.35 per run, estimated with
  tiktoken) is now measured: $0.18 at `low` effort, ≈ $0.29 at the
  provider default.
- **Progress is logged per case** (`<id>: answered in N s (M request(s))`,
  `<id>: error after N s: …`) through the stdlib logger, with the httpx
  request logs silenced. Without it the first attempt ran silent for ten
  minutes and could not be told from a hang.
- **Normalization folds Unicode dashes to `-`** (U+2010–U+2014, U+2212)
  before the digit rules, added after the first run: the model wrote
  `Molykote G‑Rapid Plus` with a non-breaking hyphen and a correct answer
  scored red. Trailing decimal zeros are deliberately not stripped
  (`1,80` versus the fact `1,8`): the same rule would turn the
  digit-grouped `1.800` into `1.8`, so facts are authored as the manual
  prints them.
- **`false_refusal_rate` excludes errored cases** (they are counted in
  `errors`), so the two diagnostics never double-count a failure; an
  error is also not a refusal for `refusal_rate`, as designed.
- **`fact_cases` sits in the gates block**; slice blocks carry
  `fact_recall` as `null` when no case in the slice has facts, instead of
  a misleading 0.
- **An errored case carries `"usage": null`** (nothing was measured), not
  zeros.
- **Per-question means** divide by the answered (non-errored) cases;
  `run.cases.answered` counts every case that went through the answerer,
  errored ones included.
- **The `cited` entries' `source`** (`seed`/`tool`) is derived in the
  report from the first reference on that `(document, page)`.
- **Per-case `quotes` and `unmatched_citations`** (added with [Decision
  0013](/docs/decisions/0013-citations-as-quotes.md)): the passages the
  model quoted and the ones no chunk contained, 140-character previews,
  with the run total of unmatched quotes in `diagnostics` and on the
  `ANSWER DIAG` line. The citation gates still read `(document, page)`,
  now of the chunk each quote resolved to.
- **`make eval-answers`** defaults to `workers=4` as designed; the first
  runs used `workers=8` because 93 gpt-5-mini questions with tool rounds
  exceeded ten minutes at four, and no 429 appeared at eight.

# Open questions that stay open

- **Judge**: deferred as above; revisit when red cases are disputable.
- **Cold connection per LLM call**: `infer_model` builds a fresh httpx
  client on every `complete()`. Caching the `Model` in the adapter while
  the route stays sync would share one async client across threads and
  event loops — a hazard only of that hybrid shape. The owner's stated
  direction (2026-09-02) is a future migration to a fully async path
  (async ports, `async def` route, one event loop), where a shared
  cached client is the normal shape and the anyio threadpool's 40-thread
  ceiling disappears; the harness's `answerer` seam survives that change
  (a thread pool becomes `asyncio.gather` under a semaphore). Measured
  latency includes today's cold-connection cost.
- **Rate-limit retries**: none; `errors` in the report is the signal, and
  the fix is fewer workers. A retry policy (pydantic-ai's `retries`
  extra) is a dependency decision for later.

[^harness-spec]: Eval Harness — Design & Implementation Plan: populations, exclusion rules, results schema v2, compare rules, runner shape with injected collaborators.

[^eval-spec]: Eval Structure & Golden Dataset — Design: `expected_facts` normalization intent (case, unit spacing, decimal comma), alternates accepted by citation scoring, unanswerable semantics.

[^decision-0006]: 0006 — Eval metrics and golden-dataset shape: answer gates (facts containment, citation set-match), judged metrics diagnostic-only, efficiency logged every run.

[^decision-0008]: 0008 — Question agent baseline: the harness consumes `AgentService.answer()` in-process; HTTP end-to-end rejected.

[^decision-0009]: 0009 — Structured reply: `AgentReply.has_answer`, chunk ids as citation handles, XML chunk rendering (the token overhead measured here), the tool-cap `RuntimeError`.

[^agent-spec]: Question Agent — Design & Implementation Plan: live-smoke finding (refusal in the context's language) awaiting an eval-gated prompt fix; tool-on/off eval plan "not yet runnable".

[^golden-dataset]: Golden Dataset: negatives' near-miss traps, CESTARI as canary, page semantics behind `(document, page)`.

[^baseline]: Retrieval baseline run 20260901-190240: precision@5 0.24 (seed noise the citation gates now measure downstream), per-case retrieval latency median 342 ms.

[^openai-pricing]: OpenAI API pricing, consulted 2026-09-02 — per-1M-token prices quoted in the cost analysis.
