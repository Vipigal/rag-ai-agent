import re

_DASHES = re.compile("[\u2010\u2011\u2012\u2013\u2014\u2212]")
_MARKUP = re.compile(r"<[^<>]{1,30}>|[*#|`\"'\u2018\u2019\u201c\u201d\u00ab\u00bb]")
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    text = _DASHES.sub("-", text.casefold())
    text = _MARKUP.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def contains(text: str, quote: str) -> bool:
    lines = [normalized for line in quote.splitlines() if (normalized := normalize(line))]
    if not lines:
        return False
    haystack = normalize(text)
    return all(line in haystack for line in lines)
