---
type: Policy
title: Golden Rules — the project's priorities
description: The six axes every change in this repo is weighed against — Functionality, Retrieval, LLM Use, Code Quality, API Design, Developer UX — and what each one means in practice here.
tags: [policy, priorities, north-star]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-04T12:00:00Z }
verified: { by: human:vinicius, at: 2026-08-31T18:28:00Z }
---

# Why this document exists

A RAG system can be optimised in a dozen directions at once, and most of
them trade against each other: a cleverer retriever costs latency, a
tighter abstraction costs readability, a richer answer costs grounding.
This document fixes the six axes that matter here and the order of
argument when two of them collide. Every agent working in this repo holds
them in context, and every [decision record](/docs/decisions/) says which
ones it serves.

# The rules

| Priority      | What it demands                                            |
| ------------- | ---------------------------------------------------------- |
| Functionality | The system works as described and returns accurate answers |
| Retrieval     | Relevant document chunks are correctly retrieved           |
| LLM Use       | Prompts are constructed effectively for answer generation  |
| Code Quality  | Clean, modular, maintainable code                          |
| API Design    | Clear, documented, intuitive endpoints                     |
| Developer UX  | Easy to set up, test, and understand the solution          |

# What each rule means in practice

1. **Functionality** — the API contract is implemented exactly as
   specified, end to end, and answers are _accurate_ — which is why this
   repo is eval-first: accuracy is measured, not assumed. See the
   [Development Workflow](/docs/development-workflow.md).
2. **Retrieval** — retrieval quality is a first-class, independently
   evaluated concern, not "the answer looked right". Evals must measure
   whether the _right chunks_ were retrieved, separately from whether the
   final answer was right.
3. **LLM Use** — prompts are deliberate artifacts: grounded in retrieved
   context, designed to cite references, and iterated on through evals,
   never ad-hoc strings buried in code.
4. **Code Quality** — modules are small, composable, and built test-first
   (TDD). A module without tests does not exist.
5. **API Design** — endpoints are documented (OpenAPI), validate their
   input, and fail with errors that name what went wrong and what to do
   about it.
6. **Developer UX** — a newcomer must be able to clone, set up, run, and
   test the project in minutes, following the README alone. Setup friction
   is a bug.

# How agents must use this

- Before starting any task, re-read the table above and ask: _which of
  these does this task serve?_
- When a tradeoff arises — a clever abstraction against readable code, a
  faster hack against a testable module — resolve it in favour of these
  priorities.
- They are not ranked against each other; a change that improves one by
  degrading another needs a [decision record](/docs/decisions/)
  justifying it.
