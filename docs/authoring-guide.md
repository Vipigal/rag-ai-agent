---
type: Playbook
title: Authoring Guide — Adding Knowledge to This Bundle
description: How and when to add OKF concepts — the whole repo is one bundle, module knowledge is co-located with module code, and the bundle explains what the code cannot say.
tags: [process, documentation, okf]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T19:45:00Z }
verified: { by: human:vinicius, at: 2026-08-31T18:35:00Z }
sources:
  - id: okf-spec
    resource: /okf_spec.md
    title: Open Knowledge Format (OKF) v0.2 specification
---

# What this bundle is for

The **whole repository is one OKF bundle** ([OKF v0.2](/okf_spec.md)),[^okf-spec]
rooted at the repo root, with the bundle spread across the codebase so that
knowledge sits next to the code it describes (see
[Decision 0002](/docs/decisions/0002-colocate-docs-with-code.md)). Its job
is to explain **what the code does not say**:

- **Architecture decisions** — why the system is shaped this way, what was
  rejected, and under which constraints.
- **Rules** — policies the project follows (the [Golden Rules](/docs/golden-rules.md),
  the [Development Workflow](/docs/development-workflow.md)).
- **Decisions made during the project** — tradeoffs, tuning choices, eval
  thresholds, anything a future reader would otherwise have to reverse-
  engineer from git archaeology.

The litmus test before writing: _could a competent engineer recover this by
reading the code and its tests?_ If yes, do not document it — code and
tests are the source of truth for behavior. If no — the knowledge lives
only in a conversation, a judgment call, or an external source — it
belongs here.

# When to write

Documentation is not an afterthought; it is part of finishing a task.
Before closing any piece of work, ask:

1. Did I make a choice between viable alternatives? → add a
   [decision record](/docs/decisions/).
2. Did I establish a rule, convention, or process others must follow? →
   add or update a `Policy`/`Playbook` concept.
3. Did I rely on knowledge I could not find in this bundle? → that is a
   documentation gap; fill it.

Small factual corrections go into the existing concept (update
`generated`); new knowledge gets a new concept.

## The approval gate

This bundle is **curated**: the owner (`human:vinicius`) is its editor and
approves every new concept before it exists. An agent that identifies
something worth documenting does not write the file — it **proposes**
first, in conversation:

- the high-level idea (one short paragraph: what knowledge, why it earns
  a place in the bundle),
- the intended `type` and title,
- the intended location (path/filename).

Only after the owner's explicit OK does the concept get written, following
whatever adjustments the owner made to structure or location. **Updating an
existing concept** (corrections, link fixes, the closing ritual on
`index.md`/`log.md`) needs no proposal. Agents running unattended
(background research, parallel sessions) must not create concepts at all:
they report their proposal back and wait.

# Where knowledge lives: co-location

Knowledge lives **as close as possible to what it describes**:

- **Module knowledge is co-located with module code.** A concept about the
  RAG ingestion module lives in the ingestion module's own directory (e.g.
  `src/ingestion/`), next to the `.py` files. Name the module's overview
  concept after the module (e.g. `src/ingestion/ingestion.md`); further
  concepts get their own descriptive names.
- **Cross-cutting knowledge** — project north, process, anything owned by
  no single module — lives in `docs/`.
- **Decision records** live centrally in `docs/decisions/` (one number
  sequence for the whole project). Module concepts link to the decisions
  that shaped them.
- **Research findings** — corpus surveys, gathered external evidence,
  benchmark digests — live in `research/`, not `docs/`. They are `type:
  Reference` concepts kept as a **backlink source**: decisions and module
  concepts cite them in `sources` entries instead of re-researching.
- Any directory holding **two or more concepts** gets an `index.md`
  listing them; the root `index.md` links each module's knowledge once it
  exists.
- **Code and configuration files carry no comments.** What would have
  been a comment — a file header, a caveat, a rationale — lives in a
  co-located OKF concept instead (created through the approval gate
  above) or in the module's existing concept, and only if it truly needs
  saying. Knowledge buried in comments is invisible to the bundle.

Because the repo tree _is_ the bundle tree, **every `.md` file anywhere in
the repo must carry OKF frontmatter with a `type`**, except:

- the reserved filenames `index.md` and `log.md` (OKF §3.1), and
- the exempt files listed in
  [Decision 0002](/docs/decisions/0002-colocate-docs-with-code.md):
  the repo-root `README.md` and tool-mandated markdown such as
  `CLAUDE.md`, and
- dot-directories (`.claude/`, `.github/`), which sit outside the bundle
  tree — their markdown (e.g. skill files) follows each tool's own format.

Knowledge must never live only in an exempt file or outside the bundle.

# How to write a concept

Every concept is a markdown file with YAML frontmatter, per the
[OKF spec](/okf_spec.md). Conventions for this repo:

## Frontmatter

```yaml
---
type: Decision # REQUIRED — see types below
title: Short display name
description: One sentence; it is copied into index.md entries.
tags: [lowercase, kebab-case]
status: stable # draft | stable | deprecated (absent ⇒ stable)
generated: { by: <actor>, at: <ISO 8601 UTC> }
sources: # when the concept derives from material — cite it
  - id: stable-key
    resource: <url or bundle-relative path>
    title: Human-readable label
---
```

- **Actors** follow the OKF convention: agents write
  `claude_code/<model-id>` (e.g. `claude_code/claude-fable-5`); humans
  write `human:vinicius`.
- **`verified`** is added only by a human (or at a human's explicit
  direction) after actually reviewing the content — never self-added by
  the agent that generated it.
- **Per-claim attribution**: cite a source inline with a footnote whose
  label matches a `sources[].id`.

## Types used in this bundle

| Type           | Use for                                                         |
| -------------- | --------------------------------------------------------------- |
| `Policy`       | Non-negotiable rules (e.g. the Golden Rules).                   |
| `Playbook`     | Processes and how-tos agents must follow.                       |
| `Decision`     | One decision: context, options, choice, consequences.           |
| `Reference`    | Mirrors or summaries of external material (e.g. the challenge). |
| `Architecture` | Descriptions of system structure and its rationale.             |
| `Module`       | A co-located overview of one code module: purpose, boundaries, and the decisions behind it. |
| `Glossary`     | Ubiquitous language: `docs/glossary.md` project-wide, `glossary.md` co-located per module. |
| `Spec`         | An approved design for a subsystem before it is built, in `specs/` at the repo root; decision records distill its durable choices. |

New types are allowed when none fits — pick a descriptive name and add it
to this table.

## Naming and links

- Filenames are `kebab-case.md`. The file path (minus `.md`) is the
  concept's ID — renames break links, so name carefully.
- Decisions are named `NNNN-short-slug.md`, numbered sequentially, never
  reused. A superseded decision is marked `status: deprecated` and links
  to its successor — never deleted.
- Prefer bundle-relative links, which resolve against the **repo root**
  (`/docs/golden-rules.md`, `/src/ingestion/ingestion.md`); they survive
  file moves.

## The closing ritual

Every time a concept is added, renamed, or deprecated:

1. Update the nearest `index.md` (and the root one when a module gains its
   first concept or a new section appears), reusing the concept's
   `description` as the entry text.
2. Add an entry to the repo-root `log.md` under today's date
   (`YYYY-MM-DD`, newest first): `**Creation**`, `**Update**`, or
   `**Deprecation**`.

A concept that is not reachable from an `index.md` does not exist for the
next reader.

[^okf-spec]: Open Knowledge Format (OKF) v0.2 specification
