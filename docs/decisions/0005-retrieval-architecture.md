---
type: Decision
title: 0005 — Retrieval architecture: strategy port, dual-path agent, Qdrant
description: The read side splits into a persistence port (VectorStore) and a strategy port (Retriever) so retrieval experiments are adapter swaps; answering runs a deterministic seed retrieval plus a query_knowledge tool over the same Retriever; Qdrant is the starting vector store.
tags: [retrieval, vector-store, qdrant, hybrid-search, embeddings, agent, tools]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T21:16:46Z }
verified: { by: human:vinicius, at: 2026-08-31T21:25:00Z }
sources:
  - id: retrieval-evidence
    resource: /docs/research/retrieval-strategy-evidence.md
    title: Retrieval Strategy Evidence
  - id: corpus-findings
    resource: /docs/research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
  - id: qdrant-docs
    resource: https://qdrant.tech/documentation/
    title: Qdrant documentation
---

# Context

Retrieval quality is the crux of the challenge ([Golden
Rules](/docs/golden-rules.md)), and the gathered
evidence[^retrieval-evidence] says the first experiments to run are hybrid
search (pure vector collapses on exact-identifier queries: NDCG 11.7 vs
79.2 for keyword — and this corpus is full of motor codes), reranking,
small-to-big expansion, and ingest-time contextual augmentation. The
architecture ([Decision
0004](/docs/decisions/0004-ports-and-adapters-lite.md)) must make each of
those a cheap, eval-gated swap. The owner additionally wants answering to
use retrieval two ways — deterministic context injection on every question
plus a `query_knowledge` tool the model may call — backed by one shared
implementation.

# Decision

## Two read-side ports

- **`VectorStore`** is the _persistence_ port: `add(chunks, vectors)`,
  `search(vector, k)`, growing keyword/sparse search when hybrid lands.
  Ingestion writes through it; retriever adapters read through it.
- **`Retriever`** is the _strategy_ port: `retrieve(query, k) ->
list[RetrievedChunk]`. It is the only retrieval seam `AgentService`
  sees. Strategies are adapters and decorators in `src/retrieval/`:
  `VectorRetriever` first, then `HybridRetriever`, and decorators such as
  `RerankingRetriever` or `ParentExpansionRetriever` wrapping an inner
  `Retriever`. Swapping strategy = one line at the composition root.

## The persisted chunk is the ingestion↔retrieval contract

The services never import each other. One Qdrant point = chunk `id` +
vector(s) + payload `{document_id, filename, text, page, section,
index_in_doc}` (`section` comes from the extractor's `toc_items`
breadcrumbs[^corpus-findings]). `Document` is denormalized into chunk
payloads — no separate document store until a listing/deletion endpoint
demands one. Any read-time strategy that needs new metadata (e.g.
parent-document linkage) is therefore also an ingestion change plus a
reindex, and its eval must cover both sides.

## One embedder, both paths

A single `EmbeddingModel` instance, wired once at the composition root,
embeds chunks at ingestion and queries at retrieval. Embedding write and
read with different models is the classic silent RAG bug; single wiring
makes it structurally impossible.

## Embeddings: provider-first, port-guarded

`EmbeddingModel` adapters may call frontier provider APIs (OpenAI, Gemini —
reusing the same `OPENAI_API_KEY`/`GEMINI_API_KEY` already supplied for the
LLM, so no extra setup burden) or run locally (fastembed,
useful as an eval baseline). No default is baked in; evals arbitrate.
Whatever the adapter, it must handle the corpus's languages (PT + EN +
ES[^corpus-findings]).

## Qdrant as the starting vector store

- Hybrid search is first-class: dense + sparse vectors on the same point
  with server-side RRF fusion — the top-priority experiment becomes
  configuration, not hand-rolled fusion code.[^qdrant-docs]
- `QdrantClient(":memory:")` runs the same client API in-process — adapter
  tests and evals run without Docker.
- Payloads carry the chunk contract; one extra `docker-compose.yml`
  service with a named volume keeps the single-command run.
- Apache-2.0, mature Python client.

Rejected: **Chroma** (great DX, weak sparse/hybrid story — penalizes the
crux), **pgvector** (hybrid means hand-written SQL + RRF — code that
doesn't serve retrieval), **FAISS** (a library, not a store: no payloads,
no service, everything manual). Per 0004's supremacy clause, evals can
overturn this choice.

## Dual-path answering over one Retriever

`AgentService.answer()` always runs a deterministic seed
`retriever.retrieve(question)`, then enters a bounded tool loop against
the `LLM` port exposing a `query_knowledge` tool whose handler closes over
the **same injected `Retriever`**. Consequences:

- The `LLM` port speaks a minimal domain vocabulary — `Message`,
  `ToolSpec`, `ToolCall` dataclasses — not provider types; the tool loop
  (with an iteration cap) lives in `AgentService`, so swapping LangChain
  never touches it.
- `Answer.references` accumulates chunks from **both** paths
  (`RetrievedChunk.retrieval_source` tags `"seed"` vs `"tool"`), keeping
  the challenge's references contract honest and letting evals measure
  each path's contribution.
- The tool can be disabled by configuration, making "does the agentic path
  earn its latency?" a cheap eval.

# Alternatives rejected

- **`VectorStore` as AgentService's seam** — every strategy change would
  edit the service instead of swapping an adapter; the strategy port is
  where the experiment leverage lives.
- **LangChain retriever classes as the seam** — welds the domain to the
  orchestration library 0004 confines to adapters.
- **Tool-only retrieval (no deterministic seed)** — makes retrieval
  quality hostage to the model's tool-calling mood; the seed guarantees
  grounded context on every question.
- **Local-only embeddings (fastembed as the default)** — the owner wants
  frontier provider embedders in play; the key they need is already
  required for the LLM, so the DX cost is zero.

# Consequences

- Experiment → edit map: hybrid/rerank/small-to-big → `src/retrieval/`
  (plus ingestion + reindex when new metadata is needed); contextual
  augmentation and chunk sizing → `src/ingestion/` + reindex. All gated by
  before/after evals per the
  [Development Workflow](/docs/development-workflow.md).
- `docker-compose.yml` gains a `qdrant` service with a named volume when
  retrieval is implemented.
- Serves _Retrieval_ (cheap experiments at the strategy seam), _LLM Use_
  (deliberate context injection + tool design), _Code Quality_ (pure
  domain, one-line swaps), and _Developer UX_ (no extra keys, one-command
  run, in-memory tests).

[^retrieval-evidence]:
    Retrieval Strategy Evidence — hybrid NDCG figures
    (Azure study), small-to-big hit-rate gains, contextual-retrieval
    failure reductions.

[^corpus-findings]:
    Case Files Corpus Findings — trilingual corpus
    (PT/EN/ES), motor-code-heavy text, pymupdf4llm `toc_items` breadcrumbs.

[^qdrant-docs]:
    Qdrant documentation — sparse vectors, Query API fusion,
    in-memory client mode.
