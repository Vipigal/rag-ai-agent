from collections.abc import Callable, Sequence
from dataclasses import dataclass

from domain.models import RetrievedChunk, Usage
from evaluation.answers import (
    AnswerAggregates,
    AnswerBlock,
    AnswerResult,
    AnswerRun,
    AnswerSettings,
    aggregate_answers,
    evaluate_answer,
)
from evaluation.dataset import GoldenCase
from evaluation.metrics import SLICE_DIMENSIONS, CaseResult, MetricBlock, aggregate, mean, p95


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
    result: CaseResult | None
    retrieved: tuple[RetrievedChunk, ...]
    latency_ms: float | None
    answer: AnswerRun | None = None


def build_payload(
    run: RunInfo,
    case_runs: Sequence[CaseRun],
    unanswerable_excluded: int,
    answers: AnswerSettings | None = None,
) -> dict:
    scored = [cr for cr in case_runs if cr.result is not None]
    aggregates = aggregate([(cr.case, cr.result) for cr in scored if cr.result is not None])
    latencies = [cr.latency_ms for cr in scored if cr.latency_ms is not None]
    evaluated = [
        (cr.case, cr.answer, evaluate_answer(cr.case, cr.answer))
        for cr in case_runs
        if cr.answer is not None
    ]
    results = {result.case_id: result for _, _, result in evaluated}
    cases: dict[str, int] = {
        "total": len(scored) + unanswerable_excluded,
        "gated": aggregates.gates.cases,
        "image_diagnostic": aggregates.image_diagnostic.cases if aggregates.image_diagnostic else 0,
        "unanswerable_excluded": unanswerable_excluded,
    }
    if answers is not None:
        cases["answered"] = len(case_runs)
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
            "cases": cases,
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
                "mean": round(mean(latencies), 1),
                "p95": round(p95(latencies), 1),
            }
        },
        "slices": {
            dimension: {
                value: _block_dict(block)
                for value, block in aggregates.slices[dimension].items()
            }
            for dimension in SLICE_DIMENSIONS
        },
        "cases": [_case_dict(cr, results.get(cr.case.id), answers is not None) for cr in case_runs],
        "answers": (
            _answers_dict(answers, aggregate_answers(evaluated)) if answers is not None else None
        ),
    }


def _block_dict(block: MetricBlock) -> dict:
    return {
        "cases": block.cases,
        "recall_at_k": block.recall_at_k,
        "hit_rate_at_k": block.hit_rate_at_k,
        "mrr_at_k": block.mrr_at_k,
        "precision_at_k": block.precision_at_k,
    }


def _answers_dict(settings: AnswerSettings, aggregates: AnswerAggregates) -> dict:
    answered = aggregates.answered
    return {
        "llm_model": settings.llm_model,
        "tool_enabled": settings.tool_enabled,
        "max_tool_rounds": settings.max_tool_rounds,
        "workers": settings.workers,
        "gates": {
            "fact_recall": aggregates.gates.fact_recall,
            "fact_cases": aggregates.gates.fact_cases,
            "citation_precision": aggregates.gates.citation_precision,
            "citation_recall": aggregates.gates.citation_recall,
            "refusal_rate": aggregates.refusal_rate,
            "unanswerable_cases": aggregates.unanswerable_cases,
        },
        "diagnostics": {
            "false_refusal_rate": aggregates.gates.false_refusal_rate,
            "errors": aggregates.errors,
            "unmatched_citations": aggregates.unmatched_citations,
            "requires_image": (
                {
                    "fact_recall": aggregates.image_diagnostic.fact_recall,
                    "citation_precision": aggregates.image_diagnostic.citation_precision,
                    "citation_recall": aggregates.image_diagnostic.citation_recall,
                }
                if aggregates.image_diagnostic
                else None
            ),
        },
        "efficiency": {
            "latency_ms": {
                "mean": round(aggregates.latency_mean_ms, 1),
                "p95": round(aggregates.latency_p95_ms, 1),
            },
            "usage": _usage_dict(aggregates.usage),
            "per_question": {
                "requests": _per(aggregates.usage.requests, answered),
                "input_tokens": _per(aggregates.usage.input_tokens, answered),
                "output_tokens": _per(aggregates.usage.output_tokens, answered),
            },
        },
        "slices": {
            dimension: {
                value: _answer_block_dict(block)
                for value, block in aggregates.slices[dimension].items()
            }
            for dimension in SLICE_DIMENSIONS
        },
    }


def _answer_block_dict(block: AnswerBlock) -> dict:
    return {
        "cases": block.cases,
        "fact_recall": block.fact_recall,
        "citation_precision": block.citation_precision,
        "citation_recall": block.citation_recall,
        "false_refusal_rate": block.false_refusal_rate,
    }


def _usage_dict(usage: Usage) -> dict:
    return {
        "requests": usage.requests,
        "tool_calls": usage.tool_calls,
        "input_tokens": usage.input_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "output_tokens": usage.output_tokens,
    }


def _per(total: int, count: int) -> float:
    return round(total / count, 1) if count else 0.0


def _case_dict(case_run: CaseRun, answer_result: AnswerResult | None, with_answer: bool) -> dict:
    case = case_run.case
    result = case_run.result
    entry: dict = {
        "id": case.id,
        "question": case.question,
        "category": case.category,
        "persona": case.persona,
        "language": case.language,
        "notes": case.notes,
        "recall": result.recall if result else None,
        "hit": result.hit if result else None,
        "reciprocal_rank": result.reciprocal_rank if result else None,
        "precision": result.precision if result else None,
        "first_relevant_rank": result.first_relevant_rank if result else None,
        "latency_ms": round(case_run.latency_ms, 1) if case_run.latency_ms is not None else None,
        "gold_excerpts": [
            {
                "slot": slot,
                "document": excerpt.document,
                "page": excerpt.page,
                "matched_by_ranks": [
                    rank
                    for rank, slots in enumerate(result.chunk_matches if result else (), start=1)
                    if slot in slots
                ],
                "excerpt": _truncate(excerpt.text),
            }
            for slot, excerpt in enumerate(case.gold_excerpts)
        ],
        "retrieved": (
            [
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
            ]
            if result
            else None
        ),
    }
    if with_answer:
        entry["answer"] = (
            _answer_dict(case, case_run.answer, answer_result)
            if case_run.answer is not None and answer_result is not None
            else None
        )
    return entry


def _answer_dict(case: GoldenCase, run: AnswerRun, result: AnswerResult) -> dict:
    answer = run.answer
    sources: dict[tuple[str, int], str] = {}
    for reference in answer.references if answer else []:
        sources.setdefault((reference.chunk.filename, reference.chunk.page), reference.retrieval_source)
    return {
        "text": answer.text if answer else None,
        "has_answer": result.has_answer,
        "reference_answer": case.reference_answer,
        "facts": [
            {"fact": fact, "found": found}
            for fact, found in zip(case.expected_facts, result.fact_hits, strict=True)
        ],
        "fact_recall": result.fact_recall,
        "cited": [
            {"document": document, "page": page, "in_gold": in_gold, "source": sources[(document, page)]}
            for (document, page), in_gold in zip(result.cited, result.cited_in_gold, strict=True)
        ],
        "quotes": [_truncate(reference.quote) for reference in answer.references] if answer else [],
        "unmatched_citations": (
            [_truncate(quote) for quote in answer.unmatched_citations] if answer else None
        ),
        "citation_precision": result.citation_precision,
        "citation_recall": result.citation_recall,
        "latency_ms": round(run.latency_ms, 1),
        "usage": _usage_dict(answer.usage) if answer else None,
        "error": run.error,
    }


def _truncate(text: str) -> str:
    if len(text) <= 140:
        return text
    return text[:139] + "…"


GREEN = "\x1b[32m"
RED = "\x1b[31m"
YELLOW = "\x1b[33m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"

GATE_KEYS = ("recall_at_k", "hit_rate_at_k", "mrr_at_k")
ANSWER_GATE_KEYS = ("fact_recall", "citation_precision", "citation_recall", "refusal_rate")
ANSWER_SLICE_KEYS = ("fact_recall", "citation_precision", "citation_recall")

Painter = Callable[[str, str], str]


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
            _cells(payload["gates"], previous["gates"] if previous else None, GATE_KEYS, paint),
        )
    )

    lines.append("")
    lines.append(_row("BY DOCUMENT", ["cases", *metric_names]))
    previous_documents = previous["slices"]["document"] if previous else {}
    for document, block in payload["slices"]["document"].items():
        cells = _cells(block, previous_documents.get(document), GATE_KEYS, paint)
        lines.append(_row(document, [str(block["cases"]), *cells]))

    lines.append("")
    lines.append(_diagnostics_line(payload, previous, k, paint))
    latency = payload["efficiency"]["retrieval_latency_ms"]
    lines.append(
        f"EFFICIENCY    retrieval latency: mean {latency['mean']:.0f} ms · p95 {latency['p95']:.0f} ms"
    )
    answers = payload.get("answers")
    if answers is not None:
        lines.extend(_answer_lines(payload, answers, previous, paint))
    return "\n".join(lines)


def _answer_lines(payload: dict, answers: dict, previous: dict | None, paint: Painter) -> list[str]:
    previous_answers = previous.get("answers") if previous else None
    lines = [""]
    if previous is not None and previous_answers is None:
        lines.append(paint("previous run has no answer layer — answer deltas omitted", YELLOW))
    gates = answers["gates"]
    previous_gates = previous_answers["gates"] if previous_answers else None
    lines.append(
        _row(
            f"ANSWER GATES ({payload['run']['cases']['gated']} cases)",
            [
                f"fact_recall({gates['fact_cases']})",
                "cit_precision",
                "cit_recall",
                f"refusal_rate({gates['unanswerable_cases']})",
            ],
        )
    )
    lines.append(_row("overall", _cells(gates, previous_gates, ANSWER_GATE_KEYS, paint)))

    lines.append("")
    lines.append(_row("ANSWERS BY DOCUMENT", ["cases", "fact_recall", "cit_precision", "cit_recall"]))
    previous_documents = previous_answers["slices"]["document"] if previous_answers else {}
    for document, block in answers["slices"]["document"].items():
        cells = _cells(block, previous_documents.get(document), ANSWER_SLICE_KEYS, paint)
        lines.append(_row(document, [str(block["cases"]), *cells]))

    lines.append("")
    lines.append(_answer_diagnostics_line(payload, answers, previous_answers, paint))
    lines.extend(_efficiency_lines(answers))
    return lines


def _answer_diagnostics_line(
    payload: dict, answers: dict, previous_answers: dict | None, paint: Painter
) -> str:
    diagnostics = answers["diagnostics"]
    previous_diagnostics = previous_answers["diagnostics"] if previous_answers else None
    false_refusal = _delta_cell(
        diagnostics["false_refusal_rate"],
        previous_diagnostics["false_refusal_rate"] if previous_diagnostics else None,
        paint,
    )
    errors = f"errors {diagnostics['errors']}"
    line = (
        f"ANSWER DIAG   false_refusal {false_refusal}"
        f" · {paint(errors, RED) if diagnostics['errors'] else errors}"
        f" · unmatched quotes {diagnostics['unmatched_citations']}"
    )
    image = diagnostics["requires_image"]
    if image is not None:
        previous_image = previous_diagnostics["requires_image"] if previous_diagnostics else None
        image_cases = payload["run"]["cases"]["image_diagnostic"]
        recall = _delta_cell(
            image["fact_recall"],
            previous_image["fact_recall"] if previous_image else None,
            paint,
        )
        line += f" · requires_image ({image_cases}): fact_recall {recall}"
    return line


def _efficiency_lines(answers: dict) -> list[str]:
    efficiency = answers["efficiency"]
    latency = efficiency["latency_ms"]
    usage = efficiency["usage"]
    per_question = efficiency["per_question"]
    return [
        "EFFICIENCY    answer latency: "
        f"mean {latency['mean'] / 1000:.1f} s · p95 {latency['p95'] / 1000:.1f} s"
        f" ({answers['workers']} workers)"
        f" · llm calls {usage['requests']} · tool calls {usage['tool_calls']}",
        "              tokens: "
        f"in {_thousands(usage['input_tokens'])} (cached {_thousands(usage['cache_read_tokens'])})"
        f" · out {_thousands(usage['output_tokens'])}"
        f" · per question in {_thousands(per_question['input_tokens'])}"
        f" / out {_thousands(per_question['output_tokens'])}",
    ]


def _thousands(value: float) -> str:
    return f"{value / 1000:.1f}k" if value >= 1000 else f"{value:.0f}"


def _header_line(run: dict, paint: Painter) -> str:
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
    line = (
        f"{cases['total']} cases: {cases['gated']} gated"
        f" · {cases['image_diagnostic']} image-diagnostic"
        f" · {cases['unanswerable_excluded']} unanswerable (skipped)"
    )
    if "answered" in cases:
        line += f" · {cases['answered']} answered"
    return line


def _diagnostics_line(payload: dict, previous: dict | None, k: int, paint: Painter) -> str:
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


def _cells(
    block: dict, previous_block: dict | None, keys: tuple[str, ...], paint: Painter
) -> list[str]:
    return [
        _delta_cell(block[key], previous_block[key] if previous_block else None, paint)
        for key in keys
    ]


def _delta_cell(value: float | None, previous: float | None, paint: Painter) -> str:
    if value is None:
        return "n/a"
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


def _painter(color: bool) -> Painter:
    if color:
        return lambda text, code: f"{code}{text}{RESET}"
    return lambda text, code: text
