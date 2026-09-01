import re

from evaluation.dataset import GoldExcerpt

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


def normalize(text: str) -> str:
    return _NON_WORD.sub(" ", text.casefold()).strip()


def token_overlap(excerpt_text: str, chunk_text: str) -> float:
    excerpt_tokens = _tokens(excerpt_text)
    if not excerpt_tokens:
        return 0.0
    return len(excerpt_tokens & _tokens(chunk_text)) / len(excerpt_tokens)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(normalize(text).split())


def is_relevant(chunk_text: str, excerpt: GoldExcerpt, threshold: float) -> bool:
    return any(
        token_overlap(variant.text, chunk_text) >= threshold
        for variant in (excerpt, *excerpt.alternates)
    )
