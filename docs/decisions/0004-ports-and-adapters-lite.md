---
type: Decision
title: 0004 — Ports & adapters lite
description: The system is structured as a minimal hexagonal architecture — a framework-free domain in src/domain (entities, ports as Protocols, domain services), swappable adapters per pipeline stage, and one explicit composition root at the API edge.
tags: [architecture, hexagonal, ports-and-adapters, dependency-inversion, kiss]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T20:58:29Z }
verified: { by: human:vinicius, at: 2026-08-31T21:25:00Z }
sources:
  - id: corpus-findings
    resource: /docs/research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
  - id: cosmic-python
    resource: https://www.cosmicpython.com
    title: "Architecture Patterns with Python (Percival & Gregory)"
---

# Context

The system has two independent use cases sharing one domain: `POST
/documents` (extract → chunk → embed → index) and `POST /question`
(retrieve → prompt → LLM → answer). Several implementation choices are
expected to be revisited under eval pressure: the PDF extractor (the corpus
contains a PDF with a broken text layer that may defeat any single
extractor[^corpus-findings]), the LLM provider (the challenge lists
provider fallback as an enhancement), and the orchestration library (the
owner wants to start with LangChain but stay free to drop it). The owner
works OOP-first (Nest.js background) and wants dependency inversion,
but under an explicit KISS constraint: the crux of the project is
retrieval quality, not architectural purity.

# Decision

A minimal hexagonal (ports & adapters) architecture:[^cosmic-python]

- **Pure domain in `src/domain/`** — no framework imports (no FastAPI, no
  Pydantic, no LangChain). Entities are stdlib `@dataclass`es (`Document`,
  `Chunk`, `Answer`); ports are `typing.Protocol` interfaces; use cases are
  **domain services** named with the `Service` suffix (`AgentService`,
  `IngestionPipelineService`) that depend only on ports via constructor
  injection.
- **Adapters live in stage packages** (`src/ingestion/`, `src/retrieval/`,
  `src/llm/`), one package per pipeline stage, satisfying the domain's
  Protocols structurally.
- **Ports only at real seams.** A Protocol is introduced only when a second
  adapter exists or is concretely required — a test fake counts as a second
  adapter. Real seams today: PDF extraction (pymupdf4llm vs docling/OCR),
  LLM (fallback requirement + faked in tests), vector store (faked in
  tests). Chunking starts as pure functions inside ingestion; it gains a
  port only if evals demand competing strategies.
- **One explicit composition root** at the API edge builds every adapter
  and wires the domain services. No DI container library.
- **LangChain is confined to adapters.** The domain never imports it;
  replacing it means writing new adapters for the same ports.
- **Supremacy clause**: when architecture and eval results conflict, the
  architecture yields. Seams exist to make eval-driven swaps cheap; the
  moment one obstructs a retrieval experiment, it is reshaped.

Details, rules, and the concept map live in the
[Architecture](/docs/architecture.md) concept.

# Alternatives rejected

- **DI container libraries** (`dependency-injector`, `punq`) — solve a
  graph-scale problem this project will never have; the whole wiring fits
  in one small function.
- **Full cosmicpython stack** (repository pattern, unit of work, event
  bus) — built for transactional relational domains; our only store is the
  vector store, already behind a port.
- **Framework-coupled domain** (Pydantic models and FastAPI dependencies
  throughout) — faster on day one, but welds the domain to tools the owner
  explicitly wants to be able to swap, and makes pure-unit TDD noisier.
- **Flat scripts, no seams** — cheapest start, but every extractor/LLM A/B
  eval would require editing the pipeline instead of swapping an adapter.

# Consequences

- `POST /documents` is served by `IngestionPipelineService`, `POST
/question` by `AgentService`; routes stay thin (validate → call service →
  map to the challenge's response contract).
- Pydantic exists only at the API edge; domain data crosses seams as
  dataclasses.
- TDD per the [Development Workflow](/docs/development-workflow.md) gets
  its fakes at the ports; evals compare adapters through the same seams.
- Serves _Code Quality_ (small, composable, test-first modules),
  _Retrieval_ (cheap extractor/retriever experiments), and the challenge's
  provider-fallback enhancement (a fallback LLM is just another adapter).

[^corpus-findings]:
    Case Files Corpus Findings — the CESTARI manual's
    broken CMap text layer yields `�` without OCR.

[^cosmic-python]:
    Architecture Patterns with Python (Percival & Gregory) —
    the ports-and-adapters/DDD reference this decision adapts, deliberately
    dropping its repository/UoW/event patterns.
