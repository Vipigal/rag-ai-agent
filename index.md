---
okf_version: "0.2"
---

Human readers: start with [README.md](README.md), the curated five-minute
path through this bundle. Agents start here.

# Project North

- [Challenge Brief](docs/challenge.md) - What the system must do: the case, required features, API contract, and deliverables.
- [Golden Rules](docs/golden-rules.md) - The challenge's evaluation criteria, adopted as the non-negotiable priorities of every change in this repo.

# Process

- [Development Workflow](docs/development-workflow.md) - Testing-first and eval-first: how modules get built (TDD) and how system accuracy gets measured (evals).
- [Next Steps — Handoff from the 2026-09-02 session](docs/next-steps.md) - The ordered work for the sessions after 2026-09-02 — the reading path to review what landed, the five-step story of the retrieval gains (recall@5 0.65 → 0.95) with the why behind each for the oral exam, the code-review checklist with the open design questions, the citation-excerpt problem that page-level chunks created against the challenge's reference contract, the end-to-end test procedure, and the decisions and experiments still pending.
- [Authoring Guide](docs/authoring-guide.md) - How to add knowledge to this bundle: co-location with code, what deserves documentation, and the OKF conventions.

# Architecture

- [System Architecture — Ports & Adapters Lite](docs/architecture.md) - The operating map of the codebase: structure, concepts, rules, and how to extend the system. Read before implementing any module.
- [Project Glossary](docs/glossary.md) - The ubiquitous language of the RAG question-answering system — one word per concept across code, bundle and evals, with the words to avoid.

# Decisions

- [Decisions](docs/decisions/) - Architecture and project decisions, one concept per decision, numbered chronologically.

# Modules

Module knowledge is co-located with module code: each module directory
carries its own concepts and, once it holds two or more, an `index.md`
(see the [Authoring Guide](docs/authoring-guide.md)). Entries appear here
as the tree grows.

- [Ingestion Module](src/ingestion/ingestion.md) - The write path's extraction and chunking stage — pymupdf4llm behind a font-repair pre-pass (ToUnicode CMaps from fontTools' standard glyph order for fonts that lack one, no OCR) and a page-cleaning post-pass (running headers, page numbers, dot leaders), sections from the PDF outline or from markdown headings, one chunk per page, and the small units (paragraphs, table rows) the embedder sees for each chunk — with the rules the code cannot state, the measured corpus numbers and the experiments that shaped them.
- [Retrieval Module](src/retrieval/retrieval.md) - The read side's adapters — PydanticAiEmbeddingModel over pydantic-ai's Embedder (OpenAI or Google behind one EMBEDDING_MODEL value, documents and queries embedded with their task types, batched per provider), QdrantVectorStore holding one multivector point per chunk scored by MaxSim (upserts batched under Qdrant's JSON limit, incompatible collections refused with the fix named) and VectorRetriever, the one Retriever strategy — with what the code cannot say: why the query is a one-row multivector, why the vector size is a registry at the composition root, what switching the embedder costs, the measured numbers, and how to test all of it without Docker.
- [Golden Dataset](evals/golden/golden-dataset.md) - Co-located overview of the 93-case golden dataset — what each YAML file covers, page-numbering and transcription semantics per source PDF, each file's canary role, and the semantics of negative cases.
- [Eval Harness Module](src/evaluation/evaluation.md) - How to run the retrieval eval (make eval / make eval-fresh) and what its code cannot say — the eval-collection re-ingestion procedure, the 0.6 token-overlap threshold and the containment subsumption, exclusion rules, the human-readable per-case results schema, the baseline findings (CESTARI text layer, cross-lingual axis), and where every later run's reading lives (evals/results/experiment-findings.md).
- [Eval Experiment Findings](evals/results/experiment-findings.md) - What each committed eval run taught and why — the 2026-09-02 ingestion chain step by step (font repair, page cleaning, structured chunking, contextualized embeddings) the chunking-core chain that followed (fontTools refactor proven equivalent, page chunks with per-unit vectors at +0.05 recall) and the embedder chain (gemini-embedding-001 at +0.09 recall, six of eleven cross-lingual cases, 8× the token price in cents), with the cases that flipped and the mechanism behind each move, the negative results (standalone tables, boundary variants at the dataset's noise floor), the discoveries made along the way, and the failure axes that remain, so the next experiment starts from evidence instead of intuition.
- [LLM Module](src/llm/llm.md) - The LLM port's adapter stage — PydanticAiLLM over pydantic_ai.direct, one provider call per complete() that offers function-derived strict tools and demands the AgentReply schema as native structured output — and what its code cannot say: the sync-only constraint that keeps the question route a plain def, schema derivation and validation with TypeAdapter, message grouping and tool_name-by-id resolution, which exceptions reach the API edge as 502 versus 500, that openai: resolves to the Responses API, the FallbackModel wiring and why gemini-3.5-flash is the fallback, and how to test against FunctionModel.

# Specs

- [Specs](specs/) - Approved designs for subsystems before they are built; distilled into decision records as choices settle.

# Research

- [Research](research/) - Evidence that grounds decisions: corpus findings and cited external evidence, kept as a backlink source for decision records and module concepts.

# References

- [OKF Specification v0.2](docs/okf-spec.md) - The documentation format this bundle is written in.
