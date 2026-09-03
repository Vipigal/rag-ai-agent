import pytest

from domain.models import Answer, Chunk, Reference, Usage
from evaluation.answers import (
    AnswerBlock,
    AnswerRun,
    aggregate_answers,
    contains_fact,
    evaluate_answer,
    normalize,
)
from evaluation.dataset import ExcerptVariant, GoldenCase, GoldExcerpt

MANUAL = GoldExcerpt(document="manual.pdf", page=34, text="grau de proteção IP55")
MIRRORED = GoldExcerpt(
    document="cestari.pdf",
    page=12,
    text="fator kr",
    alternates=(ExcerptVariant(document="cestari.pdf", page=64, text="kr factor"),),
)


def _case(
    case_id: str = "doc-001",
    category: str = "spec_lookup",
    facts: tuple[str, ...] = ("IP55",),
    excerpts: tuple[GoldExcerpt, ...] = (MANUAL,),
    requires_image: bool = False,
    persona: str = "operator",
    language: str = "pt",
) -> GoldenCase:
    return GoldenCase(
        id=case_id,
        question="qual o grau de proteção?",
        persona=persona,
        language=language,
        category=category,
        gold_excerpts=excerpts,
        reference_answer="IP55.",
        expected_facts=facts,
        requires_image=requires_image,
    )


def _reference(document: str, page: int, source: str = "seed") -> Reference:
    chunk = Chunk(
        id=f"{document}:{page}",
        document_id="d",
        filename=document,
        text="texto",
        page=page,
        section=None,
        index_in_doc=page,
    )
    return Reference(chunk=chunk, quote="texto", retrieval_source=source)


def _run(
    text: str,
    references: list[Reference],
    has_answer: bool = True,
    usage: Usage = Usage(),
    latency_ms: float = 1000.0,
    unmatched: tuple[str, ...] = (),
) -> AnswerRun:
    answer = Answer(
        text=text, references=references, has_answer=has_answer, usage=usage, unmatched_citations=list(unmatched)
    )
    return AnswerRun(answer=answer, latency_ms=latency_ms)


@pytest.mark.parametrize(
    ("answer", "fact", "expected"),
    [
        ("A potência é 2,2 kW.", "2.2 kW", True),
        ("A potência é 2.2kW.", "2,2 kW", True),
        ("São 1.800 rpm", "1,800 rpm", True),
        ("A tensão é 127/220 V", "127", True),
        ("A tensão é 127V", "127", True),
        ("A tensão é 1270 V", "127", False),
        ("Rendimento de 4 %", "4%", True),
        ("Rendimento de 14%", "4%", False),
        ("Grau IP55.", "IP55", True),
        ("Grau IP555", "IP55", False),
        ("Use Shell Rotella 10 SAE 10W", "Shell Rotella", True),
        ("Dow Corning Molykote G\u2011Rapid Plus", "Molykote G-Rapid Plus", True),
        ("faixa de 20\u201330 \u00b0C", "20-30°C", True),
        ("Temperatura de 40 °C", "40°C", True),
        ("", "IP55", False),
        ("qualquer coisa", "", False),
    ],
)
def test_contains_fact_normalizes_case_decimal_comma_digit_grouping_and_unit_spacing(
    answer: str, fact: str, expected: bool
):
    assert contains_fact(answer, fact) is expected


def test_the_digit_separator_collapse_makes_a_decimal_match_a_bare_number():
    assert contains_fact("gira a 736 rpm", "7,36") is True


def test_normalize_casefolds_and_collapses_whitespace():
    assert normalize("  Motor  de 2,2 kW\n") == "motor de 22kw"


def test_facts_and_citations_are_scored_against_the_gold_pages():
    case = _case(facts=("IP55", "IP66"))
    run = _run(
        "O grau é IP55.",
        [_reference("manual.pdf", 34), _reference("manual.pdf", 34, "tool"), _reference("manual.pdf", 2)],
    )

    result = evaluate_answer(case, run)

    assert result.has_answer is True
    assert result.fact_hits == (True, False)
    assert result.fact_recall == 0.5
    assert result.cited == (("manual.pdf", 34), ("manual.pdf", 2))
    assert result.cited_in_gold == (True, False)
    assert result.citation_precision == 0.5
    assert result.citation_recall == 1.0


def test_an_alternate_page_counts_as_gold_for_citations():
    case = _case(facts=(), excerpts=(MANUAL, MIRRORED))
    run = _run("kr = 2,5.", [_reference("cestari.pdf", 64)])

    result = evaluate_answer(case, run)

    assert result.fact_recall is None
    assert result.cited_in_gold == (True,)
    assert result.citation_precision == 1.0
    assert result.citation_recall == 0.5


def test_an_answer_without_references_scores_zero_on_citations():
    result = evaluate_answer(_case(), _run("IP55.", []))

    assert result.fact_recall == 1.0
    assert result.cited == ()
    assert result.citation_precision == 0.0
    assert result.citation_recall == 0.0


def test_a_refusal_on_an_answerable_case_scores_the_worst_outcome():
    result = evaluate_answer(_case(), _run("Não sei.", [], has_answer=False))

    assert result.has_answer is False
    assert result.fact_hits == (False,)
    assert result.fact_recall == 0.0
    assert result.citation_precision == 0.0
    assert result.citation_recall == 0.0


def test_an_error_scores_like_a_refusal_but_is_never_an_answer():
    result = evaluate_answer(_case(), AnswerRun(answer=None, latency_ms=50.0, error="RuntimeError('cap')"))

    assert result.has_answer is False
    assert result.fact_recall == 0.0
    assert (result.citation_precision, result.citation_recall) == (0.0, 0.0)


def test_unanswerable_cases_carry_no_citation_or_fact_scores():
    case = _case(category="unanswerable", facts=(), excerpts=())

    refused = evaluate_answer(case, _run("Não há informação.", [], has_answer=False))
    hallucinated = evaluate_answer(case, _run("Custa R$ 2.000.", [_reference("manual.pdf", 1)]))

    assert refused.has_answer is False and hallucinated.has_answer is True
    assert refused.fact_recall is None and hallucinated.fact_recall is None
    assert refused.citation_precision is None and hallucinated.citation_precision is None
    assert refused.citation_recall is None and hallucinated.citation_recall is None


def _evaluated(case: GoldenCase, run: AnswerRun):
    return case, run, evaluate_answer(case, run)


def test_aggregation_splits_the_three_populations_and_sums_usage():
    usage = Usage(requests=2, tool_calls=1, input_tokens=6000, cache_read_tokens=2000, output_tokens=300)
    evaluated = [
        _evaluated(_case("a", facts=("IP55",)), _run("IP55.", [_reference("manual.pdf", 34)], usage=usage, latency_ms=1000, unmatched=("perdida", "outra perdida"))),
        _evaluated(_case("b", facts=(), excerpts=(MIRRORED,), language="en"), _run("kr.", [_reference("manual.pdf", 1)], usage=usage, latency_ms=3000)),
        _evaluated(_case("c", facts=("IP66",)), _run("Não sei.", [], has_answer=False, usage=usage, latency_ms=2000)),
        _evaluated(_case("d", facts=("x",)), AnswerRun(answer=None, latency_ms=100, error="RuntimeError('cap')")),
        _evaluated(_case("img", facts=("y",), requires_image=True), _run("y.", [_reference("manual.pdf", 34)], usage=usage)),
        _evaluated(_case("n1", category="unanswerable", facts=(), excerpts=()), _run("Não há.", [], has_answer=False, usage=usage)),
        _evaluated(_case("n2", category="unanswerable", facts=(), excerpts=()), _run("Custa 10.", [], usage=usage)),
    ]

    aggregates = aggregate_answers(evaluated)

    assert aggregates.gates == AnswerBlock(
        cases=4,
        fact_cases=3,
        fact_recall=1 / 3,
        citation_precision=0.25,
        citation_recall=0.25,
        false_refusal_rate=0.25,
    )
    assert aggregates.refusal_rate == 0.5
    assert aggregates.unanswerable_cases == 2
    assert aggregates.errors == 1
    assert aggregates.answered == 6
    assert aggregates.unmatched_citations == 2
    assert aggregates.image_diagnostic == AnswerBlock(
        cases=1, fact_cases=1, fact_recall=1.0, citation_precision=1.0, citation_recall=1.0, false_refusal_rate=0.0
    )
    assert aggregates.slices["language"]["en"].cases == 1
    assert aggregates.slices["language"]["en"].fact_recall is None
    assert aggregates.slices["document"]["cestari.pdf"].citation_precision == 0.0
    assert set(aggregates.slices) == {"persona", "language", "category", "document"}
    assert aggregates.usage == Usage(requests=12, tool_calls=6, input_tokens=36000, cache_read_tokens=12000, output_tokens=1800)
    assert aggregates.latency_mean_ms == pytest.approx((1000 + 3000 + 2000 + 100 + 1000 * 3) / 7)
    assert aggregates.latency_p95_ms == 3000


def test_aggregation_without_image_cases_has_no_diagnostic_row():
    aggregates = aggregate_answers([_evaluated(_case(), _run("IP55.", []))])

    assert aggregates.image_diagnostic is None
    assert aggregates.refusal_rate == 0.0
