---
type: Decision
title: 0010 — Developer UX: .env.example, make install, Python ≥ 3.12, foreground compose behind a Qdrant healthcheck, ingestion progress logs
description: The setup path a newcomer walks is a product surface — a committed .env.example with every knob, make install with a Python 3.12 floor (3.14 no longer pinned), guarded make targets that fail with the next command to run, docker compose in the foreground gated on a Qdrant healthcheck, and per-file ingestion progress logs so the ~60 s corpus upload is visibly alive.
tags: [developer-ux, makefile, docker-compose, python-version, logging, env]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T02:55:04Z }
verified: { by: human:vinicius, at: 2026-09-03T17:22:00Z }
sources:
  - id: golden-rules
    resource: /docs/golden-rules.md
    title: Golden Rules
  - id: decision-0003
    resource: /docs/decisions/0003-toolchain-plain-pip-docker-first.md
    title: 0003 — Toolchain: plain pip + venv, docker-first
  - id: ingestion-module
    resource: /src/ingestion/ingestion.md
    title: Ingestion Module
---

> **Amended by [Decision 0014](/docs/decisions/0014-error-semantics-and-startup-validation.md)**
> (2026-09-02): the "a failed prerequisite names the next command" rule now
> reaches the keys and the process itself — `make check-env` refuses empty
> `OPENAI_API_KEY`/`GEMINI_API_KEY`, the FastAPI lifespan validates the
> configuration and the vector store at startup so `make up` fails naming
> the problem, `GET /health` reports readiness, and every API error is one
> `{"detail": …}` sentence with a status that says who is at fault.

# Context

Someone meeting this repo for the first time has 30–60 minutes with it, and
the _Developer UX_ [priority](/docs/golden-rules.md)[^golden-rules] says
setup friction is a bug. A first-run review of the repo (2026-09-01) listed
the friction:

- No `.env.example`: the only way to learn that `OPENAI_API_KEY` is
  needed was reading `docker-compose.yml`, and `make eval` sourced
  `.env` without a guard — without the file it died with a shell error.
- No target creates the venv that `make test` and `make typecheck`
  assume exists.
- Python 3.14 pinned by `.python-version` and the image
  ([Decision 0003](/docs/decisions/0003-toolchain-plain-pip-docker-first.md))[^decision-0003]
  while nothing in the code needs it; a pyenv user without 3.14 hits
  "version is not installed" just by running `python3` in the directory.
- Uploading the four corpus PDFs blocks for ~60 s and answers once, with
  no log line in between — it looks hung.
- No Qdrant healthcheck: the API could take its first request while
  Qdrant was still starting.
- `make up` ran detached, hiding the logs that would have shown all of
  the above.

The same review noted the documentation weight for a human reader (root
`index.md` as an agent map, OKF ceremony, the format spec and the
challenge PDF in the repo root). This record covers the mechanics; the
curated five-minute path is the README's job and is out of scope here.

# Decision

- **`.env.example` is committed**, listing every variable the compose
  file and the composition root read: `OPENAI_API_KEY` first and empty,
  the rest with their defaults as values (config files carry no comments
  in this repo, so the value _is_ the documentation of the default).
  Compose now also passes `EMBEDDING_MODEL` and `QDRANT_COLLECTION`
  through, so every knob in the example reaches the container.
- **Guarded Makefile.** `check-env` and `check-venv` are prerequisites:
  `make up`, `eval` and `eval-fresh` stop with
  "No .env found. Run: cp .env.example .env …"; `test`, `typecheck` and
  `eval` with "No .venv found. Run: make install". The failure names the
  next command, never a shell error.
- **`make install`** creates `.venv` with `$(PYTHON)` (default
  `python3`, overridable as `make install PYTHON=python3.12`) and installs
  `requirements-dev.txt`. It refuses interpreters below 3.12, naming the
  version it found. Explicit on purpose: `make test` installs nothing
  behind the reader's back.
- **Python floor 3.12; developed on 3.14.** `.python-version` is no
  longer tracked (git-ignored; the owner keeps a local one). The image
  stays `python:3.14-slim`, the interpreter every live smoke ran on. The
  floor is verified, not assumed — see Consequences.
- **`make up` runs compose in the foreground** (`docker compose up
--build`): you watch the build, Qdrant's startup, uvicorn,
  and every request; Ctrl-C stops the stack. Supersedes 0003's detached
  `-d`.
- **Qdrant healthcheck + `depends_on: condition: service_healthy`.** The
  `qdrant/qdrant` image ships no `curl`, `wget` or `nc` — only
  `bash` — so the probe is bash's `/dev/tcp` connect to port 6333
  (`:> /dev/tcp/127.0.0.1/6333`), every 2 s, 15 retries after a 5 s
  grace. The API container is created only after Qdrant accepts
  connections.
- **Ingestion logs its progress.** `IngestionPipelineService` logs, via
  stdlib `logging` (allowed in the domain by architecture rule 1), one
  INFO line per stage per file — extracting (size), pages extracted
  (seconds), chunks embedded and indexed (seconds) — plus a start line and
  a done total. Time comes from an injected `clock` (default
  `time.perf_counter`), so the exact lines are unit-tested against a fake
  clock. The API edge (`api/main.py`) installs a root stream handler and
  sets the root level to INFO: uvicorn configures only its own loggers, and
  without this the domain's INFO lines are dropped silently.

# Alternatives rejected

- **Auto-creating `.env` from the example inside `make up`** — moves
  the failure to the first request (empty key → 500) instead of failing
  early with the fix in the message.
- **Auto-installing the venv inside `make test`** — convenient, but hides
  a multi-hundred-megabyte install behind a target the reader expects to
  be read-only.
- **Lowering the image to `python:3.12-slim`** — no gain: the image is
  the tested path and needs no host Python at all.
- **Keeping `.python-version` at `3.12`** — pyenv still errors when that
  series is absent; removing the file lets `python3` resolve to whatever
  the host has and lets the floor check do the talking.
- **An HTTP `/readyz` probe** — the accurate check, but with no HTTP
  client in the image it means a hand-rolled request over `/dev/tcp`,
  unreadable in a comments-free compose file. The TCP connect is the
  Qdrant-community idiom and sufficient for startup ordering.
- **Per-page extraction logs or pymupdf4llm's progress bar** — the bar
  writes carriage-return frames that garble `docker compose` output;
  per-page logging would need per-page `to_markdown` calls, an
  ingestion-side change that goes through evals
  ([Decision 0007](/docs/decisions/0007-naive-ingestion-baseline.md)).
- **Logging in the route instead of the service** — the route sees one
  `ingest()` call; per-file progress exists only inside the service loop.
- **A `make down`** — Ctrl-C on the foreground stack already stops it;
  the Makefile surface stays small.

# Consequences

- Setup path: `cp .env.example .env` → set the keys → `make up` in
  one terminal; `make install` then `make test` for the suite on any
  Python ≥ 3.12.
- Verified 2026-09-02 with the pinned `requirements-dev.txt`: the suite
  (115 tests) and pyright `standard` are green on CPython 3.12.7, 3.13.3
  and 3.14.7 (throwaway venvs for 3.12/3.13; the image and the owner's
  venv on 3.14).
- `make up` no longer returns; anything that chained `make up && make
eval` starts the stack in another terminal (the
  [Eval Harness Module](/src/evaluation/evaluation.md) says so).
- Decision 0003 stands for pip + venv + pinned requirements and
  docker-first delivery; its "Python 3.14 pinned" and "detached compose"
  points are superseded here.
- The [Ingestion Module](/src/ingestion/ingestion.md)[^ingestion-module]
  records where to watch the upload's progress and which stretch stays
  silent (pymupdf4llm on the largest PDF).
- Serves _Developer UX_ directly and _Code Quality_ through the tested,
  clock-injected logging.

[^golden-rules]: Golden Rules — _Developer UX_: setup friction is a bug.

[^decision-0003]:
    0003 — Toolchain: the pip/venv/docker-first choices this record
    amends.

[^ingestion-module]: Ingestion Module — per-stage timings behind the progress lines.
