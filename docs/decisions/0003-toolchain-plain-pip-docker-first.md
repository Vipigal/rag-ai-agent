---
type: Decision
title: 0003 — Toolchain: plain pip + venv, Python 3.14, docker-first
description: The project uses classic pip with a pinned requirements.txt inside a venv (no uv/poetry), Python 3.14 provided by pyenv on the host, and Docker Compose as the official way evaluators run the system.
tags: [toolchain, pip, docker, python-version, developer-ux]
status: stable
verified: { by: human:vinicius, at: 2026-08-31T21:22:00Z }
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T02:55:04Z }
---

# Context

> **Amended by [Decision 0010](/docs/decisions/0010-examiner-developer-ux.md)**
> (2026-09-02): Python is no longer pinned to 3.14 — the floor is 3.12,
> `.python-version` is untracked, and `make up` runs compose in the
> foreground behind a Qdrant healthcheck. Pip + venv with pinned
> requirements and docker-first delivery stand.

The project needs a Python toolchain and a run story for two audiences:
the owner developing locally (TypeScript/Node background, values a familiar
and minimal workflow) and the challenge evaluators, who must set up and run
the system in minutes ([Golden Rules](/docs/golden-rules.md): _Developer
UX_). The owner explicitly ruled out modern package managers (uv, poetry)
in favor of the classic toolchain, and chose a docker-first delivery.

# Decision

- **Python 3.14** (currently 3.14.7), pinned in `.python-version`.
- **Host version management via pyenv** (the `nvm` of Python): versions
  are installed side by side in `~/.pyenv`; the system `python3` symlink
  is never remapped, because Ubuntu tooling (`apt` among others) depends
  on the distro's own Python.
- **Classic pip + venv, no uv/poetry/conda.** Dependencies are declared
  in `requirements.txt` (runtime) and `requirements-dev.txt` (adds
  pytest/httpx2), both with **exact `==` pins** — pip has no automatic
  lockfile, so pinning is what makes the evaluator's install reproduce
  the tested one.
- **Docker-first**: the API ships as a `python:3.14-slim` image, and
  `docker compose up` is the official, single-command way to run the
  system. Components the system grows to need (vector store, etc.) join
  `docker-compose.yml` so the one command keeps working.
- **Hot reload lives in compose, not in the image**: the Dockerfile CMD
  is a plain `uvicorn` serve; `docker-compose.yml` bind-mounts `./src`
  over the image's copy and overrides the command with `--reload`. Local
  edits reload inside the container; the image itself stays
  production-shaped.

# Alternatives rejected

- **uv / poetry** — better resolvers and real lockfiles, but one more
  tool for evaluators to know and against the owner's explicit preference
  for the classic, universally-understood flow.
- **Remapping system `python3` to 3.14** — breaks OS tooling; rejected
  outright.
- **deadsnakes PPA for the host Python** — only supports Ubuntu LTS; the
  dev machine runs a non-LTS release, so pyenv (compile from source) is
  the reliable path.

# Consequences

- Evaluators need only Docker: clone → `docker compose up` → API on
  `:8000`. No host Python required to run the system.
- Local development uses the venv (`.venv/`, git-ignored) for the fast
  TDD loop; `pytest` runs on the host against the same pinned versions
  the image installs.
- Every new runtime dependency must be added **pinned** to
  `requirements.txt` (dev-only tools go to `requirements-dev.txt`), and
  the image rebuilt (`docker compose up --build`).
- Serves _Developer UX_ (one-command run, minimal tooling) and _Code
  Quality_ (reproducible installs, prod-shaped image).
