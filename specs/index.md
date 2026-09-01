# Specs

Approved designs for subsystems before they are built. A spec is the
output of a design session; its durable choices are distilled into
[decision records](/docs/decisions/) once settled.

- [Naive Ingestion Baseline — Design](ingestion-baseline-design.md) - Approved design for the first functional POST /documents — a deliberately naive pipeline (pymupdf4llm extraction without OCR, fixed-size chunking, OpenAI embeddings, Qdrant) whose entities and payload carry explicit extension points (kind, metadata) so eval-driven improvements swap pieces without redesign.
- [Eval Structure & Golden Dataset — Design](eval-structure-design.md) - Approved design for the eval layer — adopted metrics split into deterministic gates and LLM-judged diagnostics, the golden-dataset case schema with chunking-independent ground truth, case taxonomy and per-document distribution, file layout, and the authoring process.
- [Eval Harness — Design & Implementation Plan](eval-harness-design.md) - Approved design for the retrieval-eval harness — a pure metric core under src/evaluation/ fed by ranked chunks, matching with a 0.6 token-overlap threshold, the minimal read-side slice (VectorStore.search, Retriever port, VectorRetriever), an in-process runner with skip-if-populated ingestion, committed JSON results, and the ordered TDD implementation plan.
- [Question Agent — Design & Implementation Plan](question-agent-design.md) - Approved design for POST /question — the domain LLM vocabulary and LLM port, the AgentService dual-path flow (seed retrieval + bounded query_knowledge tool loop) with the [i]-citation / NO_ANSWER protocol, the PydanticAI direct adapter, the thin route, composition/config — plus the ordered TDD implementation plan; no separate plan document exists.
