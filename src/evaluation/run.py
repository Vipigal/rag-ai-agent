import argparse
import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from domain.models import Answer
from domain.ports import Retriever, VectorStore
from evaluation.answers import AnswerRun, AnswerSettings
from evaluation.dataset import GoldenCase, load_golden_cases
from evaluation.metrics import evaluate_case
from evaluation.report import CaseRun, RunInfo, build_payload, render

Answerer = Callable[[str], Answer]

log = logging.getLogger("evaluation.run")


def execute_run(
    *,
    label: str,
    k: int,
    threshold: float,
    golden_dir: Path,
    results_dir: Path,
    retriever: Retriever,
    store: VectorStore,
    ingest: Callable[[], None],
    embedding_model: str,
    collection: str,
    git_sha: str | None,
    git_dirty: bool,
    now: Callable[[], datetime],
    clock: Callable[[], float],
    compare_path: Path | None,
    no_compare: bool,
    color: bool,
    write_output: Callable[[str], None],
    answerer: Answerer | None = None,
    answer_settings: AnswerSettings | None = None,
) -> Path:
    if (answerer is None) != (answer_settings is None):
        raise ValueError("answerer and answer_settings must be given together")
    cases = load_golden_cases(golden_dir)
    if store.count() == 0:
        ingest()

    scored: dict[str, CaseRun] = {}
    for case in cases:
        if case.category == "unanswerable":
            continue
        started = clock()
        retrieved = retriever.retrieve(case.question, k)
        latency_ms = (clock() - started) * 1000
        result = evaluate_case(case, [r.chunk for r in retrieved], k, threshold)
        scored[case.id] = CaseRun(
            case=case, result=result, retrieved=tuple(retrieved), latency_ms=latency_ms
        )

    answer_runs: dict[str, AnswerRun] = {}
    if answerer is not None and answer_settings is not None:
        write_output(
            f"answering {len(cases)} cases with {answer_settings.workers} worker(s)"
            f" · {answer_settings.llm_model} · tool {'on' if answer_settings.tool_enabled else 'off'}"
        )
        answer_runs = _answer_all(cases, answerer, answer_settings.workers, clock)

    case_runs = [
        replace(
            scored.get(case.id, CaseRun(case=case, result=None, retrieved=(), latency_ms=None)),
            answer=answer_runs.get(case.id),
        )
        for case in cases
        if case.id in scored or case.id in answer_runs
    ]
    unanswerable_excluded = sum(1 for case in cases if case.category == "unanswerable")

    at = now()
    run_info = RunInfo(
        at=at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        label=label,
        git_sha=git_sha,
        git_dirty=git_dirty,
        k=k,
        token_overlap_threshold=threshold,
        embedding_model=embedding_model,
        collection=collection,
    )
    payload = build_payload(
        run_info, case_runs, unanswerable_excluded=unanswerable_excluded, answers=answer_settings
    )

    compare, compare_name = _resolve_compare(
        results_dir, compare_path, no_compare, k, threshold, with_answers=answerer is not None
    )

    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / f"{at.strftime('%Y%m%d-%H%M%S')}-{label}.json"
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    write_output(render(payload, compare, compare_name, color))
    write_output(f"→ {out_path}")
    return out_path


def _answer_all(
    cases: tuple[GoldenCase, ...],
    answerer: Answerer,
    workers: int,
    clock: Callable[[], float],
) -> dict[str, AnswerRun]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        runs = list(pool.map(lambda case: _answer_case(answerer, case, clock), cases))
    return {case.id: run for case, run in zip(cases, runs, strict=True)}


def _answer_case(answerer: Answerer, case: GoldenCase, clock: Callable[[], float]) -> AnswerRun:
    started = clock()
    try:
        answer = answerer(case.question)
    except Exception as exc:
        elapsed_ms = (clock() - started) * 1000
        log.info("%s: error after %.1fs: %r", case.id, elapsed_ms / 1000, exc)
        return AnswerRun(answer=None, latency_ms=elapsed_ms, error=repr(exc))
    elapsed_ms = (clock() - started) * 1000
    log.info(
        "%s: answered in %.1fs (%d request(s))", case.id, elapsed_ms / 1000, answer.usage.requests
    )
    return AnswerRun(answer=answer, latency_ms=elapsed_ms)


def _resolve_compare(
    results_dir: Path,
    compare_path: Path | None,
    no_compare: bool,
    k: int,
    threshold: float,
    with_answers: bool,
) -> tuple[dict | None, str | None]:
    if no_compare:
        return None, None
    if compare_path is not None:
        return _load_json(compare_path), compare_path.name
    if not results_dir.exists():
        return None, None
    comparable = [
        (path, candidate)
        for path, candidate in (
            (path, _load_json(path)) for path in sorted(results_dir.glob("*.json"), reverse=True)
        )
        if candidate["run"]["k"] == k and candidate["run"]["token_overlap_threshold"] == threshold
    ]
    if with_answers:
        for path, candidate in comparable:
            if candidate.get("answers") is not None:
                return candidate, path.name
    for path, candidate in comparable:
        return candidate, path.name
    return None, None


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.run",
        description="Run the retrieval eval over the golden dataset.",
    )
    parser.add_argument("--label", required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.6)
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    compare_group = parser.add_mutually_exclusive_group()
    compare_group.add_argument("--compare", type=Path, default=None)
    compare_group.add_argument("--no-compare", action="store_true")
    return parser


def _git_state() -> tuple[str | None, bool]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return sha, status != ""
    except (OSError, subprocess.CalledProcessError):
        return None, False


def main() -> None:
    from api.composition import (
        agent_max_tool_rounds,
        build_agent_service,
        build_ingestion_service,
        build_vector_store,
        embedding_model_name,
        get_embedder,
        llm_model,
        llm_model_name,
        query_knowledge_enabled,
    )
    from llm.pydantic_ai_llm import PydanticAiLLM
    from retrieval.vector_retriever import VectorRetriever

    args = build_parser().parse_args()
    logging.basicConfig(format="%(levelname)s:     %(name)s: %(message)s", level=logging.INFO)
    for noisy in ("httpx", "httpx2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    collection = os.environ.get("EVAL_QDRANT_COLLECTION", "eval_chunks")
    store = build_vector_store(collection)
    ingestion_service = build_ingestion_service(store)
    retriever = VectorRetriever(get_embedder(), store)
    case_files_dir = Path("case_files")

    def ingest() -> None:
        files = [
            (path.name, path.read_bytes())
            for path in sorted(case_files_dir.glob("*.pdf"))
        ]
        ingestion_service.ingest(files)

    answerer: Answerer | None = None
    answer_settings: AnswerSettings | None = None
    if args.answers:
        agent = build_agent_service(retriever, PydanticAiLLM(llm_model()), k=args.k)
        answerer = agent.answer
        answer_settings = AnswerSettings(
            llm_model=llm_model_name(),
            tool_enabled=query_knowledge_enabled(),
            max_tool_rounds=agent_max_tool_rounds(),
            workers=args.workers,
        )

    git_sha, git_dirty = _git_state()
    execute_run(
        label=args.label,
        k=args.k,
        threshold=args.threshold,
        golden_dir=Path("evals/golden"),
        results_dir=Path("evals/results"),
        retriever=retriever,
        store=store,
        ingest=ingest,
        embedding_model=embedding_model_name(),
        collection=collection,
        git_sha=git_sha,
        git_dirty=git_dirty,
        now=lambda: datetime.now(timezone.utc),
        clock=time.perf_counter,
        compare_path=args.compare,
        no_compare=args.no_compare,
        color=sys.stdout.isatty() and "NO_COLOR" not in os.environ,
        write_output=print,
        answerer=answerer,
        answer_settings=answer_settings,
    )


if __name__ == "__main__":
    main()
