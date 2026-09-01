# Research

Evidence gathered to ground decisions: empirical findings about this repo's
corpus and cited external evidence. Concepts here are `type: Reference` and
exist to be **cited via backlinks** — decision records and module concepts
point at them in `sources` entries instead of re-researching.

- [Case Files Corpus Findings](case-files-corpus-findings.md) - Empirical survey of the four case_files PDFs — languages, structure, extraction quality — including the broken text layer in the CESTARI manual and measured pymupdf4llm 1.28.2 behavior on this corpus.
- [Retrieval Strategy Evidence](retrieval-strategy-evidence.md) - External evidence gathered 2026-08-31 on hybrid search (BM25 + vectors), small-to-big / parent-document retrieval, chunk sizing, and PDF-parser benchmarks, to ground future chunking/retrieval decisions.
- [RAG Eval Metrics Evidence](rag-eval-metrics-evidence.md) - External evidence gathered 2026-08-31 on RAG evaluation metrics — retrieval (recall@k, MRR, precision, NDCG, MAP), answer quality (correctness, faithfulness, relevancy, citation quality), chunking-independent ground-truth encoding, LLM-as-judge pitfalls, and efficiency logging — to ground the golden-dataset and eval-harness decisions.
- [LLM Adapter Library Evidence](llm-adapter-library-evidence.md) - Evidence gathered 2026-09-01 comparing candidate libraries for the LLM port adapter — OpenAI SDK direct, LangChain deepagents (vs plain init_chat_model), Strands Agents, PydanticAI, LiteLLM — on loop ownership, dependency weight, latency-overhead evidence, multi-provider support, and maturity, against the domain-owned tool loop of Decision 0005.
