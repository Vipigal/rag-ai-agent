---
type: Decision
title: 0002 — Module documentation is co-located with module code
description: The bundle is re-rooted at the repo root so each module's OKF concepts live in the directory that defines the module; docs/ keeps only cross-cutting knowledge.
tags: [documentation, okf, repo-structure, co-location]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T18:40:00Z }
verified: { by: human:vinicius, at: 2026-08-31T19:49:00Z }
sources:
  - id: okf-spec
    resource: /okf_spec.md
    title: Open Knowledge Format (OKF) v0.2 specification
---

# Context

[Decision 0001](0001-okf-bundle-at-docs.md) rooted the bundle at `docs/`.
The project owner (`human:vinicius`) redirected: documentation must be
co-located with the code it describes — e.g. the RAG ingestion module's
OKF concepts must live in the same folder where the module is defined. A
bundle confined to `docs/` cannot express that, so the bundle now spreads
across the codebase.

# Decision

- The bundle root is the **repo root**: the whole repository is one OKF
  bundle, with the root `index.md` and `log.md` at the top level.
- **Module knowledge is co-located**: concepts describing a module live in
  the module's own directory (e.g. `src/ingestion/`), next to the code,
  with an `index.md` once the directory holds two or more concepts.
- `docs/` remains a subdirectory of the bundle holding **cross-cutting**
  knowledge only: project north, process, and decision records.
- Decision records stay centralized in `docs/decisions/` (one number
  sequence for the whole project); module concepts link to the decisions
  that shaped them.

# Conformance handling

OKF conformance (§11) requires every non-reserved `.md` in the bundle tree
to carry frontmatter with a `type`. With the whole repo as the bundle:

- `okf_spec.md` received a minimal `type: Reference` frontmatter block; the
  spec text itself remains verbatim.
- **Exemption**: the repo-root `README.md` (when created) stays plain
  markdown — GitHub renders it as the landing page evaluators read first,
  and OKF frontmatter there would hurt the _Developer UX_
  [golden rule](/docs/golden-rules.md). Tool-mandated markdown (e.g.
  `CLAUDE.md`, CI or PR templates) falls under the same exemption. This is a deliberate,
  documented deviation, and knowledge must never live only in an exempt
  file.

# Consequences

- Bundle-relative links (`/...`) resolve against the repo root, e.g.
  `/docs/golden-rules.md` or `/src/ingestion/ingestion.md`.
- Every new `.md` anywhere in the repo is a concept and must carry
  frontmatter with a `type`, unless reserved (`index.md`, `log.md`) or
  exempt (above).
- Agents start every session from the root `index.md`; when working inside
  a module directory they must first read the concepts co-located there,
  and module design changes update those concepts in the same change.
- Supersedes [Decision 0001](0001-okf-bundle-at-docs.md), now deprecated.
