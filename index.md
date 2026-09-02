---
okf_version: "0.2"
---

# Project North

- [Challenge Brief](docs/challenge.md) - What the system must do: the case, required features, API contract, and deliverables.
- [Golden Rules](docs/golden-rules.md) - The challenge's evaluation criteria, adopted as the non-negotiable priorities of every change in this repo.

# Process

- [Development Workflow](docs/development-workflow.md) - Testing-first and eval-first: how modules get built (TDD) and how system accuracy gets measured (evals).
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

- [Ingestion Module](src/ingestion/ingestion.md) - The write path's extraction and chunking stage — pymupdf4llm adapter with TOC-breadcrumb sections and the fixed-size chunker, deliberately naive per Decision 0007, with the CESTARI broken-text behavior indexed on purpose as the eval baseline.
- [Golden Dataset](evals/golden/golden-dataset.md) - Co-located overview of the 93-case golden dataset — what each YAML file covers, page-numbering and transcription semantics per source PDF, each file's canary role, and the semantics of negative cases.
- [Eval Harness Module](src/evaluation/evaluation.md) - How to run the retrieval eval (make eval / make eval-fresh) and what its code cannot say — the eval-collection re-ingestion procedure, the 0.6 token-overlap threshold and the containment subsumption, exclusion rules, the human-readable per-case results schema, and the baseline findings including the partially-broken CESTARI text layer and the cross-lingual failure axis.
- [LLM Module](src/llm/llm.md) - The LLM port's adapter stage — PydanticAiLLM over pydantic_ai.direct, one provider call per complete() that offers function-derived strict tools and demands the AgentReply schema as native structured output — and what its code cannot say: the sync-only constraint that keeps the question route a plain def, schema derivation and validation with TypeAdapter, message grouping and tool_name-by-id resolution, which exceptions reach the API edge as 502 versus 500, that openai: resolves to the Responses API, the FallbackModel path, and how to test against FunctionModel.

# Specs

- [Specs](specs/) - Approved designs for subsystems before they are built; distilled into decision records as choices settle.

# Research

- [Research](research/) - Evidence that grounds decisions: corpus findings and cited external evidence, kept as a backlink source for decision records and module concepts.

# References

- [OKF Specification v0.2](okf_spec.md) - The documentation format this bundle is written in.
