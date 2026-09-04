---
type: Decision
title: 0014 — Error semantics: one body shape, four statuses, fail-fast startup, a readiness check and a documented OpenAPI
description: Every API error is {"detail": "<one sentence naming the culprit and the fix>"} and the status says who is at fault — 422 the request (blank question, non-PDF, unreadable PDF, nothing indexed), 502 an LLM or embedding provider after the fallback or an unusable reply, 503 a dependency or the configuration (Qdrant unreachable or incompatible, provider key missing), 500 only as a catch-all that still names the exception and logs the traceback; adapters translate infrastructure failures into domain errors (UnreadableDocument) or keep the library's typed exceptions, the extractor rejects corrupt, password-protected and page-less PDFs, ingestion extracts every file before storing any, a malformed structured reply is requested once more before it is a 502 (reversing the deliberate 500 of Decision 0009), the FastAPI lifespan validates the configuration and the vector store at startup so make up fails naming the missing key, make check-env refuses empty keys, GET /health reports the vector store, the indexed chunk count and the configured models, and every route and model carries summaries, descriptions, real examples and the declared error statuses.
tags: [api, errors, openapi, developer-ux, startup, health, fastapi, pydantic-ai, qdrant]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-03T00:40:00Z }
sources:
  - id: challenge
    resource: /docs/challenge.pdf
    title: Challenge Brief
  - id: golden-rules
    resource: /docs/golden-rules.md
    title: Golden Rules
  - id: decision-0009
    resource: /docs/decisions/0009-structured-reply-function-tools.md
    title: 0009 — Structured agent reply, function-derived tools, chunk ids as citation handles
  - id: decision-0010
    resource: /docs/decisions/0010-developer-ux-setup-path.md
    title: 0010 — Developer UX: the setup path
  - id: llm-module
    resource: /src/llm/llm.md
    title: LLM Module
  - id: ingestion-module
    resource: /src/ingestion/ingestion.md
    title: Ingestion Module
  - id: arch
    resource: /docs/architecture.md
    title: System Architecture — Ports & Adapters Lite
  - id: findings
    resource: /evals/results/experiment-findings.md
    title: Eval Experiment Findings
---

# Context

A first-run review of the repository (2026-09-02) walked
every failure a user could hit in the first ten minutes and provoked
each one. Eight of them reached the client as FastAPI's bare
`Internal Server Error`: a PDF with a `%PDF` header but corrupt content
(`pymupdf.FileDataError`), a truncated PDF that opens with zero pages
(`IndexError` inside pymupdf4llm), Qdrant unreachable
(`ResponseHandlingException`), a collection of another vector size (the
store's `ValueError`, on the first request), an empty `OPENAI_API_KEY` or
`GEMINI_API_KEY` (`pydantic_ai.exceptions.UserError` on the first
question or upload — with a message naming `GOOGLE_API_KEY`, a variable
the README never mentions), an unknown `EMBEDDING_MODEL` or
`LLM_THINKING` value, a malformed structured reply (1 case in 93 on the
answer eval[^findings]), and the tool-round cap. Two of those were
deliberate: [Decision 0009](/docs/decisions/0009-structured-reply-function-tools.md)
chose a 500 for a schema-violating reply "so it is investigated, not
retried", and the LLM module documented configuration errors as "500 on
purpose".[^decision-0009][^llm-module] The OpenAPI page showed
auto-generated summaries ("Upload Documents"), no descriptions, no
examples and no error statuses — while the **API Design** priority reads
"clear, documented, intuitive endpoints" and **Developer UX** "easy to set
up, test, and understand".[^golden-rules]

The owner's direction: format the OpenAPI documentation and minimise the
chance that anyone calling the API ever sees a generic 500.

# Decision

## 1. One body shape, four statuses, and the status says who is at fault

Every error the API returns is `{"detail": "<one sentence>"}` — including
FastAPI's request-validation errors, which are flattened from their list
form to `question: String should have at least 1 character`. The status
codes:

- **422** — the request: blank question, a file that is not a PDF, a PDF
  that cannot be read (corrupt, password-protected, no pages). The message
  names the file and the reason. Nothing is indexed.
- **502** — an LLM or embedding provider failed after the fallback
  (`ModelAPIError`, `FallbackExceptionGroup`, `openai.OpenAIError`), or
  the LLM's reply could not be used (`UnexpectedModelBehavior`,
  `ToolRoundsExhausted`). The provider or model is named.
- **503** — a dependency or the configuration: the vector store cannot be
  reached (`qdrant_client.http.exceptions.ApiException`, the message
  carries `QDRANT_URL`), its collection does not match the configured
  embedding model (`IncompatibleCollection`, the message says to delete
  it), or a provider key is missing (`UserError`, with `GOOGLE_API_KEY`
  rewritten to the `GEMINI_API_KEY` the README documents).
- **500** — only the catch-all, and even then
  `internal error: <ExceptionType>: <message>` with the traceback logged
  under `api.errors`. A 500 without a message no longer exists.

The mapping lives in one module, `src/api/errors.py`, registered on the
app by `register_exception_handlers`; routes stay thin (architecture
rule 5).[^arch]

## 2. Adapters translate; the domain names its own failures

`src/domain/errors.py` holds the domain's exceptions: `UnreadableDocument
(filename, reason)` and `ToolRoundsExhausted(rounds)`. The extractor
adapter translates every `RuntimeError` pymupdf raises while opening a
stream, a document that `needs_pass` and a document with zero pages into
`UnreadableDocument`, so the route can answer 422 with the file's name
without importing pymupdf. Library exceptions that already carry the
right meaning (`ModelAPIError`, `UnexpectedModelBehavior`, `UserError`,
`ApiException`) are not wrapped; the Qdrant store's incompatibility check
raises its own `IncompatibleCollection(ValueError)` so the edge can tell
it from any other `ValueError`.

## 3. Ingestion extracts every file before it stores any

`IngestionPipelineService.ingest` runs in two phases — extract and chunk
all files, then embed and store them — so an unreadable second file aborts
the upload before the first file is indexed, and the README's
"all-or-nothing" is true. The per-file progress log keeps its lines; the
extraction lines now come before the indexing lines.[^ingestion-module]

## 4. A malformed reply is requested once more, then a 502

`PydanticAiLLM.complete` requests the model again when `validate_json`
rejects a text reply, and raises `UnexpectedModelBehavior` with the
offending body only when the second attempt fails too; both attempts count
in `Usage`. This reverses Decision 0009's deliberate 500: a strict native
schema makes a malformed reply rare (1 in 93), so one retry hides it from
the caller at no cost on the happy path, and when it persists the
status names the model rather than the server.[^decision-0009]

## 5. Fail at startup, not on the first request

The FastAPI lifespan calls `validate_configuration()` at the composition
root: `EMBEDDING_MODEL` and `LLM_THINKING` values, then each provider key
a configured model needs (`OPENAI_API_KEY` for `openai:` models;
`GEMINI_API_KEY` or `GOOGLE_API_KEY` for `google:` ones — the message says
which setting needs it and to fill `.env`), then the LLM is built and the
vector store reached and its collection checked. A failure is logged as
`startup failed: …` and re-raised, so uvicorn exits with the message in
the `make up` terminal before any upload. One layer earlier,
`make check-env` refuses a `.env` whose keys are empty, naming the
variable (extending [Decision 0010](/docs/decisions/0010-developer-ux-setup-path.md)'s
rule that a failed prerequisite names the next command).[^decision-0010]

## 6. `GET /health` is a readiness check

It answers `{"status": "ok", "vector_store": "ok", "indexed_chunks": N,
"llm_model": …, "embedding_model": …}`, touching Qdrant on each call, and
a 503 with the vector-store message when Qdrant is unreachable — the
first `curl` when something fails.

## 7. The OpenAPI document is documentation

`FastAPI(title, summary, description, version, openapi_tags)` explains the
two-step flow and the error semantics; every route has a `summary`, a
`description`, a tag, a `response_description` and `responses` declaring
422, 500, 502 and 503 with `ErrorResponse` and a real example; every
request and response model carries field descriptions and the README's
real examples (including the refusal with empty `references`). The
challenge's wire contract is unchanged, byte for byte.

# Alternatives rejected

- **Serving with an invalid configuration and answering 503 per request.**
  Quieter than a startup failure; it would surface on the first upload
  instead of in the `make up` terminal.
- **Keeping the 500 for schema violations** (Decision 0009). The strict
  schema makes the event rare, but the eval showed it happens; "investigate,
  not retry" is the right posture for a bug and the wrong one for a
  provider hiccup in front of a user.
- **Catching pymupdf's exceptions in the route.** The domain must stay free
  of the library, and the route would not have the filename the message
  needs; the adapter is where infrastructure exceptions become domain
  language.
- **A `500` catch-all without the exception's name.** Hiding the type
  protects internals; when whoever hits the error is running the code
  locally, a named failure is worth more than the secrecy.
- **A per-request check of the LLM provider in `/health`.** It would cost
  an LLM call per probe; the health check reports the configured model
  names and leaves the provider to the first question.

# Consequences

- Rules served: **API Design** (documented, self-describing endpoints
  and one error shape), **Developer UX** (setup mistakes fail at
  `make check-env` or `make up` naming the fix; `/health` says what is
  down), **Functionality** (an intermittent malformed reply no longer
  fails a question), **Code Quality** (the edge maps exceptions in one
  module; adapters own the translation).
- Costs: the unreachable `ToolRoundsExhausted` path and two more
  exception classes to keep in the domain; a startup that depends on
  Qdrant being up (compose already gates the API on its healthcheck); the
  catch-all names exception types to the client.
- Superseded: Decision 0009's deliberate 500 for a schema-violating
  reply, and the LLM module's "configuration errors are 500 on purpose";
  both carry pointers here.
- Tests: one per handler at the edge, the lifespan against a broken
  environment, the extractor against corrupt, password-protected and
  page-less PDFs, the two-phase pipeline against a rejecting extractor,
  the adapter against a provider that fails once and one that fails
  twice, and a test that reads the OpenAPI document and checks every
  operation's summary, description, tag, error statuses and examples.

[^findings]: Eval Experiment Findings — chain 5's malformed-reply incident (1 in 93).

[^decision-0009]: 0009 — the deliberate 500 for a schema-violating reply, reversed here.

[^decision-0010]: 0010 — the setup rule this decision extends to the keys and to startup.

[^llm-module]: LLM Module — the adapter's retry, the exception classes and how they reach the edge.

[^ingestion-module]: Ingestion Module — the extractor's unreadable-document rules and the two-phase pipeline.

[^arch]: System Architecture — rule 5 (thin routes) and rule 11 (adapters translate exceptions).

[^golden-rules]: Golden Rules — API Design and Developer UX.
