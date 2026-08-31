---
type: Reference
title: Case Files Corpus Findings
description: Empirical survey of the four case_files PDFs — languages, structure, extraction quality — including the broken text layer in the CESTARI manual and measured pymupdf4llm 1.28.2 behavior on this corpus.
tags: [corpus, ingestion, pdf-extraction, pymupdf4llm, ocr]
status: draft
generated: { by: claude_code/claude-fable-5, at: 2026-08-31T19:05:00Z }
verified: { by: human:vinicius, at: 2026-08-31T19:49:00Z }
sources:
  - id: lb5001
    resource: /case_files/LB5001.pdf
    title: LB5001 — AC & DC Motor Installation & Maintenance Instructions
  - id: mn414
    resource: /case_files/MN414_0224.pdf
    title: MN414 — AC Submersible Pump Motors (ABB/Baldor, Feb 2024)
  - id: cestari
    resource: /case_files/WEG-CESTARI-manual-iom-guia-consulta-rapida-50111652-pt-en-es-web.pdf
    title: WEG-CESTARI IOM Quick Reference Guide (PT/ES/EN)
  - id: weg-guia
    resource: /case_files/WEG-motores-eletricos-guia-de-especificacao-50032749-brochure-portuguese-web.pdf
    title: WEG Guia de Especificação de Motores Elétricos (PT)
  - id: pymupdf4llm-docs
    resource: https://github.com/pymupdf/pymupdf4llm
    title: PyMuPDF4LLM documentation (v1.28.2)
---

# Corpus survey

Measured 2026-08-31 with poppler `pdftotext`/`pdfinfo` and pymupdf4llm
1.28.2. Whole corpus ≈ 55k words (≈ 70–100k tokens): small enough that
any ingestion strategy costs cents; per-question cost dominates.

| File                                 | Pages | Language(s)                                    | Words  | Text layer | Notes                                                                                                  |
| ------------------------------------ | ----- | ---------------------------------------------- | ------ | ---------- | ------------------------------------------------------------------------------------------------------ |
| LB5001[^lb5001]                      | 2     | EN                                             | ~1.0k  | clean      | Datasheet-style leaflet                                                                                |
| MN414_0224[^mn414]                   | 16    | EN                                             | ~5.3k  | clean      | Manual, simple layout                                                                                  |
| WEG-CESTARI[^cestari]                | 84    | PT + ES + EN (trilingual, sequential sections) | ~11.8k | **broken** | See trap below                                                                                         |
| WEG guia de especificação[^weg-guia] | 68    | PT                                             | ~37.2k | clean      | Numbered headings (`5.1.2`), 32 of 68 pages contain detectable tables, formulas, figures with captions |

# The CESTARI trap: broken CMap text layer

The CESTARI manual's[^cestari] main font has a corrupted/missing
ToUnicode CMap. `pdftotext` emits shifted glyph codes (`23(5$d­2` for
"OPERAÇÃO"); PyMuPDF maps the same glyphs to U+FFFD (`�`). Naive
ingestion silently indexes garbage for most of this document.

Verified behavior of pymupdf4llm 1.28.2 on this file:

- Default `use_ocr=True` did **not** trigger its garbled-text OCR
  heuristic; output was `�`-runs.
- `use_ocr=OCRMode.FORCE_DROP_OLD` **also returned `�`-runs, silently,**
  when Tesseract is not installed (no exception raised).

Consequences for the ingestion pipeline:

1. The environment (Docker image) must ship Tesseract with `por`, `spa`,
   `eng` traineddata for OCR fallback to actually work.
2. Ingestion needs an extraction **quality gate** — e.g. reject a page
   whose U+FFFD ratio (or out-of-dictionary ratio) exceeds a threshold —
   and route failing pages to forced OCR. Never trust the extractor's
   own auto-detection alone.

# Measured pymupdf4llm 1.28.2 behavior on this corpus

- **Headings**: font-size-based detection works; numbered sections come
  out as markdown headings (`# 1.2.6 Rendimento`). `page_chunks=True`
  returns `toc_items` per page with hierarchy levels — ready-made
  section breadcrumbs for chunk metadata.
- **`page_chunks` schema drift**: v1.28.2 returns keys `metadata,
toc_items, page_boxes, text` — the README still documents `tables`,
  `images`, `graphics` lists that are no longer present.[^pymupdf4llm-docs]
- **Tables**: simple spec tables render as clean markdown
  (`|Carcaça|Quantidade|Potência(W)|`). Tables with merged/multi-level
  headers (e.g. Tabela 8.6 noise limits) flatten with partial structure
  loss (`|2po|los|4po|los|`). In-text formulas are sometimes rendered as
  pseudo-tables.
- **Images**: `write_images=True` inserts `![](path.png)` refs inline at
  the correct reading-order position — between the citing sentence
  ("… (Figura 5.1):") and the caption ("Figura 5.1 - Resumo das ligações
  Dahlander") — giving text↔image linkage for free.
- **Speed**: table detection ≈ 0.5 s/page CPU (32.6 s for the 68-page
  guide); markdown conversion itself is sub-second per page.

[^lb5001]: LB5001 — AC & DC Motor Installation & Maintenance Instructions

[^mn414]: MN414 — AC Submersible Pump Motors (ABB/Baldor, Feb 2024)

[^cestari]: WEG-CESTARI IOM Quick Reference Guide (PT/ES/EN)

[^weg-guia]: WEG Guia de Especificação de Motores Elétricos (PT)

[^pymupdf4llm-docs]: PyMuPDF4LLM documentation (v1.28.2)
