---
type: Glossary
title: Project Glossary
description: The ubiquitous language of the RAG question-answering system — one word per concept across code, bundle and evals, with the words to avoid.
tags: [glossary, domain-language]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T02:38:25Z }
verified: { by: human:vinicius, at: 2026-09-02T02:40:00Z }
---

The language of a system that indexes uploaded PDFs as chunks and answers
questions about them with an LLM that cites what it read. Written after
the 2026-09-02 review settled that the answer path speaks of **chunks**,
never excerpts — the word "excerpt" belongs to the evaluation side only.
Module glossaries: none yet.

# Language

## Documents and chunks

**Document**:
A PDF uploaded through the API; the unit of indexing, identified by its content.
_Avoid_: file, upload, manual (the corpus happens to be manuals; the system is generic)

**Chunk**:
A piece of one document's text carrying its provenance (document, page, section), stored and retrieved as a unit; the only thing the model ever reads from the corpus.
_Avoid_: excerpt, passage, fragment, snippet

**Section**:
The breadcrumb of outline headings a chunk sits under, outermost first.
_Avoid_: heading path, TOC entry

## Retrieval

**Retriever**:
The strategy that turns a query into ranked chunks.
_Avoid_: search, vector store (that is persistence, not strategy)

**Retrieved chunk**:
A chunk together with the score it was ranked by and the retrieval source that produced it.

**Retrieval source**:
Which path produced a retrieved chunk — `seed` or `tool`.
_Avoid_: origin, path

**Seed retrieval**:
The retrieval run with the user's question itself, before the model speaks.
_Avoid_: initial search, pre-fetch, first pass

**query_knowledge**:
The one tool the model may call: a retrieval with a query of its own over the same retriever.
_Avoid_: search tool, lookup, RAG tool

## Answering

**Reply**:
What the model returns at the end of its turn — the answer text, its citations, and whether it found an answer at all.
_Avoid_: output, response (that is HTTP), completion (that is the port's return: a reply or a tool request)

**Citation**:
A chunk id the model names as grounding its reply.
_Avoid_: marker, source

**Refusal**:
A reply that found no answer in the chunks: a one-sentence explanation in the question's language, no references.
_Avoid_: fallback, empty answer, no-answer

**Tool round**:
One iteration of the model requesting a tool and receiving its result; the number of rounds per question is capped.
_Avoid_: step, turn (a turn is one message), iteration

**Answer**:
The system's result for a question — the answer text and its references — the thing the API returns.
_Avoid_: reply (that is the model's), result

**Reference**:
A cited chunk returned with the answer; on the wire, its verbatim text.
_Avoid_: source (overloaded with OKF `sources`), excerpt

## Evaluation

**Golden case**:
A hand-authored question with the gold excerpts and reference answer it is judged against.
_Avoid_: test case, sample

**Gold excerpt**:
A human-transcribed verbatim passage of a document, with its page, that a relevant chunk must contain; a truth marker, never a chunk.
_Avoid_: excerpt for anything on the answer path, snippet

**Canary**:
A golden-dataset slice expected to fail on purpose so the eval proves it can see the failure (today: the CESTARI broken text layer).
_Avoid_: negative case (that is an unanswerable question)
