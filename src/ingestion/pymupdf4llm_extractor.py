import logging
import re

import pymupdf
import pymupdf4llm

from domain.errors import UnreadableDocument
from domain.models import SECTION_SEPARATOR, Page
from ingestion.page_cleaning import clean_pages
from ingestion.pdf_font_repair import repair_fonts

log = logging.getLogger(__name__)

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_DECORATION = re.compile(r"^[\s*_]+|[\s*_]+$")
_INLINE_TAGS = re.compile(r"</?(?:u|b|i)>")


class Pymupdf4llmExtractor:
    def extract(self, data: bytes, filename: str) -> list[Page]:
        doc = _open(data, filename)
        repaired = repair_fonts(doc)
        if repaired:
            log.info(
                "%s: repaired %d font(s) lacking ToUnicode: %s",
                filename,
                len(repaired),
                ", ".join(repaired),
            )
        page_dicts = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
        if not isinstance(page_dicts, list):
            raise TypeError(
                f"{filename}: expected a list of page dicts from pymupdf4llm, "
                f"got {type(page_dicts).__name__}"
            )

        texts: list[str] = []
        toc_entries: list[list[tuple[int, str]]] = []
        for number, page_dict in enumerate(page_dicts, start=1):
            if not isinstance(page_dict, dict):
                raise TypeError(
                    f"{filename} page {number}: expected a page dict, "
                    f"got {type(page_dict).__name__}"
                )
            text = page_dict.get("text")
            if not isinstance(text, str):
                raise TypeError(
                    f"{filename} page {number}: expected str text, "
                    f"got {type(text).__name__}"
                )
            texts.append(text)
            toc_entries.append(_toc_entries(page_dict.get("toc_items", []), filename, number))

        cleaned = clean_pages(texts)
        sections = page_sections(cleaned, toc_entries)
        return [
            Page(number=number, text=text, section=section)
            for number, (text, section) in enumerate(zip(cleaned, sections), start=1)
        ]


def _open(data: bytes, filename: str) -> pymupdf.Document:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except RuntimeError as error:
        raise UnreadableDocument(filename, str(error)) from error
    if doc.needs_pass:
        raise UnreadableDocument(filename, "the file is password-protected")
    if doc.page_count == 0:
        raise UnreadableDocument(filename, "the file has no pages")
    return doc


def page_sections(
    texts: list[str], toc_entries: list[list[tuple[int, str]]]
) -> list[str | None]:
    toc = _Breadcrumb()
    headings = _Breadcrumb()
    sections: list[str | None] = []
    for text, entries in zip(texts, toc_entries, strict=True):
        for level, title in entries:
            toc.descend(level, title)
        for match in _HEADING.finditer(text):
            headings.descend(len(match.group(1)), _title(match.group(2)))
        sections.append(toc.path() or headings.path())
    return sections


class _Breadcrumb:
    def __init__(self) -> None:
        self._levels: dict[int, str] = {}

    def descend(self, level: int, title: str) -> None:
        self._levels = {lvl: t for lvl, t in self._levels.items() if lvl < level}
        self._levels[level] = title

    def path(self) -> str | None:
        return SECTION_SEPARATOR.join(title for _, title in sorted(self._levels.items())) or None


def _title(raw: str) -> str:
    return _DECORATION.sub("", _INLINE_TAGS.sub("", raw))


def _toc_entries(raw: object, filename: str, number: int) -> list[tuple[int, str]]:
    if not isinstance(raw, list):
        raise TypeError(
            f"{filename} page {number}: expected a list of toc items, got {type(raw).__name__}"
        )
    entries: list[tuple[int, str]] = []
    for item in raw:
        if not (
            isinstance(item, list)
            and len(item) >= 2
            and isinstance(item[0], int)
            and isinstance(item[1], str)
        ):
            raise TypeError(f"{filename} page {number}: malformed toc item {item!r}")
        entries.append((item[0], item[1]))
    return entries
