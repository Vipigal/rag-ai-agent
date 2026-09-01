import pytest

from evaluation.dataset import ExcerptVariant, GoldExcerpt
from evaluation.matching import is_relevant, token_overlap

EXCERPT = "graxa polyrex intervalo 9500 horas"


def test_token_overlap_is_fraction_of_excerpt_tokens_found_in_chunk() -> None:
    chunk = "o manual fala de graxa e do intervalo de 9500"

    assert token_overlap(EXCERPT, chunk) == pytest.approx(0.6)


def test_token_overlap_full_when_chunk_contains_all_excerpt_tokens() -> None:
    chunk = "trocar a graxa Polyrex EM num intervalo de 9500 horas de uso"

    assert token_overlap(EXCERPT, chunk) == pytest.approx(1.0)


def test_token_overlap_zero_when_no_tokens_shared() -> None:
    assert token_overlap(EXCERPT, "tensão nominal do enrolamento") == 0.0


def test_token_overlap_ignores_case_punctuation_and_repetition() -> None:
    chunk = "GRAXA... graxa; (polyrex): Intervalo—9500, 9500 HORAS!"

    assert token_overlap(EXCERPT, chunk) == pytest.approx(1.0)


def _excerpt(text: str, alternates: tuple[ExcerptVariant, ...] = ()) -> GoldExcerpt:
    return GoldExcerpt(document="manual.pdf", page=1, text=text, alternates=alternates)


def test_is_relevant_when_chunk_contains_excerpt_despite_formatting() -> None:
    chunk = "Manutenção:\n  GRAXA  Polyrex,\nintervalo (9500) horas — ver tabela."

    assert is_relevant(chunk, _excerpt(EXCERPT), threshold=0.6)


def test_is_relevant_at_exact_overlap_threshold() -> None:
    chunk = "o manual fala de graxa e do intervalo de 9500"

    assert is_relevant(chunk, _excerpt(EXCERPT), threshold=0.6)


def test_not_relevant_when_overlap_below_threshold() -> None:
    chunk = "o manual fala de graxa e do intervalo de 9500"

    assert not is_relevant(chunk, _excerpt(EXCERPT), threshold=0.61)


def test_alternate_match_satisfies_the_slot() -> None:
    primary = _excerpt(
        "lubrificação do rolamento dianteiro",
        alternates=(
            ExcerptVariant(document="manual.pdf", page=53, text="front bearing lubrication"),
        ),
    )
    chunk = "see chapter on front bearing lubrication for details"

    assert is_relevant(chunk, primary, threshold=0.6)


def test_not_relevant_when_no_variant_matches() -> None:
    assert not is_relevant("tensão nominal do enrolamento", _excerpt(EXCERPT), threshold=0.6)
