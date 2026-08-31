# Specs

Approved designs for subsystems before they are built. A spec is the
output of a design session; its durable choices are distilled into
[decision records](/docs/decisions/) once settled.

- [Naive Ingestion Baseline — Design](ingestion-baseline-design.md) - Approved design for the first functional POST /documents — a deliberately naive pipeline (pymupdf4llm extraction without OCR, fixed-size chunking, OpenAI embeddings, Qdrant) whose entities and payload carry explicit extension points (kind, metadata) so eval-driven improvements swap pieces without redesign.
- [Eval Structure & Golden Dataset — Design](eval-structure-design.md) - Approved design for the eval layer — adopted metrics split into deterministic gates and LLM-judged diagnostics, the golden-dataset case schema with chunking-independent ground truth, case taxonomy and per-document distribution, file layout, and the authoring process.
