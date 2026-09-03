---
type: Module
title: Retrieval Module
description: The read side's adapters — PydanticAiEmbeddingModel over pydantic-ai's Embedder (OpenAI or Google behind one EMBEDDING_MODEL value, documents and queries embedded with their task types, batched per provider), QdrantVectorStore holding one multivector point per chunk scored by MaxSim (upserts batched under Qdrant's JSON limit, incompatible collections refused with the fix named) and VectorRetriever, the one Retriever strategy — with what the code cannot say: why the query is a one-row multivector, why the vector size is a registry at the composition root, what switching the embedder costs, the measured numbers, and how to test all of it without Docker.
tags: [retrieval, qdrant, multivector, embeddings, pydantic-ai, vector-store, retriever]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T20:19:48Z }
verified: { by: human:vinicius, at: 2026-09-02T19:02:00Z }
sources:
  - id: decision-0005
    resource: /docs/decisions/0005-retrieval-architecture.md
    title: 0005 — Retrieval architecture
  - id: decision-0012
    resource: /docs/decisions/0012-page-chunks-unit-vectors-and-providers.md
    title: 0012 — Retrieval granularity and providers
  - id: ingestion-module
    resource: /src/ingestion/ingestion.md
    title: Ingestion Module
  - id: findings
    resource: /evals/results/experiment-findings.md
    title: Eval Experiment Findings
  - id: qdrant-multivectors
    resource: https://qdrant.tech/documentation/concepts/vectors/
    title: Qdrant — Vectors (multivectors and MaxSim)
  - id: pydantic-ai-embeddings
    resource: https://ai.pydantic.dev/embeddings/
    title: Pydantic AI — Embeddings
---

# What this module is

The adapters of the read side, behind the ports [Decision
0005](/docs/decisions/0005-retrieval-architecture.md) drew:[^decision-0005]
`PydanticAiEmbeddingModel` (the `EmbeddingModel` port), `QdrantVectorStore`
(the `VectorStore` port) and `VectorRetriever` (the `Retriever` port, the
only strategy today). The write path uses the first two through
`IngestionPipelineService`; the question path uses all three through
`AgentService`. What gets stored is the ingestion module's
decision;[^ingestion-module] this concept covers how it is embedded,
kept and searched, per [Decision 0012](/docs/decisions/0012-page-chunks-unit-vectors-and-providers.md).[^decision-0012]

# The embedder adapter — one library, one config value

- `PydanticAiEmbeddingModel(make_embedder, max_batch)` wraps pydantic-ai's
  `Embedder`.[^pydantic-ai-embeddings] `embed_documents` calls
  `embed_sync(batch, input_type="document")` in slices of `max_batch`;
  `embed_query` calls `embed_sync(text, input_type="query")`. For Google
  models the input type becomes the `RETRIEVAL_DOCUMENT` /
  `RETRIEVAL_QUERY` task type; OpenAI models ignore the distinction. The
  two methods exist on the port for that asymmetry — a single `embed`
  cannot express it.
- The composition root owns three registries: `EMBEDDING_DIMENSIONS`
  (`openai:text-embedding-3-small` 1,536, `openai:text-embedding-3-large`
  3,072, `google:gemini-embedding-001` 3,072), `EMBEDDING_BATCH_SIZES`
  per provider (OpenAI 2,048 inputs per request, Google 100) and the
  default `google:gemini-embedding-001`. The size is a registry, not a
  probe, because the collection must be created with its vector size
  before any text has been embedded, and the dimension is also passed as
  `EmbeddingSettings(dimensions=…)` so the model returns exactly that.
  An `EMBEDDING_MODEL` outside the registry — including an unprefixed
  `text-embedding-3-small` — fails with the supported list in the message.
- One instance, cached at the composition root, embeds both the chunks'
  units and the queries (architecture rule 8); the eval harness reuses it.
- **One `Embedder` per thread.** The adapter takes a factory and builds
  the `Embedder` lazily in a `threading.local`. Measured 2026-09-02:
  `embed_sync` runs an event loop per thread, while a shared `Embedder`
  holds one async Google client; under six concurrent threads — the sync
  `/question` route in FastAPI's thread pool, or the eval's `--workers` —
  one call in twelve failed with `RuntimeError: <asyncio.locks.Event> is
  bound to a different event loop`. With a client per thread, 18 of 18
  passed. The LLM adapter shares its `FallbackModel` the same way and
  passed 24 of 24 in the same spike, so it stays as is until a failure is
  measured. The fully async path the owner intends removes the hazard,
  and the thread-local with it.
- Provider errors: pydantic-ai wraps them as `ModelAPIError`, mapped to
  502 at the API edge; the older `openai.OpenAIError` handler stays for SDK
  errors that escape unwrapped.

# The store — one multivector point per chunk

- The collection is created with `VectorParams(size, Distance.COSINE,
multivector_config=MultiVectorConfig(comparator=MAX_SIM))`.[^qdrant-multivectors]
  A point carries the chunk id (a UUIDv5 of `document_id:index`, so
  re-ingesting the same file overwrites instead of duplicating), a
  **list of unit vectors** — one per paragraph or table row the ingestion
  module produced — and the payload `{document_id, filename, text, page,
section, index_in_doc, kind, metadata}`, the persisted-chunk contract of
  Decision 0005.
- `add(chunks, vectors)` takes one vector group per chunk and refuses a
  length mismatch or an empty group before touching Qdrant; the bug that
  would produce either is a pipeline regrouping error, and the message
  says which chunk.
- **How MaxSim scores a page.** `search` sends the query as `[vector]`, a
  one-row multivector. MaxSim sums, over the query's rows, the best
  similarity against the point's rows; with one row that is simply the
  cosine of the chunk's best-matching unit. The page is therefore
  retrieved by its most specific paragraph or table row and returned
  whole — small-to-big without a parent index — and `RetrievedChunk.score`
  is that best-unit cosine, comparable across chunks.
- **Upserts are batched by floats.** `MAX_FLOATS_PER_UPSERT = 750_000`
  (488 vectors at 1,536 dimensions, 244 at 3,072): the WEG guia alone is
  1,951 units and a single upsert of it exceeded Qdrant's 32 MB JSON body
  limit. `_batches` never splits a chunk's units across requests.
- **Incompatible collections are refused, with the fix named.** An existing
  collection created without multivector support (the pre-0012 shape) or
  with another vector size than the configured embedder raises at store
  construction: delete it so it is recreated. Switching `EMBEDDING_MODEL`
  therefore always means re-indexing: `curl -X DELETE
localhost:6333/collections/chunks` (or `docker compose down -v`) for the
  API collection, `make eval-fresh` for the eval collection.

# The retriever — the one strategy, and where the next ones go

`VectorRetriever.retrieve(query, k)` embeds the query once and calls
`search`; twelve lines. Every retrieval experiment the findings queue is a
new `Retriever` adapter or a decorator around this one, swapped at the
composition root and arbitrated by evals:[^findings] hybrid sparse + dense
with RRF for exact identifiers (`W1/W2`, `MN417`), a score-relative cutoff
or smaller `k` for precision, deduplication of CESTARI's mirrored-language
pages, and — only if a corpus ever needs it — a neighbour-page expansion
when the matched unit is the first or last block of its page. None of them
changes the store's shape.

# Reference numbers and operations

- Corpus (four manuals): 164 points, 2,940 unit vectors; at 3,072
  dimensions ≈ 36 MB of vectors. Ingestion embeddings ≈ 270 k tokens:
  ≈ $0.04 with `gemini-embedding-001` (free on Google's free tier),
  ≈ $0.005 with `text-embedding-3-small`.
- Query embedding: ≈ 340 ms median with OpenAI on the eval runs, roughly
  +150 ms with Gemini; per-run means of 300–555 ms were network tails.
- Gates on the current configuration (`20260902-052352-gemini-embedding`):
  recall@5 0.95 · hit_rate@5 0.95 · MRR@5 0.91 · precision@5 0.39.

# How to test the module

- The store: `QdrantClient(":memory:")` runs the real client in-process —
  no Docker. `tests/retrieval/test_qdrant_store.py` covers the payload
  round trip, idempotent re-adds, the mismatch and empty-group refusals,
  ranking by best unit, `k`, the batching bound and both incompatible-
  collection refusals (a single-vector collection, another size).
- The embedder adapter: `pydantic_ai.embeddings.test.TestEmbeddingModel`
  subclassed to record calls — batching order, the `document`/`query`
  input types, that an empty list makes no provider call, and that the
  factory runs once per thread
  (`tests/retrieval/test_pydantic_ai_embedder.py`).
- The retriever: fakes of both ports. Embedding _accuracy_ belongs to the
  evals (`make eval`), never to unit tests.

[^decision-0005]: 0005 — Retrieval architecture: `VectorStore` versus `Retriever`, the persisted-chunk contract, Qdrant and its rejected alternatives.

[^decision-0012]: 0012 — Retrieval granularity and providers: why the chunk is the page, the vector the unit, the embedder Gemini.

[^ingestion-module]: Ingestion Module — the page chunker and `embedding_units`, which decide what this module stores.

[^findings]: Eval Experiment Findings — the runs behind the numbers and the experiments queued behind the `Retriever` port.

[^qdrant-multivectors]: Qdrant — Vectors: multivector configuration and the MaxSim comparator.

[^pydantic-ai-embeddings]: Pydantic AI — Embeddings: `Embedder`, input types, settings and the test model.
