---
type: Playbook
title: Development Workflow — Testing-First, Eval-First
description: How code gets built in this repo — TDD for every Python module and its integrations, evals for end-to-end system accuracy.
tags: [process, tdd, evals, testing]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T18:40:00Z }
verified: { by: human:vinicius, at: 2026-08-31T18:31:00Z }
---

# Principle

This repo is **testing-first** and **eval-first**. The two loops answer
different questions and neither substitutes for the other:

- **Tests (TDD)** answer: _does the code do what I designed it to do?_
  Deterministic, fast, per-module and per-integration.
- **Evals** answer: _does the system achieve the challenge's objective —
  accurate, well-grounded answers?_ Statistical, end-to-end, measured
  against the [Golden Rules](/docs/golden-rules.md).

Both were established as directives at project start, before any code
existed, so that no module or pipeline stage is ever built without its
verification path defined first.

# Loop 1 — TDD for modules and integrations

Every Python module, and every integration between modules, is built
red-green-refactor:

1. **Red** — write a failing test that states the intended behavior.
2. **Green** — write the minimum code that makes it pass.
3. **Refactor** — clean up with the tests as a safety net.

Rules:

- No production code without a failing test demanding it first.
- Integration seams (e.g., extractor → chunker, retriever → prompt builder,
  API route → pipeline) get integration tests of their own; unit tests on
  the parts do not cover the seam.
- External services (LLM APIs, embedding APIs) are faked or recorded at the
  unit/integration level so the test suite stays fast and deterministic.
  Their real behavior is exercised by evals, not by unit tests.
- The full test suite must pass before any work is considered done.

# Loop 2 — Evals for system accuracy

Evals measure the system against the challenge objective: accurate answers
grounded in the uploaded documents. They are as much a deliverable as the
code.

- **Corpus**: the PDFs in `case_files/` (see the
  [Challenge Brief](/docs/challenge.md)) are the reference corpus — real motor
  manuals in Portuguese and English, matching the challenge's example
  question.
- **Golden dataset**: a curated set of question → expected-answer (and
  expected-source) pairs over the corpus. It grows as the system grows and
  lives in version control.
- **Two layers of measurement**, mirroring the Golden Rules:
  - **Retrieval evals** — given a question, were the relevant chunks
    retrieved? (serves the _Retrieval_ rule, independently of generation).
  - **Answer evals** — is the final answer correct and grounded in the
    returned `references`? (serves _Functionality_ and _LLM Use_).
- **Evals gate tuning**: any change to chunking, embedding, retrieval, or
  prompting must show its effect on the evals. "It seems better" is not
  evidence; a before/after eval run is.

# Working agreement for agents

- Starting a module? Write its first failing test before its first line of
  implementation.
- Touching the RAG pipeline (chunking, embedding, retrieval, prompts)? Run
  the evals before and after; report the delta.
- Found a wrong answer or bad retrieval during manual use? Turn it into a
  golden-dataset case first, then fix it — the eval suite is how bugs in
  accuracy stay fixed.
- Decisions about eval metrics, datasets, or thresholds are documented as
  [decision records](/docs/decisions/).
