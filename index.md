---
okf_version: "0.2"
---

Human readers: start with [README.md](README.md), the curated five-minute
path through this bundle. Agents start here.

# Project North

- [Golden Rules](docs/golden-rules.md) - The six priorities every change in this repo is weighed against, and what each means in practice.

# Process

- [Development Workflow](docs/development-workflow.md) - Testing-first and eval-first: how modules get built (TDD) and how system accuracy gets measured (evals).
- [Authoring Guide](docs/authoring-guide.md) - How to add knowledge to this bundle: co-location with code, what deserves documentation, and the OKF conventions.

# Architecture

- [System Architecture — Ports & Adapters Lite](docs/architecture.md) - The operating map of the codebase: structure, concepts, rules, and how to extend the system. Read before implementing any module.
- [Project Glossary](docs/glossary.md) - The ubiquitous language of the system — one word per concept across code, bundle and evals, with the words to avoid.

# Decisions

- [Decisions](docs/decisions/) - Architecture and project decisions, one concept per decision, numbered chronologically.

# Modules

Module knowledge is co-located with module code: each module directory
carries its own concepts and, once it holds two or more, an `index.md`
(see the [Authoring Guide](docs/authoring-guide.md)).

- [Ingestion Module](src/ingestion/ingestion.md) - The write path: font repair before extraction, page cleaning after it, one chunk per page, and the small units the embedder sees — with the rules the code cannot state and the experiments that shaped them.
- [Retrieval Module](src/retrieval/retrieval.md) - The read side: the embedder over one `EMBEDDING_MODEL` value, the Qdrant multivector store scored by MaxSim, and the one `Retriever` strategy — with what switching the embedder costs and how to test it all without Docker.
- [LLM Module](src/llm/llm.md) - The LLM port's adapter: one provider call per `complete()` offering function-derived tools and demanding a structured reply — plus the sync-only constraint, the fallback wiring, the reasoning-effort default and where every exception lands at the API edge.
- [Golden Dataset](evals/golden/golden-dataset.md) - The 93-case dataset: what each YAML file covers, page-numbering and transcription semantics per PDF, the canary roles, and the rules a case is written by.
- [Eval Harness Module](src/evaluation/evaluation.md) - How to run the retrieval eval and the answer layer, the thresholds and exclusion rules, the answer gates, the efficiency block, and the owner-as-judge workflow.
- [Eval Experiment Findings](evals/results/experiment-findings.md) - What every committed run taught and why: the seven chains that took recall@5 from 0.65 to 0.95, which cases flipped and the mechanism behind each move, the negative results, and the probes taken before building.

# Research

- [Research](docs/research/) - Evidence that grounds decisions: corpus findings and cited external evidence, kept as a backlink source for decision records and module concepts.

# References

- [OKF Specification v0.2](docs/okf-spec.md) - The documentation format this bundle is written in.
