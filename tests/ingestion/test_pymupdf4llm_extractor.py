import logging
from pathlib import Path

import pymupdf
import pytest

from ingestion.pymupdf4llm_extractor import Pymupdf4llmExtractor, page_sections

CESTARI = (
    Path(__file__).resolve().parents[2]
    / "case_files"
    / "WEG-CESTARI-manual-iom-guia-consulta-rapida-50111652-pt-en-es-web.pdf"
)


@pytest.fixture(scope="module")
def extracted_pages():
    doc = pymupdf.open()
    for marker in ("alpha content", "bravo content", "charlie content"):
        page = doc.new_page()
        page.insert_text((72, 72), marker)
    doc.set_toc([[1, "Intro", 1], [1, "Operation", 2], [2, "Startup", 2]])
    data = doc.tobytes()

    return Pymupdf4llmExtractor().extract(data, "generated.pdf")


def test_extracts_one_page_per_pdf_page_with_its_text(extracted_pages):
    assert [p.number for p in extracted_pages] == [1, 2, 3]
    assert "alpha content" in extracted_pages[0].text
    assert "bravo content" in extracted_pages[1].text
    assert "charlie content" in extracted_pages[2].text


def test_sections_come_from_toc_breadcrumbs_and_carry_forward(extracted_pages):
    assert extracted_pages[0].section == "Intro"
    assert extracted_pages[1].section == "Operation > Startup"
    assert extracted_pages[2].section == "Operation > Startup"


def test_fonts_lacking_tounicode_are_repaired_before_extraction(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="ingestion.pymupdf4llm_extractor")
    doc = pymupdf.open(CESTARI)
    doc.select([17])
    data = doc.tobytes()

    pages = Pymupdf4llmExtractor().extract(data, "cestari.pdf")

    assert "�" not in pages[0].text
    assert "Temperatura" in pages[0].text
    assert "Óleo Mineral" in pages[0].text
    assert [record.getMessage() for record in caplog.records] == [
        "cestari.pdf: repaired 2 font(s) lacking ToUnicode: Arial,Bold, Arial"
    ]


def test_readable_pdfs_log_no_repair(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="ingestion.pymupdf4llm_extractor")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "readable text")

    Pymupdf4llmExtractor().extract(doc.tobytes(), "clean.pdf")

    assert caplog.records == []


def test_running_headers_are_cleaned_out_of_page_text():
    doc = pymupdf.open()
    for marker in ("alpha", "bravo", "charlie", "delta"):
        page = doc.new_page()
        page.insert_text((72, 40), "www.example.net")
        page.insert_text((72, 300), f"{marker} content")

    pages = Pymupdf4llmExtractor().extract(doc.tobytes(), "generated.pdf")

    assert all("www.example.net" not in page.text for page in pages)
    assert [page.text.lstrip("# ") for page in pages] == [
        "alpha content",
        "bravo content",
        "charlie content",
        "delta content",
    ]


def test_page_sections_follow_the_toc_breadcrumb_when_the_pdf_has_an_outline():
    texts = ["# Intro\n\nbody", "## Startup\n\nbody", "body"]
    toc = [[(1, "Intro")], [(1, "Operation"), (2, "Startup")], []]

    assert page_sections(texts, toc) == ["Intro", "Operation > Startup", "Operation > Startup"]


def test_page_sections_fall_back_to_markdown_headings_and_carry_across_pages():
    texts = [
        "# **Operation**\n\nrun it\n\n## Startup\n\nstart it",
        "continued without headings",
        "# Maintenance\n\ngrease it",
        "## **<u>Lubrication</u>**\n\ngrease more",
    ]

    assert page_sections(texts, [[], [], [], []]) == [
        "Operation > Startup",
        "Operation > Startup",
        "Maintenance",
        "Maintenance > Lubrication",
    ]


def test_page_sections_are_none_before_any_heading_or_toc_entry():
    assert page_sections(["plain text", "# Title\n\nbody"], [[], []]) == [None, "Title"]
