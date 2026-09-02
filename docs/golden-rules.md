---
type: Policy
title: Golden Rules
description: The challenge's six evaluation criteria, adopted as the non-negotiable priorities that every change in this repo must serve.
tags: [policy, evaluation-criteria, north-star]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T02:55:04Z }
verified: { by: human:vinicius, at: 2026-08-31T18:28:00Z }
sources:
  - id: challenge-pdf
    resource: /docs/challenge.pdf
    title: "[Challenge] Machine Learning Engineering - LLM"
---

# Why this document exists

This repo exists to score well on the [challenge](/docs/challenge.md). Its
evaluation criteria are therefore the north star of every decision: when
two approaches conflict, choose the one that scores better against these
rules. Every agent working here must hold them in context, and every
[decision record](/docs/decisions/) should say which rules it serves.

# The rules

Verbatim from the challenge:[^challenge-pdf]

| Criteria      | Description                                                |
| ------------- | ---------------------------------------------------------- |
| Functionality | The system works as described and returns accurate answers |
| Retrieval     | Relevant document chunks are correctly retrieved           |
| LLM Use       | Prompts are constructed effectively for answer generation  |
| Code Quality  | Clean, modular, maintainable code                          |
| API Design    | Clear, documented, intuitive endpoints                     |
| Developer UX  | Easy to set up, test, and understand your solution         |

# What each rule means in practice

1. **Functionality** — the API contract in the [Challenge Brief](/docs/challenge.md)
   is implemented exactly as specified, end to end, and answers are
   _accurate_ — which is why this repo is eval-first: accuracy is measured,
   not assumed. See the [Development Workflow](/docs/development-workflow.md).
2. **Retrieval** — retrieval quality is a first-class, independently
   evaluated concern (not just "the answer looked right"). Evals must
   measure whether the _right chunks_ were retrieved, separately from
   whether the final answer was right.
3. **LLM Use** — prompts are deliberate artifacts: grounded in retrieved
   context, designed to cite references, and iterated on through evals,
   never ad-hoc strings buried in code.
4. **Code Quality** — modules are small, composable, and built test-first
   (TDD). A module without tests does not exist.
5. **API Design** — endpoints match the challenge spec, are documented
   (e.g., OpenAPI), validate input, and fail with clear errors.
6. **Developer UX** — an evaluator must be able to clone, set up, run, and
   test the project in minutes, following the README alone. Setup friction
   is a bug.

# How agents must use this

- Before starting any task, re-read the table above and ask: _which rules
  does this task serve?_
- When a tradeoff arises (e.g., a clever abstraction vs. readable code, a
  faster hack vs. testable module), resolve it in favor of the rules.
- Rules are not ranked against each other; a change that improves one by
  degrading another needs a [decision record](/docs/decisions/) justifying it.

[^challenge-pdf]: [Challenge] Machine Learning Engineering - LLM
