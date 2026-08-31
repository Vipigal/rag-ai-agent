---
type: Reference
title: Retrieval Strategy Evidence
description: External evidence gathered 2026-08-31 on hybrid search (BM25 + vectors), small-to-big / parent-document retrieval, chunk sizing, and PDF-parser benchmarks, to ground future chunking/retrieval decisions.
tags: [retrieval, hybrid-search, chunking, benchmarks, pdf-extraction]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T19:05:00Z }
verified: { by: human:vinicius, at: 2026-08-31T19:48:00Z }
sources:
  - id: azure-hybrid
    resource: https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/azure-ai-search-outperforming-vector-search-with-hybrid-retrieval-and-reranking/3929167
    title: "Azure AI Search: Outperforming vector search with hybrid retrieval and ranking (2023-09-18)"
  - id: anthropic-contextual
    resource: https://www.anthropic.com/news/contextual-retrieval
    title: Anthropic — Introducing Contextual Retrieval (2024-09-19)
  - id: beir
    resource: https://arxiv.org/abs/2104.08663
    title: "Thakur et al. — BEIR: Zero-shot Evaluation of IR Models (NeurIPS 2021)"
  - id: rrf
    resource: https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
    title: Cormack, Clarke & Büttcher — Reciprocal Rank Fusion (SIGIR 2009)
  - id: elastic-hybrid
    resource: https://www.elastic.co/search-labs/blog/improving-information-retrieval-elastic-stack-hybrid
    title: Elastic — Hybrid retrieval (2023-07-20)
  - id: llamaindex-recursive
    resource: https://developers.llamaindex.ai/python/examples/retrievers/recursive_retriever_nodes/
    title: LlamaIndex — Recursive Retriever + Node References (small-to-big)
  - id: llamaindex-automerge
    resource: https://developers.llamaindex.ai/python/examples/retrievers/auto_merging_retriever/
    title: LlamaIndex — Auto Merging Retriever eval
  - id: llamaindex-prod
    resource: https://developers.llamaindex.ai/python/framework/optimizing/production_rag/
    title: LlamaIndex — Building Performant RAG for Production
  - id: langchain-pdr
    resource: https://reference.langchain.com/python/langchain-classic/retrievers/parent_document_retriever/ParentDocumentRetriever
    title: LangChain — ParentDocumentRetriever reference
  - id: aragog
    resource: https://arxiv.org/abs/2404.01037
    title: "Eibich et al. — ARAGOG: Advanced RAG Output Grading (2024)"
  - id: rag-best-practices
    resource: https://arxiv.org/abs/2407.01219
    title: Wang et al. — Searching for Best Practices in RAG (EMNLP 2024)
  - id: nvidia-chunking
    resource: https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/
    title: NVIDIA — Finding the Best Chunking Strategy (2025-06-18)
  - id: omnidocbench
    resource: https://arxiv.org/abs/2412.07626
    title: OmniDocBench (CVPR 2025) + leaderboard github.com/opendatalab/OmniDocBench
  - id: olmocr-bench
    resource: https://github.com/allenai/olmocr
    title: Allen AI — olmOCR & olmOCR-Bench
  - id: docling-report
    resource: https://arxiv.org/abs/2408.09869
    title: Docling Technical Report
  - id: procycons
    resource: https://procycons.com/en/blogs/pdf-data-extraction-benchmark/
    title: Procycons — PDF Data Extraction Benchmark (2025-03-24)
---

# Why this document exists

Chunking/retrieval decisions in this repo must be eval-first and
justified (see [Golden Rules](/docs/golden-rules.md)). This concept
records the external evidence collected on 2026-08-31 so decision
records can cite it instead of re-researching. Numbers below are as
reported by each source; our own evals over `case_files/` remain the
final arbiter.

# Hybrid search (BM25 + dense vectors)

- Azure AI Search study[^azure-hybrid] (ada-002 embeddings, RRF fusion):
  customer-dataset NDCG@3 — keyword 40.6, vector 43.8, hybrid 48.4,
  hybrid + semantic ranker 60.1. Decisive for this corpus: on "keyword
  queries" (exact identifiers) pure vector collapses to **11.7 vs 79.2**
  for keyword search; hybrid recovers to 61.0.
- Anthropic Contextual Retrieval[^anthropic-contextual]: contextual
  embeddings −35% top-20 retrieval failures (5.7%→3.7%); + contextual
  BM25 −49% (→2.9%); + reranking −67% (→1.9%). Also the "Error code
  TS-999" argument: embeddings alone miss exact-string matches.
- BEIR[^beir]: BM25 is a robust zero-shot baseline; dense retrievers
  often underperform out of domain — motors/gearbox manuals are exactly
  out-of-domain for general embedding models.
- RRF[^rrf]: `score(d) = Σ 1/(k + rank(d))`, k=60; beats the best
  individual system and Condorcet/CombMNZ by 4–5% on TREC/LETOR.
- Elastic[^elastic-hybrid]: BM25+ELSER via RRF ≥ either alone on all
  BEIR subsets tested (+18% NDCG@10 over BM25 alone).

# Small-to-big / parent-document retrieval

- LlamaIndex recursive retriever (chunk references 128/256/512 → 1024
  parent)[^llamaindex-recursive]: hit-rate 0.778→0.897, MRR 0.563→0.691
  vs flat retrieval. Design principle ("decouple chunks used for
  retrieval from those used for synthesis") in the production RAG
  guide.[^llamaindex-prod] LangChain ships it as
  `ParentDocumentRetriever`.[^langchain-pdr]
- ARAGOG[^aragog]: sentence-window retrieval had the best retrieval
  precision (+0.1134 vs naive, p<0.0001) but _mediocre answer
  similarity_ — retrieval gains don't automatically become answer
  gains.
- Wang et al.[^rag-best-practices]: small2big and sliding window
  improve faithfulness/relevancy by ~1–2 points; sliding window edged
  out small2big.
- Honest caveat: LlamaIndex's own auto-merging eval is ~neutral
  ("results are roughly the same", pairwise 0.525).[^llamaindex-automerge]
- Chunk size: NVIDIA's 5-dataset study[^nvidia-chunking] found
  page-level (~medium) chunks best on average (0.648 accuracy); 128 and
  2048-token extremes underperform.

# PDF parser benchmarks (2024–2026)

- olmOCR-Bench[^olmocr-bench] (most independent): olmOCR 82.4, Marker
  76.1, MinerU 75.2, Mistral OCR API 72.0. Tables: olmOCR 84.9, Marker
  72.9.
- OmniDocBench[^omnidocbench]: MinerU leads (TEDS 81.9–93.4) — but the
  benchmark is run by MinerU's own org (OpenDataLab); treat as
  partially self-reported. Docling/Unstructured/PyMuPDF not evaluated.
- Procycons[^procycons]: Docling 97.9% cell accuracy on a complex
  hierarchical table; Unstructured 75% on complex tables (+
  hallucinated content); LlamaParse 0% correct placement on complex
  tables (older mode). Docling ≈1.3 pages/s CPU.[^docling-report]
- Licensing: PyMuPDF4LLM AGPL-3.0; Docling MIT; Marker Apache-2.0 code
  - revenue-capped model weights; MinerU custom Apache-based; olmOCR
    Apache-2.0 (needs 12 GB+ GPU); LlamaParse ~$0.004/page; Mistral OCR
    $0.001/page.

[^azure-hybrid]: Azure AI Search hybrid retrieval study (2023-09-18)

[^anthropic-contextual]: Anthropic — Introducing Contextual Retrieval (2024-09-19)

[^beir]: Thakur et al. — BEIR (NeurIPS 2021)

[^rrf]: Cormack, Clarke & Büttcher — RRF (SIGIR 2009)

[^elastic-hybrid]: Elastic — Hybrid retrieval (2023-07-20)

[^llamaindex-recursive]: LlamaIndex — Recursive Retriever + Node References

[^llamaindex-automerge]: LlamaIndex — Auto Merging Retriever eval

[^llamaindex-prod]: LlamaIndex — Building Performant RAG for Production

[^langchain-pdr]: LangChain — ParentDocumentRetriever reference

[^aragog]: Eibich et al. — ARAGOG (arXiv 2404.01037)

[^rag-best-practices]: Wang et al. — Searching for Best Practices in RAG (arXiv 2407.01219)

[^nvidia-chunking]: NVIDIA — Finding the Best Chunking Strategy (2025-06-18)

[^omnidocbench]: OmniDocBench (arXiv 2412.07626)

[^olmocr-bench]: Allen AI — olmOCR-Bench

[^docling-report]: Docling Technical Report (arXiv 2408.09869)

[^procycons]: Procycons — PDF Data Extraction Benchmark (2025-03-24)
