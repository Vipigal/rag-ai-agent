---
type: Reference
title: Challenge Brief — ML Engineering (LLM)
description: The interview challenge this repo solves — a RAG system for question answering over uploaded PDFs — with its required API contract and deliverables.
tags: [challenge, requirements, api]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T02:55:04Z }
verified: { by: human:vinicius, at: 2026-08-31T18:34:00Z }
sources:
  - id: challenge-pdf
    resource: /docs/challenge.pdf
    title: "[Challenge] Machine Learning Engineering - LLM"
---

# Case

Build a system that allows users to upload PDF documents and later ask
questions about their contents. The solution must extract information from
the documents, store it in a way that allows efficient retrieval, and use an
LLM to answer user questions accurately.[^challenge-pdf]

Tools, libraries, and frameworks are free choices. The evaluators are most
interested in how the solution is structured, how well it demonstrates
understanding of retrieval-augmented generation (RAG), and how the
components integrate into a working system.

# Required features

- Upload PDF documents and extract their contents.
- Chunk and embed document text for semantic search.
- Store embeddings for later retrieval.
- Ask questions based on the uploaded content.
- Use an LLM to answer questions with contextual accuracy.

# API contract

## POST /documents

Upload one or more PDF documents to be indexed.

Request: `multipart/form-data` with one or more PDF files under the field
name `files`.

Response:

```json
{
  "message": "Documents processed successfully",
  "documents_indexed": 2,
  "total_chunks": 128
}
```

## POST /question

Request: `application/json`.

```json
{
  "question": "What is the power consumption of the motor?"
}
```

Response — note that `references` carries the retrieved source excerpts
that ground the answer:

```json
{
  "answer": "The motor's power consumption is 2.3 kW.",
  "references": [
    "the motor xxx has requires 2.3kw to operate at a 60hz line frequency"
  ]
}
```

# Optional enhancements

- Basic frontend or Streamlit interface.
- Support multiple LLM providers or fallback behavior.
- Logging, stats, or latency metrics.
- Dockerized environment or Makefile.

# Deliverables

- A GitHub repository with the complete implementation.
- Clear instructions to set up and run the project.
- Example requests and expected responses.
- Any extra requirements, environment variables, or API keys needed to run
  the code. LLM provider keys should be listed as necessary; the evaluators
  will supply one to test.

# Evaluation

Submissions are judged on six criteria. They are adopted in this repo as
the [Golden Rules](/docs/golden-rules.md) — every change is weighed against them.

# Test corpus

The `case_files/` directory at the repo root holds real PDFs (WEG motor
manuals and specification guides, in Portuguese and English) suitable as an
indexing and evaluation corpus. The example question in the API contract
("power consumption of the motor") is answerable from this corpus.

[^challenge-pdf]: [Challenge] Machine Learning Engineering - LLM
