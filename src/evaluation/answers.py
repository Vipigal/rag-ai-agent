import re
from collections.abc import Sequence
from dataclasses import dataclass

from domain.models import Answer, Reference, Usage
from evaluation.dataset import GoldenCase, GoldExcerpt
from evaluation.metrics import SLICE_DIMENSIONS, mean, p95, slice_value

_DASHES = re.compile("[\u2010\u2011\u2012\u2013\u2014\u2212]")
_DIGIT_SEPARATOR = re.compile(r"(?<=\d)[.,](?=\d)")
_UNIT_SPACE = re.compile(r"(?<=\d)\s+(?=[^\W\d_]|[%°])")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class AnswerSettings:
    llm_model: str
    tool_enabled: bool
    max_tool_rounds: int
    workers: int


@dataclass(frozen=True)
class AnswerRun:
    answer: Answer | None
    latency_ms: float
    error: str | None = None


@dataclass(frozen=True)
class AnswerResult:
    case_id: str
    has_answer: bool
    fact_hits: tuple[bool, ...]
    fact_recall: float | None
    cited: tuple[tuple[str, int], ...]
    cited_in_gold: tuple[bool, ...]
    citation_precision: float | None
    citation_recall: float | None


@dataclass(frozen=True)
class AnswerBlock:
    cases: int
    fact_cases: int
    fact_recall: float | None
    citation_precision: float
    citation_recall: float
    false_refusal_rate: float


@dataclass(frozen=True)
class AnswerAggregates:
    gates: AnswerBlock
    refusal_rate: float
    unanswerable_cases: int
    errors: int
    answered: int
    unmatched_citations: int
    image_diagnostic: AnswerBlock | None
    slices: dict[str, dict[str, AnswerBlock]]
    latency_mean_ms: float
    latency_p95_ms: float
    usage: Usage


Evaluated = Sequence[tuple[GoldenCase, AnswerRun, AnswerResult]]


def normalize(text: str) -> str:
    text = _DIGIT_SEPARATOR.sub("", _DASHES.sub("-", text.casefold()))
    text = _UNIT_SPACE.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def contains_fact(answer: str, fact: str) -> bool:
    needle = normalize(fact)
    if not needle:
        return False
    start = r"(?<!\d)" if needle[0].isdigit() else r"(?<!\w)"
    end = r"(?!\d)" if needle[-1].isdigit() else r"(?!\w)"
    return re.search(start + re.escape(needle) + end, normalize(answer)) is not None


def evaluate_answer(case: GoldenCase, run: AnswerRun) -> AnswerResult:
    unanswerable = case.category == "unanswerable"
    answer = run.answer
    if answer is None or not answer.has_answer:
        return AnswerResult(
            case_id=case.id,
            has_answer=False,
            fact_hits=tuple(False for _ in case.expected_facts),
            fact_recall=0.0 if case.expected_facts else None,
            cited=(),
            cited_in_gold=(),
            citation_precision=None if unanswerable else 0.0,
            citation_recall=None if unanswerable else 0.0,
        )
    hits = tuple(contains_fact(answer.text, fact) for fact in case.expected_facts)
    cited = cited_pages(answer.references)
    gold = {page for excerpt in case.gold_excerpts for page in _pages(excerpt)}
    in_gold = tuple(page in gold for page in cited)
    return AnswerResult(
        case_id=case.id,
        has_answer=True,
        fact_hits=hits,
        fact_recall=mean([float(hit) for hit in hits]) if hits else None,
        cited=cited,
        cited_in_gold=in_gold,
        citation_precision=None if unanswerable else (sum(in_gold) / len(cited) if cited else 0.0),
        citation_recall=None if unanswerable else _slot_recall(case.gold_excerpts, set(cited)),
    )


def cited_pages(references: Sequence[Reference]) -> tuple[tuple[str, int], ...]:
    pages: list[tuple[str, int]] = []
    for reference in references:
        page = (reference.chunk.filename, reference.chunk.page)
        if page not in pages:
            pages.append(page)
    return tuple(pages)


def _pages(excerpt: GoldExcerpt) -> set[tuple[str, int]]:
    return {(variant.document, variant.page) for variant in (excerpt, *excerpt.alternates)}


def _slot_recall(excerpts: Sequence[GoldExcerpt], cited: set[tuple[str, int]]) -> float:
    if not excerpts:
        return 0.0
    covered = sum(1 for excerpt in excerpts if _pages(excerpt) & cited)
    return covered / len(excerpts)


def aggregate_answers(evaluated: Evaluated) -> AnswerAggregates:
    answerable = [item for item in evaluated if item[0].category != "unanswerable"]
    unanswerable = [item for item in evaluated if item[0].category == "unanswerable"]
    gated = [item for item in answerable if not item[0].requires_image]
    image = [item for item in answerable if item[0].requires_image]
    answered = [run.answer for _, run, _ in evaluated if run.answer is not None]
    usage = Usage()
    for answer in answered:
        usage += answer.usage
    latencies = [run.latency_ms for _, run, _ in evaluated]
    return AnswerAggregates(
        gates=_block(gated),
        refusal_rate=_refusal_rate(unanswerable),
        unanswerable_cases=len(unanswerable),
        errors=sum(1 for _, run, _ in evaluated if run.error is not None),
        answered=len(answered),
        unmatched_citations=sum(len(answer.unmatched_citations) for answer in answered),
        image_diagnostic=_block(image) if image else None,
        slices={dimension: _sliced(gated, dimension) for dimension in SLICE_DIMENSIONS},
        latency_mean_ms=mean(latencies),
        latency_p95_ms=p95(latencies),
        usage=usage,
    )


def _sliced(evaluated: Evaluated, dimension: str) -> dict[str, AnswerBlock]:
    values = sorted({slice_value(case, dimension) for case, _, _ in evaluated})
    return {
        value: _block([item for item in evaluated if slice_value(item[0], dimension) == value])
        for value in values
    }


def _block(evaluated: Evaluated) -> AnswerBlock:
    results = [result for _, _, result in evaluated]
    fact_recalls = [r.fact_recall for r in results if r.fact_recall is not None]
    return AnswerBlock(
        cases=len(results),
        fact_cases=len(fact_recalls),
        fact_recall=mean(fact_recalls) if fact_recalls else None,
        citation_precision=mean([r.citation_precision for r in results if r.citation_precision is not None]),
        citation_recall=mean([r.citation_recall for r in results if r.citation_recall is not None]),
        false_refusal_rate=_refusal_rate(evaluated),
    )


def _refusal_rate(evaluated: Evaluated) -> float:
    refusals = [float(run.error is None and not result.has_answer) for _, run, result in evaluated]
    return mean(refusals)
