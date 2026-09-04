---
type: Module
title: Golden Dataset
description: Co-located overview of the 93-case golden dataset — what each YAML file covers, page-numbering and transcription semantics per source PDF, each file's canary role, the semantics of negative cases, and the rules a case is written by.
tags: [evals, golden-dataset, corpus, ground-truth]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-04T12:00:00Z }
sources:
  - id: decision-0006
    resource: /docs/decisions/0006-eval-metrics-and-golden-dataset.md
    title: 0006 — Eval metrics and golden-dataset shape
  - id: corpus-findings
    resource: /docs/research/case-files-corpus-findings.md
    title: Case Files Corpus Findings
---

# What lives here

The hand-authored golden dataset over `case_files/`: 93 question →
ideal-answer cases split across five YAML files, one per source PDF plus
one of negatives. The case schema is the YAML itself, validated by
`src/evaluation/dataset.py`; the metric decisions the dataset feeds are in
Decision 0006.[^decision-0006] Each case's `notes` field states the
specific trap that case tests. This concept carries what the YAML files
themselves cannot say (this repo keeps code and config files
comment-free): the per-file knowledge below, and the rules a case is
written by.

# The files

| File            | Source PDF (pages, language)                                                | Cases | Role                                                                 |
| --------------- | --------------------------------------------------------------------------- | ----- | -------------------------------------------------------------------- |
| `lb5001.yaml`   | LB5001.pdf — AC & DC Motor Installation & Maintenance, Baldor/ABB (2 p., EN) | 8     | Small-doc baseline; grease/relubrication tables                       |
| `mn414.yaml`    | MN414_0224.pdf — AC Submersible Pump Motors, Baldor-Reliance (16 p., EN)     | 17    | Cross-page synthesis, color-code tables, one photo-only image case    |
| `cestari.yaml`  | WEG-CESTARI IOM quick guide — gear units (84 p., trilingual PT/ES/EN)        | 20    | **OCR-ingestion canary**: broken text layer, rotated defect table     |
| `weg-guia.yaml` | WEG Guia de Especificação de Motores Elétricos (68 p., PT)                   | 40    | Main table/figure/formula load, incl. the flattened-table canary      |
| `negatives.yaml`| — (no source)                                                                | 8     | Unanswerable controls with near-miss traps                            |

# Page-numbering semantics

- `page` is always the **1-based physical page index** of the PDF file,
  never the number printed on the page.
- **LB5001, MN414, WEG guia**: physical index and printed number coincide
  (MN414's cover is page 1; the guide's printed numbers match physical).
- **CESTARI**: printed page N maps to physical page N + 4. The manual is
  trilingual with mirrored sections — printed PT pages 1-26, ES 27-52, EN
  53-78 — so one fact at PT physical page p also exists at physical p + 26
  (ES) and p + 52 (EN). That is why CESTARI excerpts carry `alternates`:
  retrieval returning the same fact from another language section is a
  hit, and any alternate's (doc, page) satisfies citation scoring.

# Transcription caveats

- **CESTARI's text layer is broken** (corrupted CMap[^corpus-findings]):
  naive extraction yields `�`-runs. Every excerpt in `cestari.yaml` is a
  human transcription from the rendered pages, so matching for this
  document works only through the token-overlap path against whatever OCR
  ingestion produces. If ingestion indexes garbage, recall on this file
  collapses — by design.
- **WEG guia's text layer is clean**, but tables and in-text formulas are
  transcribed flattened (no pipes, no dot leaders); matching relies on
  token overlap. `weg-guia-033` targets Tabela 8.6, measured by the corpus
  survey[^corpus-findings] to flatten with structure loss under
  pymupdf4llm, and pairs with `weg-guia-032` (a table that renders
  cleanly) to isolate the multi-header table path when one fails.
- The defect-troubleshooting table in CESTARI (`cestari-018`) is rendered
  rotated 90° in the PDF — the hardest table-ingestion case in the corpus.

# Negative cases

Every case in `negatives.yaml` has no answer in the corpus:
`gold_excerpts` is empty, the `reference_answer` is a grounded refusal,
and the harness checks that the system refused instead of hallucinating.
They are excluded from retrieval metrics. Several are deliberate
near-miss traps — the corpus contains something *similar* that a
hallucinating system would grab (e.g. `neg-007`: a 12-month warranty
exists in the corpus, but for CESTARI gearboxes, not the pump motor being
asked about).

# How a case is written

Cases are hand-authored. The author reads each PDF **page by page as
rendered**, not through the text layer — mandatory for CESTARI, whose
extraction yields `�`. LLM test-set generation was rejected on two
grounds: generated questions parrot the source's phrasing, which inflates
retrieval scores, and CESTARI's broken text layer would poison the
generator's input. The first batch (LB5001) was reviewed for tone and
difficulty before the remaining cases were written.

Five style rules govern every question:

1. **A question never references the manual or its structure** — not
   "according to the relubrication table", not "in section 5.1". Someone
   holding the manual would read it, not ask the system. Source anchoring
   belongs in `gold_excerpts`, never in the question.
2. **Operator questions never reuse the manual's vocabulary** — "parafusar
   na base", not "securely mounted by its mounting holes". Lexical overlap
   with the source inflates retrieval scores.
3. **Table excerpts carry the table title, the header row and the data
   row**, so overlap matching survives a chunker that renders the table as
   markdown.
4. **`expected_facts` stay minimal and numeric**, and the case's `notes`
   flag the normalization traps (decimal comma, digit grouping).
5. **`notes` states the trap the case tests**, for whoever debugs it as a
   red result later.

Language is assigned deliberately, not incidentally: the operator persona
asks in pt-BR throughout; the technical persona mixes pt and en.
Cross-lingual coverage is on purpose — pt questions over the EN-only
manuals (LB5001, MN414) and en questions over the PT-only guide — and
metrics are sliced by `language` and by document so a cross-lingual
embedding failure shows up as its own axis rather than as noise.

The `image_content` slice is deliberately small — 2 cases, against an
early target of ~5. Reading the whole corpus showed its figures are
consistently caption-anchored: nearly every visual fact is also stated in
text nearby. The only honest image-only questions in the corpus were a
graph value (the tE curve) and a photo detail (receptacle contacts).
Inventing more would have meant reference answers nobody could verify,
which is how a golden dataset stops being ground truth. The slice grows
when multimodal ingestion does.

[^decision-0006]: 0006 — Eval metrics and golden-dataset shape.

[^corpus-findings]: Case Files Corpus Findings — CESTARI broken CMap,
    pymupdf4llm table behavior on this corpus.
