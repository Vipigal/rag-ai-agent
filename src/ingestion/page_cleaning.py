import math
import re

MIN_REPEATED_PAGES = 3
REPEATED_PAGE_SHARE = 0.5

_HTML_COMMENT = re.compile(r"<!--.*?-->")
_DOT_LEADERS = re.compile(r"\.{4,}|\.(?:\s+\.){2,}")
_SPACE_RUNS = re.compile(r" {2,}")
_BARE_PAGE_NUMBER = re.compile(r"[\s*_.,\-–—()/]*\d[\s\d*_.,\-–—()/]*")
_FURNITURE_NOISE = re.compile(r"[\d\s*_]+")
_BLANK_RUNS = re.compile(r"\n{3,}")


def clean_pages(texts: list[str]) -> list[str]:
    pages = [_normalize_lines(text) for text in texts]
    furniture = _repeated_furniture(pages)
    return [_assemble(lines, furniture) for lines in pages]


def _normalize_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = _HTML_COMMENT.sub("", raw)
        line = _DOT_LEADERS.sub(" ", line)
        line = _SPACE_RUNS.sub(" ", line).rstrip()
        lines.append(line)
    return lines


def _repeated_furniture(pages: list[list[str]]) -> set[str]:
    threshold = max(MIN_REPEATED_PAGES, math.ceil(len(pages) * REPEATED_PAGE_SHARE))
    if len(pages) < threshold:
        return set()
    seen_on: dict[str, int] = {}
    for lines in pages:
        for key in {_furniture_key(line) for line in lines if _is_furniture_candidate(line)}:
            seen_on[key] = seen_on.get(key, 0) + 1
    return {key for key, count in seen_on.items() if count >= threshold}


def _is_furniture_candidate(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("|")


def _furniture_key(line: str) -> str:
    return _FURNITURE_NOISE.sub("", line)


def _assemble(lines: list[str], furniture: set[str]) -> str:
    kept = [
        line
        for line in lines
        if not _is_bare_page_number(line)
        and not (_is_furniture_candidate(line) and _furniture_key(line) in furniture)
    ]
    return _BLANK_RUNS.sub("\n\n", "\n".join(kept)).strip()


def _is_bare_page_number(line: str) -> bool:
    return bool(line.strip()) and _BARE_PAGE_NUMBER.fullmatch(line) is not None
