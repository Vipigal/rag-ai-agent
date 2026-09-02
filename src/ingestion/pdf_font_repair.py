import re
from collections import defaultdict

import pymupdf
from fontTools import agl
from fontTools.ttLib.standardGlyphOrder import standardGlyphOrder

SYMBOL_FONT_MARKERS = ("Wingdings", "Webdings", "Symbol", "Dingbat")
MIN_GLYPH_COVERAGE = 0.9

_FIRST_PRINTABLE_GLYPH = 3
_SPACE_GLYPH = 3
_APPLE_ONLY_GLYPH = "nonbreakingspace"
_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")
_IDENTITY_SUFFIX = "-Identity-H"
_REPLACEMENT_CHARACTER = 0xFFFD

_ARIAL_GLYPH_ORDER = [name for name in standardGlyphOrder if name != _APPLE_ONLY_GLYPH]

GLYPH_TO_CHAR: dict[int, str] = {
    gid: agl.toUnicode(name)
    for gid, name in enumerate(_ARIAL_GLYPH_ORDER)
    if gid >= _FIRST_PRINTABLE_GLYPH and agl.toUnicode(name)
}


def _build_tounicode_cmap() -> bytes:
    entries = "\n".join(f"<{gid:04X}> <{ord(char):04X}>" for gid, char in GLYPH_TO_CHAR.items())
    return (
        "/CIDInit /ProcSet findresource begin\n"
        "12 dict begin\n"
        "begincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Adobe-Identity-UCS def\n"
        "/CMapType 2 def\n"
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        f"{len(GLYPH_TO_CHAR)} beginbfchar\n{entries}\nendbfchar\n"
        "endcmap\n"
        "CMapName currentdict /CMap defineresource pop\n"
        "end\nend\n"
    ).encode()


_TOUNICODE_CMAP = _build_tounicode_cmap()


def repair_fonts(doc: pymupdf.Document) -> list[str]:
    candidates = _identity_fonts_lacking_tounicode(doc)
    if not candidates:
        return []
    usage = _garbled_glyph_usage(doc)
    patched: list[str] = []
    for xref, name in candidates:
        if _is_symbol_font(name) or not _covered_by_table(usage.get(name)):
            continue
        _attach_tounicode(doc, xref)
        patched.append(name)
    return patched


def _identity_fonts_lacking_tounicode(doc: pymupdf.Document) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for xref in range(1, doc.xref_length()):
        if not doc.xref_is_font(xref):
            continue
        if doc.xref_get_key(xref, "Subtype")[1] != "/Type0":
            continue
        if doc.xref_get_key(xref, "Encoding")[1] != "/Identity-H":
            continue
        if doc.xref_get_key(xref, "ToUnicode")[0] != "null":
            continue
        found.append((xref, _font_name(doc.xref_get_key(xref, "BaseFont")[1])))
    return found


def _font_name(base_font: str) -> str:
    name = _SUBSET_PREFIX.sub("", base_font.removeprefix("/"))
    return name.removesuffix(_IDENTITY_SUFFIX)


def _garbled_glyph_usage(doc: pymupdf.Document) -> dict[str, tuple[int, int]]:
    in_table: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)
    for page in doc:
        for span in page.get_texttrace():
            chars = span["chars"]
            if not any(char[0] == _REPLACEMENT_CHARACTER for char in chars):
                continue
            font = span["font"]
            glyphs = [char[1] for char in chars if char[1] != _SPACE_GLYPH]
            total[font] += len(glyphs)
            in_table[font] += sum(1 for glyph in glyphs if glyph in GLYPH_TO_CHAR)
    return {font: (in_table[font], total[font]) for font in total if total[font]}


def _is_symbol_font(name: str) -> bool:
    return any(marker in name for marker in SYMBOL_FONT_MARKERS)


def _covered_by_table(usage: tuple[int, int] | None) -> bool:
    if usage is None:
        return False
    in_table, total = usage
    return in_table / total >= MIN_GLYPH_COVERAGE


def _attach_tounicode(doc: pymupdf.Document, font_xref: int) -> None:
    cmap_xref = doc.get_new_xref()
    doc.update_object(cmap_xref, "<<>>")
    doc.update_stream(cmap_xref, _TOUNICODE_CMAP)
    doc.xref_set_key(font_xref, "ToUnicode", f"{cmap_xref} 0 R")
