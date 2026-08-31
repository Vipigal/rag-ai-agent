---
type: Spec
title: Naive Ingestion Baseline — Design
description: Approved design for the first functional POST /documents — a deliberately naive pipeline (pymupdf4llm extraction without OCR, fixed-size chunking, OpenAI embeddings, Qdrant) whose entities and payload carry explicit extension points (kind, metadata) so eval-driven improvements swap pieces without redesign.
tags: [ingestion, baseline, chunking, embeddings, qdrant, design, spec]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T22:50:49Z }
verified: { by: human:vinicius, at: 2026-08-31T22:55:00Z }
sources:
  - id: challenge
    resource: /docs/challenge.md
    title: Challenge Brief — ML Engineering (LLM)
  - id: decision-0005
    resource: /docs/decisions/0005-retrieval-architecture.md
    title: 0005 — Retrieval architecture
  - id: corpus-findings
    resource: /research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
  - id: retrieval-evidence
    resource: /research/retrieval-strategy-evidence.md
    title: Retrieval Strategy Evidence
---

# Goal

Give the repo its first functional `POST /documents`: a **naive baseline**
ingestion pipeline that the golden dataset ([Decision
0006](/docs/decisions/0006-eval-metrics-and-golden-dataset.md)) can measure,
establishing the honest "before" for every eval-gated improvement that
follows. The baseline is deliberately simple — its job is to be measurable
and swappable, not good. Serves _Functionality_ (the challenge contract,
end to end) and _Retrieval_ (the baseline every experiment is compared
against); the swappability serves _Code Quality_.

# Scope

**In:** the route, the ingestion domain service, the four baseline
adapters/functions (extractor, chunker, embedder, vector store write side),
the composition root, Qdrant in docker compose, and the entity/payload
contract with its extension points.

**Out (deferred, with their evolution paths recorded here):** the OCR
quality gate for the CESTARI broken text layer (first eval-driven
improvement), the image pipeline, `VectorStore.search()` and everything
read-side, GET/DELETE document endpoints, async ingestion, PDF blob
persistence.

# Route contract

`POST /documents`, synchronous (the challenge response returns counts, so
processing is inline).[^challenge] Request: `multipart/form-data`, field
`files`, one or more PDFs. Response `200`:

```json
{
  "message": "Documents processed successfully",
  "documents_indexed": 2,
  "total_chunks": 128
}
```

**Error semantics — all-or-nothing** (the contract has no per-file
status): every file is validated upfront — field present, non-empty,
magic bytes `%PDF` (client content-type headers are unreliable). Any
invalid file → `422` naming the file, nothing indexed. Embedding-provider
failure mid-pipeline → `502` with a clear message. The route stays thin:
Pydantic validation → `IngestionPipelineService.ingest()` → map result to
the contract JSON (architecture rule 5).

# Module structure

```
src/
  domain/
    models.py     Document, Page, Chunk (see Entities)
    ports.py      PdfExtractor, EmbeddingModel, VectorStore, Chunker alias
    services/
      ingestion_pipeline.py   IngestionPipelineService
  ingestion/
    pymupdf4llm_extractor.py  Pymupdf4llmExtractor (adapter)
    chunking.py               fixed_size_chunks() — pure function
  retrieval/
    openai_embedder.py        OpenaiEmbeddingModel (adapter)
    qdrant_store.py           QdrantVectorStore (adapter, write side only)
  api/
    routes/documents.py       thin route
    composition.py            composition root (env → adapters → service)
```

Ports (domain-owned `typing.Protocol`s, per [Decision
0005](/docs/decisions/0005-retrieval-architecture.md)):[^decision-0005]

```python
class PdfExtractor(Protocol):
    def extract(self, data: bytes, filename: str) -> list[Page]: ...

class EmbeddingModel(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

class VectorStore(Protocol):
    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...

Chunker = Callable[[Document, list[Page]], list[Chunk]]
```

`IngestionPipelineService` is a domain service and cannot import
`src/ingestion/`, so the chunker is **constructor-injected as a callable**
— a type alias, not a Protocol, per seam discipline: chunking earns a port
only when evals demand competing strategies. `VectorStore` is born with
`add()` only; `search()` arrives with the retrieval session, demanded by a
test.

# Entities

```python
@dataclass(frozen=True)
class Document:
    id: str          # sha256 hex of the file bytes (content-addressed)
    filename: str

@dataclass(frozen=True)
class Page:          # TRANSIENT — in-memory only, never persisted
    number: int
    text: str        # markdown from the extractor
    section: str | None   # toc_items breadcrumb

@dataclass(frozen=True)
class Chunk:
    id: str          # UUID5 of "{document_id}:{index_in_doc}" — deterministic
    document_id: str
    filename: str
    text: str
    page: int
    section: str | None
    index_in_doc: int
    kind: str = "text"    # extension point: "table", "image_caption", ...
    metadata: dict[str, object] = field(default_factory=dict)  # flows into payload untouched
```

Design points debated and settled:

- **Chunk↔Page is denormalization, not a reference.** `Page` exists only
  between extractor and chunker inside one request; the persisted chunk is
  the only survivor of ingestion (0005). The baseline chunker splits
  _within_ pages, so every chunk has exactly one `page`. A future
  cross-page strategy makes this `page_start/page_end` — an ingestion
  change + reindex, the documented evolution path.
- **The embedding is not an entity field.** Vectors pair with chunks
  positionally — `vectors[i]` embeds `chunks[i].text`, invariant asserted
  in the store adapter (`len(chunks) == len(vectors)`). Rationale: hybrid
  search makes the vector plural (dense + sparse on one point), an
  `embedding: ... | None` field is a half-initialized-entity smell, and
  the domain never reads vectors back — they live only in the Qdrant
  point.
- **`kind` + `metadata` are the extension points.** The Qdrant payload is
  schemaless and filterable on nested keys, so both cost nothing now and
  give table/image experiments their slot (`kind="table"`,
  `kind="image_caption"`, `metadata={"image_path": ...}`) without entity
  redesign. A discriminated union (`TextChunk | TableChunk | ...`) was
  rejected _for now_: the pipeline treats every chunk identically
  (embed `text`, persist), and architecture rule 4 demands a real second
  implementation before abstracting. Promoting `kind` to real types later
  is mechanical.

**Persisted payload** = the 0005 contract extended with the extension
points: `{document_id, filename, text, page, section, index_in_doc, kind,
metadata}` (amendment recorded in [Decision
0007](/docs/decisions/0007-naive-ingestion-baseline.md)).

# The pipeline

Per file: `document_id = sha256(bytes)` → extract → chunk → embed → add.

- **Extractor** — `pymupdf4llm.to_markdown(page_chunks=True)`, defaults
  otherwise: no OCR, no quality gate, `write_images=False`. The CESTARI
  manual's broken CMap will index `�`-runs **on purpose** — the eval
  baseline must capture that failure in numbers before the gate lands as
  the first measured improvement.[^corpus-findings] `section` = the page's
  `toc_items` breadcrumbs joined with `" > "` (nearly free, and the
  payload contract requires the field).
- **Chunker** — `fixed_size_chunks(document, pages, size=1000,
overlap=200)`: character-based split within each page, `page`/`section`
  propagated, `index_in_doc` global across the document. Sizing is an
  eval-tunable, not a commitment.[^retrieval-evidence]
- **Embedder** — OpenAI `text-embedding-3-small` (1536 dims): the
  `OPENAI_API_KEY` is already required for the LLM, so zero extra setup;
  adequate multilingual coverage for PT/EN/ES; cents for the whole
  corpus. One `embed()` batch per document, split into max-size
  sub-batches inside the adapter.
- **Vector store** — Qdrant collection `chunks` (cosine, 1536), created
  by the adapter if missing. Upsert semantics + deterministic IDs make
  re-ingestion **idempotent**: re-uploading the same file overwrites the
  same points, so repeated eval runs never inflate the index with
  duplicates. Accepted limitation: same filename with different content
  coexists (different `document_id`); stale chunks of a shrunk re-upload
  are impossible because content-addressing gives changed content fresh
  IDs.

# Infrastructure

- **docker compose**: new `qdrant` service (official image, port 6333,
  named volume `qdrant_data:/qdrant/storage`); `api` gains `depends_on:
qdrant` and `QDRANT_URL=http://qdrant:6333`; `OPENAI_API_KEY` flows from
  `.env`.
- **Config**: read from `os.environ` only in the composition root —
  `OPENAI_API_KEY` (required), `QDRANT_URL` (default
  `http://localhost:6333`), `QDRANT_COLLECTION` (default `chunks`),
  `EMBEDDING_MODEL` (default `text-embedding-3-small`). No
  pydantic-settings yet.
- **Dependencies**: `pymupdf4llm`, `openai`, `qdrant-client`,
  `python-multipart`; dev: `httpx` (TestClient).
- The service is wired once per process (singleton via `app.state`,
  exposed to routes with `Depends`); tests swap adapters through FastAPI
  `dependency_overrides`.

# No relational database — and the triggers that would change that

Qdrant serves every persistence need in the challenge scope: chunks +
metadata live in payloads; even a future GET/DELETE `/documents` is a
scroll/filter on `document_id`. A relational store only earns a place if
one of these appears: **(a)** transactional state outside chunks (users,
auth, async upload jobs with status), **(b)** genuinely relational queries
over document metadata, **(c)** a text source-of-truth separate from the
index. None is in scope. Related but distinct trigger: **server-side
reindexing without re-upload** would require persisting original PDFs at
ingestion — a blob directory, still not a relational DB. Uploaded PDFs are
currently extracted and discarded; the eval corpus lives in `case_files/`,
so evals can always re-ingest.

# Deferred: the image pipeline

`write_images=True` writes image files to a configurable directory and
inserts `![](path)` refs inline.[^corpus-findings] Enabled naively it would
**hurt** the baseline: path strings inside `chunk.text` become embedding
noise. The sketched future shape — decided for real when the experiment
lands, eval-gated: asset directory keyed by `document_id`, image paths in
`chunk.metadata["images"]` (out of the embedded text), and
`kind="image_caption"` chunks produced by a multimodal captioner. The
`kind`/`metadata` extension points exist precisely so this lands without
breaking the payload contract.

# Test plan (TDD, red-green per module)

| Test                                              | Against                                                                                    |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `tests/domain/test_ingestion_pipeline_service.py` | fakes of all three ports + fake chunker: orchestration, counts, chunk↔vector pairing       |
| `tests/ingestion/test_chunking.py`                | pure function: sizes, overlap, page/section propagation, deterministic IDs, `index_in_doc` |
| `tests/ingestion/test_pymupdf4llm_extractor.py`   | tiny PDF generated in-test (pymupdf): page numbers, text, section breadcrumb               |
| `tests/retrieval/test_qdrant_store.py`            | `QdrantClient(":memory:")`: add, payload contents, upsert idempotency, pairing invariant   |
| `tests/retrieval/test_openai_embedder.py`         | mocked OpenAI client: batching, vector order                                               |
| `tests/api/test_documents_route.py`               | TestClient + dependency overrides: contract shape, 422 non-PDF, multiple files             |
| route→pipeline integration                        | real extractor + real chunker, fake embedder, `:memory:` Qdrant, tiny generated PDF        |

Embedding/retrieval _accuracy_ belongs to the evals over the golden
dataset, not to unit tests ([Development
Workflow](/docs/development-workflow.md)).

[^challenge]: Challenge Brief — API contract for `POST /documents`.

[^decision-0005]:
    0005 — Retrieval architecture: ports, the persisted-chunk
    contract this spec extends, Qdrant selection.

[^corpus-findings]:
    Case Files Corpus Findings — CESTARI broken CMap behavior, measured
    pymupdf4llm 1.28.2 `page_chunks` schema and `write_images` behavior.

[^retrieval-evidence]:
    Retrieval Strategy Evidence — chunk-sizing evidence grounding the
    fixed-size starting point.
