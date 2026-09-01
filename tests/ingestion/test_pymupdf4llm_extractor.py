import pymupdf
import pytest

from ingestion.pymupdf4llm_extractor import Pymupdf4llmExtractor


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
