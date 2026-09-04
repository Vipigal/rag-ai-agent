---
type: Decision
title: 0001 — Documentation lives in an OKF bundle at docs/
description: OKF v0.2 is the official documentation format, rooted at docs/ rather than the repo root.
tags: [documentation, okf, repo-structure]
status: deprecated
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T02:55:04Z }
verified: { by: human:vinicius, at: 2026-08-31T18:35:00Z }
sources:
  - id: okf-spec
    resource: /docs/okf-spec.md
    title: Open Knowledge Format (OKF) v0.2 specification
---

> **Deprecated** — superseded by
> [Decision 0002](0002-colocate-docs-with-code.md): the bundle is now
> rooted at the repo root with module docs co-located with module code.
> Kept for history; the rationale below reflects the state at the time.

# Context

The project owner (`human:vinicius`) established OKF as the official
documentation format for this repo: documentation must explain what the
code does not say — architecture decisions, rules, and decisions made
during the project — and must instruct the agents working here. The open
question was where the bundle root should sit.

# Decision

The knowledge bundle is rooted at `docs/`, as a bundle-in-a-subdirectory
(permitted by OKF §3). The OKF spec itself stays at the repo root
(`okf_spec.md`) as format reference material, outside the bundle.

# Rationale

- OKF conformance (§11) requires **every** non-reserved `.md` file inside
  the bundle tree to carry frontmatter with a `type`. Rooting the bundle at
  the repo root would make `README.md`, `okf_spec.md`, and any future
  markdown (license, CI templates) non-conformant or force frontmatter
  onto files that other tools expect to be plain.
- A clean separation keeps the repo root for code, config, and the
  README a reader opens first (serving the _Developer UX_
  [golden rule](/docs/golden-rules.md)), while `docs/` stays a self-contained,
  distributable knowledge bundle.
- The spec is not knowledge _about this project_; it is the format's own
  definition, so it sits outside the bundle and is cited via `sources`
  where relevant.

# Consequences

- Agents start every session from `docs/index.md` (see `CLAUDE.md`).
- Bundle-relative links (`/...`) resolve against `docs/`, not the repo
  root.
- Repo-level files (README, code) may link into `docs/` freely; they are
  consumers of the bundle, not part of it.
