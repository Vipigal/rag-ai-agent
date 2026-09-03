---
type: Decision
title: 0013 — Citations are verbatim passages resolved by containment; references are the quotes
description: The model no longer names chunk ids — AgentReply.citations is a list of passages copied verbatim from the chunks it read; AgentService resolves each quote by normalized, line-wise containment over the chunks the model saw, keeps the ones it finds as Reference(chunk, quote, retrieval_source), drops and counts the rest, and POST /question returns the quotes as references, matching the challenge's excerpt-shaped contract; the <chunk> rendering lost its id attribute and the seed-page fallback for uncited answers is gone. Short per-page ids, enum-constrained UUIDs, an {chunk_id, quote} pair, page or seed fallbacks, provenance on the wire and fuzzy alignment were rejected; the before/after pair of answer-eval runs is recorded.
tags: [agent, citations, references, prompt, structured-output, api-contract, evals]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T22:19:37Z }
sources:
  - id: challenge
    resource: /docs/challenge.md
    title: Challenge Brief
  - id: decision-0009
    resource: /docs/decisions/0009-structured-reply-function-tools.md
    title: 0009 — Structured agent reply, function-derived tools, chunk ids as citation handles
  - id: decision-0012
    resource: /docs/decisions/0012-page-chunks-unit-vectors-and-providers.md
    title: 0012 — Retrieval granularity and providers
  - id: answer-spec
    resource: /specs/answer-eval-design.md
    title: Answer Eval — Design & Implementation Plan
  - id: findings
    resource: /evals/results/experiment-findings.md
    title: Eval Experiment Findings
  - id: next-steps
    resource: /docs/next-steps.md
    title: Next Steps — Handoff from the 2026-09-02 session
  - id: glossary
    resource: /docs/glossary.md
    title: Project Glossary
  - id: eval-module
    resource: /src/evaluation/evaluation.md
    title: Eval Harness Module
---

# Context

The challenge's example response carries a **short excerpt** as each
reference ("the motor xxx has requires 2.3kw to operate…"), and the brief
says `references` "carries the retrieved source excerpts that ground the
answer".[^challenge] Since [Decision 0012](/docs/decisions/0012-page-chunks-unit-vectors-and-providers.md)
made the chunk a whole page, `POST /question` returned pages of up to
6,000 characters as references: retrieval improved and the wire contract
got worse ([Next Steps](/docs/next-steps.md) section 4).[^decision-0012][^next-steps]

Two facts from the answer layer's first runs shaped the design
([findings](/evals/results/experiment-findings.md), chain 4):[^findings]
the model cites 1.8 pages per answer and one of them is not a gold page,
so citation precision sat at 0.70; and the citation handle of [Decision
0009](/docs/decisions/0009-structured-reply-function-tools.md) — a
36-character UUID the model has to copy — was the part of the reply the
owner trusted least, with a per-call `enum` recorded as the hardening if
copy errors showed.[^decision-0009]

Owner decisions taken on 2026-09-02, in conversation: each reference on the
wire is the quoted passage alone, as in the challenge's example; a quote
the system cannot find in the cited chunk is dropped, never replaced by
the page; and the model should not have to name a chunk at all — since it
reads whole pages, it can cut the passage it used and the system can find
where it came from.

# Decision

## Citations are verbatim passages, not chunk ids

`AgentReply.citations` stays `list[str]`, but each item is now a passage
copied verbatim from a chunk's `<text>`: the exact words, numbers and
units, one contiguous passage per citation — a sentence or a few, or a
table row with the header row on its own line above it. The `<chunk>`
element renders `document` and `page` only; the `id` attribute is gone
from the prompt, and the `query_knowledge` tool returns "chunks you can
quote". The schema of the structured reply is unchanged, so the adapter
and the fallback model are untouched.

## Resolution by normalized, line-wise containment

`domain/services/quotes.py` normalizes both sides the same way — casefold,
Unicode dashes folded to `-`, markdown markup (`*`, `#`, `|`, backticks,
`<br>`) and whitespace collapsed — and a quote is _contained_ in a chunk
when every non-empty line of the quote is a substring of the chunk's
normalized text. Lines are checked independently so a table citation can
carry the header row and the data row, which are not adjacent in the
chunk, and so a sentence broken across a PDF line break still matches.
`AgentService` resolves each citation against the chunks the model saw,
seed first and then tool results in the order they arrived, and takes the
first chunk that contains it. Duplicate quotes (by normalized form) are
kept once, in citation order.

## The wire carries the passages; what is not found is dropped

A resolved citation becomes `Reference(chunk, quote, retrieval_source)`;
`Answer.references` is the list of those, and the route renders
`reference.quote` — the model's passage as written, whitespace and
markup differences to the source included, never the whole chunk. A
citation that no seen chunk contains is dropped and counted in
`Answer.unmatched_citations`; an answered question whose citations all
fail therefore returns `references: []`. The former fallback — returning
the seed pages when the model cited nothing — is gone: the system never
returns text the model did not quote.

## Unmatched quotes are a measured diagnostic

The answer eval keeps its `(document, page)` citation gates unchanged
(they now read the resolved chunks) and gains, per case, the quoted
passages and `unmatched_citations`, with the run total on the `ANSWER
DIAG` line as `unmatched quotes N`.[^answer-spec][^eval-module] That
counter is the design's own risk indicator: how often the model fails to
quote what it read.

## The measured pair (k = 5, gpt-5-mini, tool on, 8 workers)

| Run                                    |   fact_recall | cit. precision | cit. recall | refusal_rate | unmatched quotes | latency mean | tokens out per question |
| -------------------------------------- | ------------: | -------------: | ----------: | -----------: | ---------------: | -----------: | ----------------------: |
| `20260902-202721-agent-tool-on` (ids)  |          0.93 |           0.70 |        0.92 |         0.75 |              n/a |       11.7 s |                     845 |
| `20260902-221750-citations-as-quotes` (quotes)                      |       0.92 |        **0.78** |      0.90 |      0.88 |        7 |      16.0 s |                 1,255 |

Citation precision rose from 0.70 to 0.78 — above the ±0.03 run-to-run
noise measured in chain 4 — for a visible reason: the model cites fewer
pages when it must quote them (1.39 per answer against 1.81), and the
cited pages that are not gold fell from 58 to 31. Fact recall and
citation recall stayed within noise; 7 of 200 quotes were dropped as not
found in any chunk (3.5 %), one answer ended with no reference. The price
is ≈ 400 more output tokens per question, the quotes being written out,
and ≈ 4 s of mean latency. Two earlier passes taught the containment
normalizer to fold quotation marks and HTML tags; all three, with the
dropped quotes that drove the rules, are read in the findings, chain
5.[^findings]

# Alternatives rejected

- **Chunk ids as today** (Decision 0009): the UUID copy is the fragile
  step, and the id adds nothing once unverified quotes are dropped — it
  would only serve the page fallback this decision rejects.
- **Short per-page ids** (`LB5001.p2`) plus a quote: less copy error than a
  UUID, but still a copy step, and a second identifier for the same
  `Chunk` — the invented-concept objection Decision 0009 already made
  against numbered handles.
- **UUIDs constrained by a per-call `enum`**: makes a hallucinated id
  impossible in strict mode, but rebuilds the output schema on every
  request and every tool round.
- **The `{chunk_id, quote}` pair**: a real quote cited under the wrong id
  would fail containment in that chunk and be dropped; searching all seen
  chunks is more robust and needs no id.
- **Falling back to the cited page, or to the seed pages, when a quote
  fails**: keeps a reference in every answer at the price of returning
  pages again; the eval's citation recall now shows the drop instead.
- **Provenance on the wire** — a `"document, p. N: …"` prefix or an object
  per reference: helps a human tester, but departs from the challenge's
  literal shape (a list of strings); document and page stay in the
  domain, the logs and the eval.
- **Fuzzy alignment, or returning the original span instead of the
  model's text**: more code for the rare cases where whitespace and
  markup normalization is not enough; the model's passage as written is
  readable and is what the containment check verified.

# Consequences

- **API Design**: `references` is now the excerpt list the challenge shows;
  README examples were recaptured from the running stack.
- **Vocabulary** ([glossary](/docs/glossary.md)):[^glossary] a _citation_
  is a passage the model quotes verbatim; a _reference_ is that passage
  resolved to its chunk, the passage alone on the wire.
- **Risk accepted**: a very short quote ("3.5") present in two pages
  resolves to the first chunk seen, which may not be the page the model
  meant; the prompt asks for sentences or table rows, and the eval's
  `(document, page)` precision would show the error.
- **What stands from Decision 0009**: the provider-enforced structured
  reply, function-derived tools, the XML context in a system message, the
  `dict[str, RetrievedChunk]` memory keyed by chunk id (internal only).
- **Follow-ups**: the fact-recall and citation gates decide the next prompt
  iteration; `unmatched_citations` decides whether the quoting rule needs
  tightening (e.g. a minimum quote length) — not before it is measured.
- Rules served: **API Design** and **Functionality** (the contract's
  excerpts), **LLM Use** (the prompt asks for the minimal supporting
  passage and the system verifies it), **Code Quality** (no second
  identifier; the schema unchanged).

[^challenge]: Challenge Brief — the `references` contract and its excerpt-shaped example.

[^decision-0009]: 0009 — Structured reply: chunk ids as citation handles, the per-call `enum` hardening recorded, "excerpt" rejected as an invented concept.

[^decision-0012]: 0012 — Retrieval granularity: the chunk is the page, which made whole-page references the wire's shape.

[^answer-spec]: Answer Eval — Design & Implementation Plan: the citation gates over `(document, page)` this decision leaves unchanged.

[^findings]: Eval Experiment Findings — chain 4 (citation precision 0.70 with ids) and chain 5 (the pair above).

[^next-steps]: Next Steps — section 4, the problem statement and the original sketch.

[^glossary]: Project Glossary — citation and reference, redefined by this decision.

[^eval-module]: Eval Harness Module — the `quotes` and `unmatched_citations` fields in the per-case block.
