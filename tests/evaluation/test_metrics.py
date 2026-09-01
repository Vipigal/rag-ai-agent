from domain.models import Chunk
from evaluation.dataset import GoldenCase, GoldExcerpt
from evaluation.metrics import Aggregates, CaseResult, MetricBlock, aggregate, evaluate_case

EXCERPT_A = "graxa polyrex intervalo 9500 horas"
EXCERPT_B = "tensão nominal do enrolamento 440V"
IRRELEVANT = "instalação do flange tipo C"


def _chunk(text: str) -> Chunk:
    return Chunk(
        id="c",
        document_id="d",
        filename="manual.pdf",
        text=text,
        page=1,
        section=None,
        index_in_doc=0,
    )


def _case(*excerpt_texts: str) -> GoldenCase:
    return GoldenCase(
        id="case-1",
        question="pergunta?",
        persona="operator",
        language="pt",
        category="spec_lookup",
        gold_excerpts=tuple(
            GoldExcerpt(document="manual.pdf", page=1, text=text) for text in excerpt_texts
        ),
        reference_answer="resposta",
    )


def test_relevant_chunk_at_rank_one_gives_perfect_metrics() -> None:
    retrieved = [_chunk(EXCERPT_A), _chunk(IRRELEVANT)]

    result = evaluate_case(_case(EXCERPT_A), retrieved, k=5, threshold=0.6)

    assert result == CaseResult(
        case_id="case-1",
        recall=1.0,
        hit=True,
        reciprocal_rank=1.0,
        precision=0.5,
        matched_excerpts=(0,),
        first_relevant_rank=1,
        chunk_matches=((0,), ()),
    )


def test_relevant_chunk_at_rank_three_gives_fractional_reciprocal_rank() -> None:
    retrieved = [_chunk(IRRELEVANT), _chunk(IRRELEVANT), _chunk(EXCERPT_A)]

    result = evaluate_case(_case(EXCERPT_A), retrieved, k=5, threshold=0.6)

    assert result.reciprocal_rank == 1 / 3
    assert result.first_relevant_rank == 3
    assert result.recall == 1.0


def test_no_relevant_chunk_zeroes_every_metric() -> None:
    retrieved = [_chunk(IRRELEVANT), _chunk(IRRELEVANT)]

    result = evaluate_case(_case(EXCERPT_A), retrieved, k=5, threshold=0.6)

    assert result == CaseResult(
        case_id="case-1",
        recall=0.0,
        hit=False,
        reciprocal_rank=0.0,
        precision=0.0,
        matched_excerpts=(),
        first_relevant_rank=None,
        chunk_matches=((), ()),
    )


def test_multi_excerpt_case_with_one_slot_hit_has_partial_recall() -> None:
    retrieved = [_chunk(EXCERPT_A), _chunk(IRRELEVANT)]

    result = evaluate_case(_case(EXCERPT_A, EXCERPT_B), retrieved, k=5, threshold=0.6)

    assert result.recall == 0.5
    assert result.matched_excerpts == (0,)
    assert result.hit is True
    assert result.chunk_matches == ((0,), ())


def test_duplicate_relevant_chunks_count_the_slot_once() -> None:
    retrieved = [_chunk(EXCERPT_A), _chunk(EXCERPT_A)]

    result = evaluate_case(_case(EXCERPT_A), retrieved, k=5, threshold=0.6)

    assert result.recall == 1.0
    assert result.precision == 1.0


def test_relevant_chunk_beyond_k_does_not_count() -> None:
    retrieved = [_chunk(IRRELEVANT)] * 5 + [_chunk(EXCERPT_A)]

    result = evaluate_case(_case(EXCERPT_A), retrieved, k=5, threshold=0.6)

    assert result.hit is False
    assert result.recall == 0.0


def _tagged_case(
    case_id: str,
    persona: str = "operator",
    language: str = "pt",
    category: str = "spec_lookup",
    document: str = "a.pdf",
    requires_image: bool = False,
) -> GoldenCase:
    excerpts = (
        (GoldExcerpt(document=document, page=1, text="x"),)
        if category != "unanswerable"
        else ()
    )
    return GoldenCase(
        id=case_id,
        question="pergunta?",
        persona=persona,
        language=language,
        category=category,
        gold_excerpts=excerpts,
        reference_answer="resposta",
        requires_image=requires_image,
    )


def _result(case_id: str, value: float) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        recall=value,
        hit=value > 0,
        reciprocal_rank=value,
        precision=value,
        matched_excerpts=(),
        first_relevant_rank=None,
    )


def test_aggregate_averages_gated_cases_and_diverts_image_cases() -> None:
    evaluated = [
        (_tagged_case("c1"), _result("c1", 1.0)),
        (_tagged_case("c2"), _result("c2", 0.0)),
        (_tagged_case("c3", document="c.pdf", requires_image=True), _result("c3", 1.0)),
    ]

    aggregates = aggregate(evaluated)

    assert aggregates.gates == MetricBlock(
        cases=2, recall_at_k=0.5, hit_rate_at_k=0.5, mrr_at_k=0.5, precision_at_k=0.5
    )
    assert aggregates.image_diagnostic == MetricBlock(
        cases=1, recall_at_k=1.0, hit_rate_at_k=1.0, mrr_at_k=1.0, precision_at_k=1.0
    )
    assert "c.pdf" not in aggregates.slices["document"]


def test_aggregate_excludes_unanswerable_and_handles_empty() -> None:
    evaluated = [
        (_tagged_case("n1", category="unanswerable"), _result("n1", 1.0)),
    ]

    aggregates = aggregate(evaluated)

    assert aggregates.gates.cases == 0
    assert aggregates.gates.recall_at_k == 0.0
    assert aggregates.image_diagnostic is None


def test_aggregate_slices_by_the_four_dimensions() -> None:
    evaluated = [
        (_tagged_case("c1"), _result("c1", 1.0)),
        (
            _tagged_case("c2", persona="technical", language="en", category="table_lookup"),
            _result("c2", 0.0),
        ),
        (
            _tagged_case("c3", category="table_lookup", document="b.pdf"),
            _result("c3", 1.0),
        ),
    ]

    slices = aggregate(evaluated).slices

    assert slices["document"]["a.pdf"].recall_at_k == 0.5
    assert slices["document"]["b.pdf"].recall_at_k == 1.0
    assert slices["persona"]["operator"] == MetricBlock(
        cases=2, recall_at_k=1.0, hit_rate_at_k=1.0, mrr_at_k=1.0, precision_at_k=1.0
    )
    assert slices["persona"]["technical"].recall_at_k == 0.0
    assert slices["language"]["pt"].cases == 2
    assert slices["category"]["table_lookup"].recall_at_k == 0.5
