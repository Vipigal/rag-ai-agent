---
type: Architecture
title: System Architecture — Ports & Adapters Lite
description: The operating map of the codebase — the hexagonal-lite structure, the concepts behind it (ports, adapters, domain services, composition root), the rules every implementation must follow, and how to extend the system.
tags: [architecture, hexagonal, ports-and-adapters, ddd, protocols]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T02:30:26Z }
verified: { by: human:vinicius, at: 2026-08-31T21:22:00Z }
sources:
  - id: cosmic-python
    resource: https://www.cosmicpython.com
    title: "Architecture Patterns with Python (Percival & Gregory)"
  - id: pep-544
    resource: https://peps.python.org/pep-0544/
    title: "PEP 544 — Protocols: Structural subtyping"
---

# Why this architecture

Chosen in [Decision 0004](/docs/decisions/0004-ports-and-adapters-lite.md).
The short version: the parts of this system most likely to change — PDF
extractor, LLM provider, orchestration library — change under **eval
pressure**, not on a whim. The architecture's one job is to make those
swaps a one-line change at the composition root, so eval-driven
experiments stay cheap. Everything beyond that job was deliberately left
out (no DI container, no repository/unit-of-work, no event bus).

Read this before implementing any module. The
[Golden Rules](/docs/golden-rules.md) rank above it; the
[Development Workflow](/docs/development-workflow.md) (TDD + evals)
operates through it.

# The shape

```
src/
  domain/       the hexagon: pure Python, zero framework imports
    models      entities — Document, Chunk, RetrievedChunk, Answer —
                plus the LLM vocabulary: Message, ToolCall, AgentReply, Completion
    ports       Protocols — PdfExtractor, EmbeddingModel, VectorStore,
                Retriever, LLM
    services    domain services — AgentService, IngestionPipelineService —
                plus prompts: the deliberate prompt artifacts (Decision 0008)
  ingestion/    adapters for extraction (+ chunking as plain functions,
                later ingest-time augmentation)
  retrieval/    adapters for embeddings and the vector store (Qdrant),
                plus the Retriever strategies (vector, hybrid, decorators)
  llm/          adapters for LLM providers (PydanticAI direct today,
                swappable — Decision 0008)
  api/          FastAPI edge: thin routes + the composition root
  evaluation/   the eval harness: golden-dataset loader, matching,
                metrics, report, CLI runner (data lives in /evals)
```

Two request flows, one shared domain:

- `POST /documents` → route → **IngestionPipelineService** → extract
  (PdfExtractor) → chunk → embed (EmbeddingModel) → index (VectorStore).
- `POST /question` → route → **AgentService** → deterministic seed
  retrieval (Retriever) → bounded tool loop against the LLM port, which
  exposes a `query_knowledge` tool calling the **same Retriever
  instance** → `Answer` whose references accumulate from both retrieval
  paths (tagged `"seed"` / `"tool"` via `RetrievedChunk.retrieval_source`).

The services never meet. Their contract is the **persisted chunk**: one
vector-store point = chunk id + vector(s) + payload `{document_id,
filename, text, page, section, index_in_doc}`. Ingestion decides what gets
stored; retrieval decides how to use it; `Document` lives denormalized in
the payloads (no separate document store until a listing/deletion endpoint
demands one). A read-time strategy that needs new metadata (e.g.
parent-document linkage) is therefore also an ingestion change plus a
reindex — its eval must cover both sides.

# The concepts and how they map here

- **Port** — an interface the domain owns, declared as a
  `typing.Protocol`.[^pep-544] Protocols are structural (like TypeScript
  interfaces): an adapter satisfies one by having the right methods, with
  no inheritance or registration. Ports are named by capability
  (`PdfExtractor`, `VectorStore`), never by tool.
- **Adapter** — a concrete class satisfying a port, named
  `<tool><Port>` (e.g. `Pymupdf4llmExtractor`, `PydanticAiLLM`), living in
  its stage package. Adapters may import anything; the domain imports no
  adapter, ever — dependency inversion is that one-way arrow.
- **Entity vs domain service** — entities (`Document`, `Chunk`, `Answer`)
  are data with identity: plain dataclasses, no behavior beyond their own
  invariants. Domain services are stateless orchestrators of ports and
  carry the **`Service` suffix** (`AgentService`) to keep the distinction
  visible in code.[^cosmic-python]
- **Composition root** — the single function at the API edge that
  instantiates adapters and injects them into the services. It is the only
  place that knows both sides of every port. Swapping pymupdf4llm for
  docling is one line here; nothing else moves.
- **VectorStore vs Retriever** — the read side has two ports on purpose.
  `VectorStore` is _persistence_: `add`, `search`, growing keyword/sparse
  search when hybrid lands ([Decision
  0005](/docs/decisions/0005-retrieval-architecture.md)). `Retriever` is
  _strategy_: `retrieve(query, k) -> list[RetrievedChunk]`, the only
  retrieval seam `AgentService` sees. Retrieval experiments — hybrid
  search, reranking, small-to-big — are `Retriever` adapters or decorators
  in `src/retrieval/`, swapped in one line at the composition root and
  arbitrated by evals.
- **Seam discipline** — a port exists only where implementations really
  vary: **a second adapter, existing or concretely required — test fakes
  count.** Today that means extraction, embeddings/vector store,
  retrieval strategy, and LLM. Chunking is plain functions until evals
  demand competing strategies. Don't pre-abstract; a hypothetical seam is
  interface tax with no leverage.

# Rules

1. `src/domain/` imports only the stdlib and itself. No FastAPI, no
   Pydantic, no LangChain, no adapter.
2. Ports are `typing.Protocol`, declared in the domain, capability-named.
3. Adapters live in their stage package and are constructor-injected;
   nothing outside the composition root instantiates an adapter.
4. New ports require a real second implementation (fakes count) — else
   write the concrete thing and wait.
5. Routes are thin: validate with Pydantic → call one domain service → map
   the result to the challenge's response contract. Pydantic models exist
   only in `src/api/`.
6. Domain services end in `Service`; entities are bare nouns.
7. TDD runs through the seams: domain services are tested against fakes of
   their ports; adapters get their own tests; LLM/embedding accuracy
   belongs to evals, not unit tests (see the
   [Development Workflow](/docs/development-workflow.md)).
8. **One `EmbeddingModel` instance**, wired once at the composition root,
   embeds both chunks (write path) and queries (read path). Embedding the
   two sides with different models is the classic silent RAG bug; single
   wiring makes it impossible.
9. `AgentService` never touches `VectorStore` directly — all reading goes
   through `Retriever`. The `LLM` port speaks the domain's
   `Message`/`ToolCall`/`AgentReply` vocabulary — tools are plain Python
   functions, the reply a structured output (Decision 0009) — never
   provider types; the tool loop (iteration-capped) lives in `AgentService`.
10. **The architecture yields to the evals.** If a seam obstructs a
    retrieval experiment, reshape the seam and update this concept plus a
    decision record — never work around it in silence.

# How to extend

- **New adapter for an existing port**: implement the Protocol in the
  stage package, TDD-first; expose it in the composition root (config or
  code); run the evals before/after if it touches retrieval quality.
- **New retrieval strategy**: implement `Retriever` (or decorate an inner
  one) in `src/retrieval/`; swap at the composition root; eval
  before/after is mandatory. If it needs new chunk metadata, that is an
  ingestion change + reindex too — update this map and the decision log.
- **New capability**: start concrete inside the relevant stage package.
  The moment a second implementation is planned (or a test needs a fake),
  lift a Protocol into the domain and register the decision if it changes
  this map.
- **Module knowledge**: each stage package carries its own OKF concepts
  next to the code (see the
  [Authoring Guide](/docs/authoring-guide.md)) — this concept stays the
  cross-cutting map and must be updated when the shape changes.

[^cosmic-python]:
    Architecture Patterns with Python (Percival & Gregory) —
    source of the service-layer/domain-model split adapted here.

[^pep-544]: PEP 544 — Protocols: Structural subtyping (static duck typing).
