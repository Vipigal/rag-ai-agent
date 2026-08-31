---
type: Reference
title: RAG Eval Metrics Evidence
description: External evidence gathered 2026-08-31 on RAG evaluation metrics — retrieval (recall@k, MRR, precision, NDCG, MAP), answer quality (correctness, faithfulness, relevancy, citation quality), chunking-independent ground-truth encoding, LLM-as-judge pitfalls, and efficiency logging — to ground the golden-dataset and eval-harness decisions.
tags: [evals, metrics, retrieval, llm-as-judge, golden-dataset]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T21:33:12Z }
verified: { by: human:vinicius, at: 2026-08-31T22:55:00Z }
sources:
  - id: iir
    resource: https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html
    title: Manning, Raghavan & Schütze — Introduction to Information Retrieval, §8.4 (ranked retrieval evaluation)
  - id: trec8-qa
    resource: https://trec.nist.gov/pubs/trec8/papers/qa_report.pdf
    title: Voorhees — The TREC-8 Question Answering Track Report (NIST, 1999)
  - id: ndcg
    resource: https://dl.acm.org/doi/10.1145/582415.582418
    title: Järvelin & Kekäläinen — Cumulated Gain-Based Evaluation of IR Techniques (ACM TOIS 20(4), 2002)
  - id: ragas-paper
    resource: https://arxiv.org/abs/2309.15217
    title: "Es et al. — RAGAS: Automated Evaluation of Retrieval Augmented Generation (2023)"
  - id: ragas-cp
    resource: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/
    title: RAGAS docs — Context Precision
  - id: ragas-cr
    resource: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/
    title: RAGAS docs — Context Recall
  - id: ragas-entities
    resource: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_entities_recall/
    title: RAGAS docs — Context Entities Recall
  - id: ragas-noise
    resource: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/noise_sensitivity/
    title: RAGAS docs — Noise Sensitivity
  - id: ragas-faith
    resource: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
    title: RAGAS docs — Faithfulness
  - id: ragas-relevancy
    resource: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/
    title: RAGAS docs — Response Relevancy
  - id: ragas-correctness
    resource: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_correctness/
    title: RAGAS docs — Answer Correctness
  - id: deepeval-intro
    resource: https://deepeval.com/docs/metrics-introduction
    title: DeepEval docs — Metrics introduction
  - id: deepeval-cp
    resource: https://deepeval.com/docs/metrics-contextual-precision
    title: DeepEval docs — Contextual Precision
  - id: deepeval-cr
    resource: https://deepeval.com/docs/metrics-contextual-recall
    title: DeepEval docs — Contextual Recall
  - id: trulens-triad
    resource: https://www.trulens.org/getting_started/core_concepts/rag_triad/
    title: TruLens docs — The RAG Triad
  - id: llamaindex-eval
    resource: https://developers.llamaindex.ai/python/framework/module_guides/evaluating/
    title: LlamaIndex docs — Evaluating (retrieval + response modules)
  - id: promptfoo-rag
    resource: https://www.promptfoo.dev/docs/guides/evaluate-rag/
    title: promptfoo docs — Evaluating RAG pipelines
  - id: promptfoo-det
    resource: https://www.promptfoo.dev/docs/configuration/expected-outputs/deterministic/
    title: promptfoo docs — Deterministic assertions (contains, latency, cost)
  - id: openai-graders
    resource: https://developers.openai.com/api/docs/guides/graders
    title: OpenAI platform docs — Graders (string_check, text_similarity, score_model, python)
  - id: ares
    resource: https://arxiv.org/abs/2311.09476
    title: "Saad-Falcon et al. — ARES: An Automated Evaluation Framework for RAG (2023)"
  - id: llm-judge
    resource: https://arxiv.org/abs/2306.05685
    title: Zheng et al. — Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena (NeurIPS 2023)
  - id: geval
    resource: https://arxiv.org/abs/2303.16634
    title: "Liu et al. — G-Eval: NLG Evaluation using GPT-4 (2023)"
  - id: alce
    resource: https://arxiv.org/abs/2305.14627
    title: "Gao et al. — ALCE: Enabling LLMs to Generate Text with Citations (EMNLP 2023)"
---

# Why this document exists

The [Golden Rules](/docs/golden-rules.md) make retrieval quality an
independently evaluated criterion, and [Decision
0005](/docs/decisions/0005-retrieval-architecture.md) gates every
retrieval experiment (hybrid, rerank, small-to-big) on before/after evals.
This concept records the external evidence on which metrics to adopt,
weighed against this project's specifics: 4 trilingual manuals full of
exact identifiers, a hand/LLM-written golden dataset (question → ideal
answer + verbatim excerpts with doc + page), and **no fixed chunking** —
ground truth must survive re-chunking.

# Retrieval metrics

| Metric                          | Definition                                                                                                      | Ground truth needed                        | Fit verdict                                                                                                                                                    |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Recall@k                        | Fraction of the gold-relevant passages present in the top k                                                     | Binary labels, all relevant passages known | **Adopt — headline retrieval metric.** With 1–2 gold excerpts per question it is exact, cheap, deterministic                                                   |
| Hit rate (success@k)            | Share of queries with ≥1 relevant passage in top k[^llamaindex-eval]                                            | Binary, ≥1 relevant passage                | **Adopt.** Equals recall@k for single-excerpt questions; the number the seed-context path lives or dies by                                                     |
| Precision@k / context precision | Relevant fraction of top k; RAGAS rank-weights it: mean of precision@k at each relevant rank k[^ragas-cp][^iir] | Binary labels (or an LLM judge, below)     | **Adopt (secondary).** Measures prompt noise fed to the LLM; report, don't gate                                                                                |
| MRR                             | Mean over queries of 1/rank of the first relevant result, 0 if none[^trec8-qa]                                  | Binary, first-relevant only                | **Adopt.** Ideal for our mostly single-passage questions; rank-sensitive where hit rate is blind. Known limit: no credit for a 2nd relevant passage[^trec8-qa] |
| NDCG@k                          | DCG with graded gains discounted by log rank, normalized by ideal ranking[^ndcg][^iir]                          | **Graded** relevance labels                | **Skip.** Our synthetic labels are binary; NDCG's advantage only exists with graded judgments[^iir]                                                            |
| MAP                             | Mean of average precision (precision after each relevant doc retrieved); binary labels, multi-relevant[^iir]    | Binary, complete relevant set              | **Skip for now.** Adds value only when many questions have several gold passages; recall@k + MRR cover us                                                      |
| Context entities recall         | Entities common to reference and retrieved contexts / entities in reference; LLM-extracted[^ragas-entities]     | Reference answer (entities derived)        | **Adapt, deterministically:** for exact-identifier questions, store the expected identifiers and check containment in retrieved text — same idea, no LLM       |

Framework support: LlamaIndex `RetrieverEvaluator` computes hit rate, MRR,
precision, recall, AP and NDCG from (query, expected node ids/texts)
pairs and can synthesize datasets via
`generate_question_context_pairs`;[^llamaindex-eval] RAGAS ships LLM-judged
and non-LLM variants of context precision/recall;[^ragas-cp][^ragas-cr]
DeepEval's contextual precision/recall are LLM-judged against
`expected_output`;[^deepeval-cp][^deepeval-cr] promptfoo recommends
evaluating retrieval separately with `context-recall`/`context-relevance`
(LLM-graded) or plain `contains`-style assertions.[^promptfoo-rag]

# Ground-truth encoding robust to re-chunking

The central design problem: chunk IDs are worthless as ground truth here
because chunking will change. Practices found, ordered by robustness:

1. **Verbatim gold excerpts + containment/overlap matching.** Store the
   supporting excerpt text; a retrieved chunk is relevant if it contains
   the (whitespace-normalized) excerpt, or exceeds a token-overlap
   threshold when chunk boundaries split an excerpt. promptfoo's
   deterministic `contains`/`icontains`/`levenshtein` assertions[^promptfoo-det]
   and RAGAS's `NonLLMContextPrecisionWithReference` /
   `NonLLMContextRecall` (reference_contexts matched by string-distance,
   no LLM)[^ragas-cp][^ragas-cr] are exactly this pattern. **Adopt as the
   primary matcher.**
2. **Page-level labels.** Our persisted chunk payload already carries
   `{document_id, page}` ([Decision 0005](/docs/decisions/0005-retrieval-architecture.md));
   a chunk is relevant if it comes from a gold (doc, page). Survives any
   re-chunk; coarse (a page holds several chunks, so it over-credits).
   **Adopt as fallback/sanity check and for citation scoring.**
3. **Claim-based recall (chunking-free).** RAGAS `LLMContextRecall`
   breaks the reference answer into claims and checks each is attributable
   to the retrieved context — needs no passage labels at all, but is
   LLM-judged.[^ragas-cr] **Use as a diagnostic**, not a gate.
4. **Node-ID matching** (LlamaIndex's default expected-ids
   mode[^llamaindex-eval]) breaks the moment chunking changes — only its
   expected-_texts_ mode is usable here. **Reject IDs; keep texts.**

# Answer (end-to-end) metrics

| Metric                      | Definition                                                                                                                                                                           | Ground truth                        | Fit verdict                                                                                                                                               |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Answer correctness          | RAGAS: weighted claim-level F1 (TP/FP/FN facts vs reference) + embedding similarity[^ragas-correctness]; LlamaIndex `CorrectnessEvaluator` scores 1–5 vs reference[^llamaindex-eval] | Reference answer + LLM judge        | **Adopt — headline answer metric.** We have reference answers by construction                                                                             |
| Exact-fact check            | Deterministic `string_check`/`contains` of expected value or identifier in the answer[^openai-graders][^promptfoo-det]                                                               | Expected string per question        | **Adopt for the technical persona** (specs, table lookups): binary, free, judge-proof                                                                     |
| Faithfulness / groundedness | Supported claims in response / total claims, verified against retrieved contexts[^ragas-faith]; TruLens Groundedness in the RAG Triad[^trulens-triad]                                | None (reference-free)[^ragas-paper] | **Adopt — the hallucination gate.** RAGAS also offers a non-LLM HHEM classifier variant[^ragas-faith]                                                     |
| Answer relevancy            | Mean cosine similarity between the question and N questions reverse-generated from the answer (RAGAS default N=3); explicitly does **not** measure factuality[^ragas-relevancy]      | None                                | **Report only.** Catches evasive answers on the operator persona; never a gate                                                                            |
| Citation precision / recall | ALCE: recall = cited passages jointly support the statement; precision = each individual citation supports it; judged by an NLI model[^alce]                                         | Gold passages                       | **Adopt deterministically:** the challenge requires references, so score cited (doc, page) against gold (doc, page) — set precision/recall, no NLI needed |
| Noise sensitivity           | Incorrect claims / total claims when relevant or irrelevant context was retrieved; lower is better[^ragas-noise]                                                                     | Reference + retrieved contexts      | **Diagnostic only** — useful when precision@k drops after hybrid/rerank changes                                                                           |

The reference-free triad (context relevance, groundedness, answer
relevance) is the shared core of RAGAS,[^ragas-paper] TruLens[^trulens-triad]
and ARES;[^ares] TruLens's claim is that passing all three verifies the app
"hallucination free up to the limit of its knowledge base".[^trulens-triad]

# LLM-as-judge pitfalls

- **Biases**: position bias, verbosity bias (longer ≻ better),
  self-enhancement bias (judges favor outputs of similar models), and weak
  grading of math/reasoning — though GPT-4-class judges reach >80%
  agreement with humans, the same as human–human agreement.[^llm-judge]
  G-Eval independently reports LLM evaluators biased toward
  LLM-generated text.[^geval]
- **Variance/calibration**: ARES exists because raw judge scores need
  statistical grounding — it fine-tunes lightweight judges and uses
  prediction-powered inference over a small human-annotated set to attach
  confidence intervals.[^ares]
- **Cost**: every judged metric is ≥1 LLM call per sample (RAGAS
  faithfulness = statement extraction + verification[^ragas-faith]);
  DeepEval states nearly all its predefined metrics are
  LLM-as-judge.[^deepeval-intro]
- Mitigations for us: pin judge model + temperature; keep deterministic
  metrics (recall@k, MRR, string checks, citation set-match) as the
  **gates** and LLM-judged metrics as diagnostics; periodically spot-check
  judge verdicts by hand on a sample.

# Efficiency metrics

Commonly logged alongside evals, not quality gates: per-question
**latency** (retrieval ms and end-to-end, promptfoo asserts a max-ms
threshold) and **cost/tokens** (promptfoo asserts a max-$ threshold using
provider cost data).[^promptfoo-det] Log retrieval latency, LLM
input/output tokens, and $ per question in every eval run so experiments
(e.g. reranking, the `query_knowledge` tool loop) show their price next to
their quality delta.

# What our golden dataset must therefore contain

Per item: `question` (tagged persona + language), `reference` (ideal
answer), `gold_excerpts` (verbatim spans, each with `document_id` +
`page`), and, for exact-spec questions, `expected_facts` (identifiers or
values for deterministic string checks). That single shape feeds every
adopted metric: recall@k / hit rate / MRR / precision@k via
excerpt-containment matching, citation precision/recall via (doc, page),
answer correctness via `reference`, faithfulness with no extra fields —
all without ever encoding a chunk ID.

[^iir]: Manning et al., Introduction to Information Retrieval §8.4

[^trec8-qa]: Voorhees — TREC-8 QA Track Report (NIST, 1999)

[^ndcg]: Järvelin & Kekäläinen — ACM TOIS 2002

[^ragas-paper]: Es et al. — RAGAS (arXiv 2309.15217)

[^ragas-cp]: RAGAS docs — Context Precision

[^ragas-cr]: RAGAS docs — Context Recall

[^ragas-entities]: RAGAS docs — Context Entities Recall

[^ragas-noise]: RAGAS docs — Noise Sensitivity

[^ragas-faith]: RAGAS docs — Faithfulness

[^ragas-relevancy]: RAGAS docs — Response Relevancy

[^ragas-correctness]: RAGAS docs — Answer Correctness

[^deepeval-intro]: DeepEval docs — Metrics introduction

[^deepeval-cp]: DeepEval docs — Contextual Precision

[^deepeval-cr]: DeepEval docs — Contextual Recall

[^trulens-triad]: TruLens docs — The RAG Triad

[^llamaindex-eval]: LlamaIndex docs — Evaluating module guide

[^promptfoo-rag]: promptfoo docs — Evaluating RAG pipelines

[^promptfoo-det]: promptfoo docs — Deterministic assertions

[^openai-graders]: OpenAI platform docs — Graders

[^ares]: Saad-Falcon et al. — ARES (arXiv 2311.09476)

[^llm-judge]: Zheng et al. — Judging LLM-as-a-Judge (arXiv 2306.05685)

[^geval]: Liu et al. — G-Eval (arXiv 2303.16634)

[^alce]: Gao et al. — ALCE (arXiv 2305.14627)
