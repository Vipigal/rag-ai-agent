# CLAUDE.md

RAG question-answering system over uploaded PDFs, built for an ML
Engineering interview challenge. Python. The full brief lives in
`docs/challenge.pdf`.

## Start every session here

1. Read `index.md` at the repo root — the whole repository is one OKF
   knowledge bundle (OKF v0.2 format, spec in `docs/okf-spec.md`), rooted here.
   Follow its links progressively into whatever concepts are relevant to
   your task.
2. Load `docs/golden-rules.md` into context and keep it there. It holds the
   project's six priorities (Functionality, Retrieval, LLM Use, Code
   Quality, API Design, Developer UX). They are the north star: every task,
   tradeoff, and review is resolved in their favor.
3. Knowledge is co-located with code: before working inside a module
   directory, read the `.md` concepts sitting next to its code.

## How we build

- **Testing-first**: every Python module and every integration between
  modules is built with TDD — failing test first, then code. No production
  code without a test demanding it.
- **Eval-first**: system accuracy (retrieval quality and answer quality) is
  measured with evals against a golden dataset over `case_files/`. Changes
  to chunking, embedding, retrieval, or prompts must show before/after eval
  results.
- Details and working agreements: `docs/development-workflow.md`.

## Documentation duty

The OKF bundle is the official documentation of this repo. It explains
what the code cannot say: architecture decisions, rules, and decisions
made during the project. Module knowledge lives **next to the module's
code** (e.g. `src/ingestion/ingestion.md`); cross-cutting knowledge lives
in `docs/`; decision records in `docs/decisions/`.

Before finishing any task, ask yourself: **did I make a choice, follow a
rule, or rely on knowledge that I could not find documented in the
bundle?** If yes, document it — a decision record, or a new/updated
concept co-located with the code it describes — following
`docs/authoring-guide.md`, and update the nearest `index.md` and the root
`log.md`. Documenting is part of the task, not an extra.

**The bundle is curated — never create a new concept without approval.**
Before writing any new `.md` concept, propose it to the owner in chat: the
high-level idea (one paragraph), the intended `type`, and the intended
path/filename — then wait for an explicit OK (see the approval gate in
`docs/authoring-guide.md`). Updating existing concepts and the
`index.md`/`log.md` ritual need no proposal. Research findings go in
`docs/research/`.

Because the repo tree is the bundle tree, every `.md` you create must
carry OKF frontmatter with a `type` (exceptions: `index.md`/`log.md`,
which are reserved, and `README.md`, which is exempt — see
`docs/decisions/0002-colocate-docs-with-code.md`).

Never add `verified` frontmatter to content you generated yourself; only a
human reviewer does that.
