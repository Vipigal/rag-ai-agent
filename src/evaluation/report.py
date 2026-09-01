import math
from collections.abc import Sequence
from dataclasses import dataclass

from domain.models import RetrievedChunk
from evaluation.dataset import GoldenCase
from evaluation.metrics import SLICE_DIMENSIONS, CaseResult, MetricBlock, aggregate


@dataclass(frozen=True)
class RunInfo:
    at: str
    label: str
    git_sha: str | None
    git_dirty: bool
    k: int
    token_overlap_threshold: float
    embedding_model: str
    collection: str


@dataclass(frozen=True)
class CaseRun:
    case: GoldenCase
    result: CaseResult
    retrieved: tuple[RetrievedChunk, ...]
    latency_ms: float


def build_payload(
    run: RunInfo, case_runs: Sequence[CaseRun], unanswerable_excluded: int
) -> dict:
    aggregates = aggregate([(cr.case, cr.result) for cr in case_runs])
    latencies = [cr.latency_ms for cr in case_runs]
    return {
        "run": {
            "at": run.at,
            "label": run.label,
            "git_sha": run.git_sha,
            "git_dirty": run.git_dirty,
            "k": run.k,
            "token_overlap_threshold": run.token_overlap_threshold,
            "embedding_model": run.embedding_model,
            "collection": run.collection,
            "cases": {
                "total": len(case_runs) + unanswerable_excluded,
                "gated": aggregates.gates.cases,
                "image_diagnostic": (
                    aggregates.image_diagnostic.cases if aggregates.image_diagnostic else 0
                ),
                "unanswerable_excluded": unanswerable_excluded,
            },
        },
        "gates": {
            "recall_at_k": aggregates.gates.recall_at_k,
            "hit_rate_at_k": aggregates.gates.hit_rate_at_k,
            "mrr_at_k": aggregates.gates.mrr_at_k,
        },
        "diagnostics": {
            "precision_at_k": aggregates.gates.precision_at_k,
            "requires_image": (
                {
                    "recall_at_k": aggregates.image_diagnostic.recall_at_k,
                    "hit_rate_at_k": aggregates.image_diagnostic.hit_rate_at_k,
                    "mrr_at_k": aggregates.image_diagnostic.mrr_at_k,
                }
                if aggregates.image_diagnostic
                else None
            ),
        },
        "efficiency": {
            "retrieval_latency_ms": {
                "mean": round(_mean(latencies), 1),
                "p95": round(_p95(latencies), 1),
            }
        },
        "slices": {
            dimension: {
                value: _block_dict(block)
                for value, block in aggregates.slices[dimension].items()
            }
            for dimension in SLICE_DIMENSIONS
        },
        "cases": [_case_dict(cr) for cr in case_runs],
    }


def _block_dict(block: MetricBlock) -> dict:
    return {
        "cases": block.cases,
        "recall_at_k": block.recall_at_k,
        "hit_rate_at_k": block.hit_rate_at_k,
        "mrr_at_k": block.mrr_at_k,
        "precision_at_k": block.precision_at_k,
    }


def _case_dict(case_run: CaseRun) -> dict:
    case = case_run.case
    result = case_run.result
    return {
        "id": result.case_id,
        "question": case.question,
        "category": case.category,
        "persona": case.persona,
        "language": case.language,
        "notes": case.notes,
        "recall": result.recall,
        "hit": result.hit,
        "reciprocal_rank": result.reciprocal_rank,
        "precision": result.precision,
        "first_relevant_rank": result.first_relevant_rank,
        "latency_ms": round(case_run.latency_ms, 1),
        "gold_excerpts": [
            {
                "slot": slot,
                "document": excerpt.document,
                "page": excerpt.page,
                "matched_by_ranks": [
                    rank
                    for rank, slots in enumerate(result.chunk_matches, start=1)
                    if slot in slots
                ],
                "excerpt": _truncate(excerpt.text),
            }
            for slot, excerpt in enumerate(case.gold_excerpts)
        ],
        "retrieved": [
            {
                "rank": rank,
                "document": retrieved.chunk.filename,
                "page": retrieved.chunk.page,
                "score": round(retrieved.score, 3),
                "matches_slots": (
                    list(result.chunk_matches[rank - 1])
                    if rank - 1 < len(result.chunk_matches)
                    else []
                ),
                "preview": _truncate(retrieved.chunk.text),
            }
            for rank, retrieved in enumerate(case_run.retrieved, start=1)
        ],
    }


def _truncate(text: str) -> str:
    if len(text) <= 140:
        return text
    return text[:139] + "…"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


GREEN = "\x1b[32m"
RED = "\x1b[31m"
YELLOW = "\x1b[33m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"

GATE_KEYS = ("recall_at_k", "hit_rate_at_k", "mrr_at_k")


def render(
    payload: dict,
    compare: dict | None,
    compare_name: str | None,
    color: bool,
) -> str:
    paint = _painter(color)
    run = payload["run"]
    k = run["k"]
    lines = [_header_line(run, paint), _params_line(run), _cases_line(run)]

    previous = None
    if compare is None:
        lines.append(paint("no comparable previous run — deltas omitted", YELLOW))
    elif (
        compare["run"]["k"] != k
        or compare["run"]["token_overlap_threshold"] != run["token_overlap_threshold"]
    ):
        lines.append(
            paint("previous run has different k/threshold — deltas suppressed", YELLOW)
        )
    else:
        lines.append(f"compared against {compare_name}")
        previous = compare

    metric_names = [f"recall@{k}", f"hit_rate@{k}", f"mrr@{k}"]
    lines.append("")
    lines.append(_row(f"GATES ({run['cases']['gated']} cases)", metric_names))
    lines.append(
        _row(
            "overall",
            _cells(payload["gates"], previous["gates"] if previous else None, paint),
        )
    )

    lines.append("")
    lines.append(_row("BY DOCUMENT", ["cases", *metric_names]))
    previous_documents = previous["slices"]["document"] if previous else {}
    for document, block in payload["slices"]["document"].items():
        cells = _cells(block, previous_documents.get(document), paint)
        lines.append(_row(document, [str(block["cases"]), *cells]))

    lines.append("")
    lines.append(_diagnostics_line(payload, previous, k, paint))
    latency = payload["efficiency"]["retrieval_latency_ms"]
    lines.append(
        f"EFFICIENCY    retrieval latency: mean {latency['mean']:.0f} ms · p95 {latency['p95']:.0f} ms"
    )
    return "\n".join(lines)


def _header_line(run: dict, paint) -> str:
    dirty = " (dirty)" if run["git_dirty"] else ""
    sha = run["git_sha"] or "no-git"
    return paint(f"eval run — {run['label']} · {sha}{dirty} · {run['at']}", BOLD)


def _params_line(run: dict) -> str:
    return (
        f"k={run['k']} · threshold={run['token_overlap_threshold']}"
        f" · collection={run['collection']} · {run['embedding_model']}"
    )


def _cases_line(run: dict) -> str:
    cases = run["cases"]
    return (
        f"{cases['total']} cases: {cases['gated']} gated"
        f" · {cases['image_diagnostic']} image-diagnostic"
        f" · {cases['unanswerable_excluded']} unanswerable (skipped)"
    )


def _diagnostics_line(payload: dict, previous: dict | None, k: int, paint) -> str:
    precision = _delta_cell(
        payload["diagnostics"]["precision_at_k"],
        previous["diagnostics"]["precision_at_k"] if previous else None,
        paint,
    )
    line = f"DIAGNOSTICS   precision@{k} {precision}"
    image = payload["diagnostics"]["requires_image"]
    if image is not None:
        previous_image = previous["diagnostics"]["requires_image"] if previous else None
        image_cases = payload["run"]["cases"]["image_diagnostic"]
        recall = _delta_cell(
            image["recall_at_k"],
            previous_image["recall_at_k"] if previous_image else None,
            paint,
        )
        line += f" · requires_image ({image_cases}): recall@{k} {recall}"
    return line


def _cells(block: dict, previous_block: dict | None, paint) -> list[str]:
    return [
        _delta_cell(block[key], previous_block[key] if previous_block else None, paint)
        for key in GATE_KEYS
    ]


def _delta_cell(value: float, previous: float | None, paint) -> str:
    base = f"{value:.2f}"
    if previous is None:
        return base
    delta = round(value - previous, 2)
    if delta == 0:
        return f"{base} {paint('(=)', DIM)}"
    code = GREEN if delta > 0 else RED
    return f"{base} {paint(f'({delta:+.2f})', code)}"


def _row(label: str, cells: list[str]) -> str:
    return "  ".join([f"{label:<24}", *(f"{cell:<15}" for cell in cells)]).rstrip()


def _painter(color: bool):
    if color:
        return lambda text, code: f"{code}{text}{RESET}"
    return lambda text, code: text
