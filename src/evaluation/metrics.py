from collections.abc import Sequence
from dataclasses import dataclass

from domain.models import Chunk
from evaluation.dataset import GoldenCase
from evaluation.matching import is_relevant


SLICE_DIMENSIONS = ("persona", "language", "category", "document")


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    recall: float
    hit: bool
    reciprocal_rank: float
    precision: float
    matched_excerpts: tuple[int, ...]
    first_relevant_rank: int | None
    chunk_matches: tuple[tuple[int, ...], ...] = ()


@dataclass(frozen=True)
class MetricBlock:
    cases: int
    recall_at_k: float
    hit_rate_at_k: float
    mrr_at_k: float
    precision_at_k: float


@dataclass(frozen=True)
class Aggregates:
    gates: MetricBlock
    image_diagnostic: MetricBlock | None
    slices: dict[str, dict[str, MetricBlock]]


Evaluated = Sequence[tuple[GoldenCase, CaseResult]]


def aggregate(evaluated: Evaluated) -> Aggregates:
    answerable = [(c, r) for c, r in evaluated if c.category != "unanswerable"]
    gated = [(c, r) for c, r in answerable if not c.requires_image]
    image = [(c, r) for c, r in answerable if c.requires_image]
    return Aggregates(
        gates=_metric_block(gated),
        image_diagnostic=_metric_block(image) if image else None,
        slices={
            dimension: _sliced(gated, dimension) for dimension in SLICE_DIMENSIONS
        },
    )


def _sliced(evaluated: Evaluated, dimension: str) -> dict[str, MetricBlock]:
    values = sorted({_slice_value(case, dimension) for case, _ in evaluated})
    return {
        value: _metric_block(
            [(c, r) for c, r in evaluated if _slice_value(c, dimension) == value]
        )
        for value in values
    }


def _slice_value(case: GoldenCase, dimension: str) -> str:
    if dimension == "document":
        return case.gold_excerpts[0].document
    return getattr(case, dimension)


def _metric_block(evaluated: Evaluated) -> MetricBlock:
    results = [result for _, result in evaluated]
    return MetricBlock(
        cases=len(results),
        recall_at_k=_mean([r.recall for r in results]),
        hit_rate_at_k=_mean([float(r.hit) for r in results]),
        mrr_at_k=_mean([r.reciprocal_rank for r in results]),
        precision_at_k=_mean([r.precision for r in results]),
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_case(
    case: GoldenCase, retrieved: Sequence[Chunk], k: int, threshold: float
) -> CaseResult:
    top = list(retrieved)[:k]
    chunk_matches = tuple(
        tuple(
            slot
            for slot, excerpt in enumerate(case.gold_excerpts)
            if is_relevant(chunk.text, excerpt, threshold)
        )
        for chunk in top
    )
    matched = tuple(
        slot
        for slot in range(len(case.gold_excerpts))
        if any(slot in slots for slots in chunk_matches)
    )
    relevant_flags = [bool(slots) for slots in chunk_matches]
    first = next((rank for rank, flag in enumerate(relevant_flags, start=1) if flag), None)
    return CaseResult(
        case_id=case.id,
        recall=len(matched) / len(case.gold_excerpts) if case.gold_excerpts else 0.0,
        hit=bool(matched),
        reciprocal_rank=0.0 if first is None else 1.0 / first,
        precision=sum(relevant_flags) / len(top) if top else 0.0,
        matched_excerpts=matched,
        first_relevant_rank=first,
        chunk_matches=chunk_matches,
    )
