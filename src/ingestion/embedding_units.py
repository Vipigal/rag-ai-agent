import re
from pathlib import PurePath

from domain.models import SECTION_SEPARATOR, Chunk

_BLANK_LINES = re.compile(r"\n\s*\n")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")


def embedding_units(chunk: Chunk) -> list[str]:
    context = _context(chunk)
    units = [
        unit
        for block in _BLANK_LINES.split(chunk.text)
        if block.strip()
        for unit in _block_units(block.strip())
    ]
    return [f"{context}\n\n{unit}" for unit in units] or [f"{context}\n\n{chunk.text}"]


def _context(chunk: Chunk) -> str:
    parts = [PurePath(chunk.filename).stem.replace("-", " ").replace("_", " ")]
    if chunk.section:
        parts.append(chunk.section)
    return SECTION_SEPARATOR.join(parts)


def _block_units(block: str) -> list[str]:
    lines = block.splitlines()
    if not all(line.lstrip().startswith("|") for line in lines):
        return [block]
    header = lines[:2] if len(lines) > 2 and _TABLE_SEPARATOR.match(lines[1]) else []
    return ["\n".join([*header, row]) for row in lines[len(header) :]]
