from pathlib import Path

import pymupdf

from ingestion.pdf_font_repair import GLYPH_TO_CHAR, repair_fonts

CESTARI = (
    Path(__file__).resolve().parents[2]
    / "case_files"
    / "WEG-CESTARI-manual-iom-guia-consulta-rapida-50111652-pt-en-es-web.pdf"
)
NO_CID_FALLBACK = pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_CID_FOR_UNKNOWN_UNICODE


def cestari_pages(*indexes: int) -> pymupdf.Document:
    doc = pymupdf.open(CESTARI)
    doc.select(list(indexes))
    return doc


def test_glyph_table_follows_the_arial_standard_order():
    assert GLYPH_TO_CHAR[3] == " "
    assert GLYPH_TO_CHAR[36] == "A"
    assert GLYPH_TO_CHAR[68] == "a"
    assert GLYPH_TO_CHAR[109] == "ã"
    assert GLYPH_TO_CHAR[111] == "ç"
    assert GLYPH_TO_CHAR[131] == "°"
    assert GLYPH_TO_CHAR[173] == "Ã"
    assert GLYPH_TO_CHAR[179] == "“"
    assert GLYPH_TO_CHAR[203] == "Í"
    assert GLYPH_TO_CHAR[207] == "Ó"
    assert {0, 1, 2}.isdisjoint(GLYPH_TO_CHAR)


def test_pdf_whose_fonts_already_map_to_unicode_is_left_alone():
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "readable text")

    assert repair_fonts(doc) == []
    assert "readable text" in doc[0].get_text()


def test_identity_h_fonts_without_tounicode_become_readable():
    doc = cestari_pages(17)
    assert "�" in doc[0].get_text(flags=NO_CID_FALLBACK)

    patched = repair_fonts(doc)

    text = doc[0].get_text(flags=NO_CID_FALLBACK)
    assert patched == ["Arial,Bold", "Arial"]
    assert "�" not in text
    assert "Temperatura" in text
    assert "de Operação" in text
    assert "Óleo Mineral" in text
    assert "--- ---" in text


def test_symbol_fonts_and_fonts_outside_the_table_are_skipped():
    doc = cestari_pages(2, 5, 17)

    patched = repair_fonts(doc)

    assert patched == ["Arial,Bold", "Arial"]


def test_fonts_unused_by_garbled_text_are_not_touched():
    doc = cestari_pages(5)

    assert repair_fonts(doc) == []
