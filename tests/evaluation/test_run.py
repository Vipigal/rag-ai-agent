import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from domain.models import Answer, Chunk, RetrievedChunk, Usage
from evaluation.answers import AnswerSettings
from evaluation.run import build_parser, execute_run

GOLDEN_YAML = """\
- id: doc-001
  question: "qual o intervalo de troca da graxa?"
  persona: operator
  language: pt
  category: spec_lookup
  gold_excerpts:
    - document: manual.pdf
      page: 2
      text: "graxa polyrex intervalo 9500 horas"
  reference_answer: "9500 horas."

- id: doc-002
  question: "qual a garantia do produto X?"
  persona: operator
  language: pt
  category: unanswerable
  gold_excerpts: []
  reference_answer: "Não há informação sobre isso nos documentos."
"""


class FakeRetriever:
    def __init__(self) -> None:
        self.queries: list[tuple[str, int]] = []

    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]:
        self.queries.append((query, k))
        chunk = Chunk(
            id="c",
            document_id="d",
            filename="manual.pdf",
            text="a graxa polyrex tem intervalo de 9500 horas",
            page=2,
            section=None,
            index_in_doc=0,
        )
        return [RetrievedChunk(chunk=chunk, score=0.9)]


class FakeStore:
    def __init__(self, points: int) -> None:
        self.points = points

    def count(self) -> int:
        return self.points

    def add(self, chunks: list[Chunk], vectors: list[list[list[float]]]) -> None:
        raise NotImplementedError

    def search(self, vector: list[float], k: int) -> list[RetrievedChunk]:
        raise NotImplementedError


def _execute(tmp_path: Path, store_points: int, **overrides) -> tuple[Path, list[str], list[str]]:
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir(exist_ok=True)
    (golden_dir / "doc.yaml").write_text(overrides.get("golden_yaml", GOLDEN_YAML), encoding="utf-8")
    results_dir = tmp_path / "results"
    ingested: list[str] = []
    printed: list[str] = []
    ticks = iter(range(1000))

    written = execute_run(
        answerer=overrides.get("answerer"),
        answer_settings=overrides.get("answer_settings"),
        label=overrides.get("label", "baseline"),
        k=5,
        threshold=0.6,
        golden_dir=golden_dir,
        results_dir=results_dir,
        retriever=FakeRetriever(),
        store=FakeStore(store_points),
        ingest=lambda: ingested.append("ingested"),
        embedding_model="text-embedding-3-small",
        collection="eval_chunks",
        git_sha="abc1234",
        git_dirty=False,
        now=lambda: datetime(2026, 9, 1, 15, 42, 10, tzinfo=timezone.utc),
        clock=overrides.get("clock", lambda: next(ticks) * 0.01),
        compare_path=overrides.get("compare_path"),
        no_compare=overrides.get("no_compare", False),
        color=False,
        write_output=printed.append,
    )
    return written, ingested, printed


def test_skips_ingestion_when_store_already_populated(tmp_path: Path) -> None:
    _, ingested, _ = _execute(tmp_path, store_points=570)

    assert ingested == []


def test_ingests_when_store_is_empty(tmp_path: Path) -> None:
    _, ingested, _ = _execute(tmp_path, store_points=0)

    assert ingested == ["ingested"]


def test_writes_results_json_with_filename_convention(tmp_path: Path) -> None:
    written, _, printed = _execute(tmp_path, store_points=570)

    assert written.name == "20260901-154210-baseline.json"
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["run"]["label"] == "baseline"
    assert payload["run"]["cases"]["unanswerable_excluded"] == 1
    assert payload["gates"]["recall_at_k"] == 1.0
    assert len(payload["cases"]) == 1
    assert payload["cases"][0]["latency_ms"] == 10.0
    assert payload["answers"] is None
    assert "answer" not in payload["cases"][0]
    assert "eval run — baseline" in printed[0]


def test_compares_against_latest_result_with_matching_parameters(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    matching = {
        "run": {"k": 5, "token_overlap_threshold": 0.6},
        "gates": {"recall_at_k": 0.5, "hit_rate_at_k": 0.5, "mrr_at_k": 0.5},
        "diagnostics": {"precision_at_k": 0.5, "requires_image": None},
        "slices": {"document": {}},
    }
    mismatching = {
        "run": {"k": 10, "token_overlap_threshold": 0.6},
        "gates": {"recall_at_k": 0.9, "hit_rate_at_k": 0.9, "mrr_at_k": 0.9},
        "diagnostics": {"precision_at_k": 0.9, "requires_image": None},
        "slices": {"document": {}},
    }
    (results_dir / "20260801-000000-old.json").write_text(
        json.dumps(matching), encoding="utf-8"
    )
    (results_dir / "20260901-000000-newer.json").write_text(
        json.dumps(mismatching), encoding="utf-8"
    )

    _, _, printed = _execute(tmp_path, store_points=570)

    assert "compared against 20260801-000000-old.json" in printed[0]
    assert "(+0.50)" in printed[0]


def test_no_compare_flag_suppresses_comparison(tmp_path: Path) -> None:
    _, _, printed = _execute(tmp_path, store_points=570, no_compare=True)

    assert "no comparable previous run" in printed[0]


def test_cli_parser_defaults_match_the_spec() -> None:
    args = build_parser().parse_args(["--label", "baseline"])

    assert args.label == "baseline"
    assert args.k == 5
    assert args.threshold == 0.6
    assert args.compare is None
    assert args.no_compare is False


SETTINGS = AnswerSettings(
    llm_model="openai:gpt-5-mini", tool_enabled=True, max_tool_rounds=3, workers=1, thinking="low"
)


def _answer(text: str, has_answer: bool = True) -> Answer:
    return Answer(text=text, references=[], has_answer=has_answer, usage=Usage(requests=1, input_tokens=100, output_tokens=10))


def test_answers_every_case_including_unanswerable_ones_and_records_the_settings(tmp_path: Path) -> None:
    asked: list[str] = []

    def answerer(question: str) -> Answer:
        asked.append(question)
        return _answer("9500 horas.") if "graxa" in question else _answer("Não há informação.", has_answer=False)

    written, _, printed = _execute(tmp_path, store_points=570, answerer=answerer, answer_settings=SETTINGS)

    payload = json.loads(written.read_text(encoding="utf-8"))
    assert asked == ["qual o intervalo de troca da graxa?", "qual a garantia do produto X?"]
    assert payload["run"]["cases"] == {"total": 2, "gated": 1, "image_diagnostic": 0, "unanswerable_excluded": 1, "answered": 2}
    assert [case["id"] for case in payload["cases"]] == ["doc-001", "doc-002"]
    assert payload["cases"][1]["recall"] is None and payload["cases"][1]["retrieved"] is None
    assert payload["cases"][0]["answer"]["text"] == "9500 horas."
    assert payload["cases"][0]["answer"]["latency_ms"] == 10.0
    assert payload["answers"]["llm_model"] == "openai:gpt-5-mini"
    assert payload["answers"]["thinking"] == "low"
    assert payload["answers"]["gates"]["refusal_rate"] == 1.0
    assert payload["answers"]["efficiency"]["usage"]["requests"] == 2
    assert "answering 2 cases with 1 worker(s) · openai:gpt-5-mini · thinking low · tool on" in printed[0]
    assert "ANSWER GATES" in printed[1]


def test_an_answer_that_raises_is_recorded_as_an_error_and_the_run_completes(tmp_path: Path) -> None:
    def answerer(question: str) -> Answer:
        raise RuntimeError("the model kept requesting tools")

    written, _, _ = _execute(tmp_path, store_points=570, answerer=answerer, answer_settings=SETTINGS)

    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["answers"]["diagnostics"]["errors"] == 2
    assert payload["cases"][0]["answer"]["error"] == "RuntimeError('the model kept requesting tools')"
    assert payload["cases"][0]["answer"]["text"] is None
    assert payload["cases"][0]["answer"]["fact_recall"] is None


FOUR_CASES = "".join(
    f"""
- id: doc-{i:03d}
  question: "pergunta {i}?"
  persona: operator
  language: pt
  category: spec_lookup
  gold_excerpts:
    - document: manual.pdf
      page: 2
      text: "graxa polyrex intervalo 9500 horas"
  reference_answer: "9500 horas."
"""
    for i in range(1, 5)
)


def test_concurrent_workers_keep_the_dataset_order(tmp_path: Path) -> None:
    def answerer(question: str) -> Answer:
        time.sleep(0.05 * (5 - int(question.split()[1].rstrip("?"))))
        return _answer(question)

    written, _, _ = _execute(
        tmp_path,
        store_points=570,
        golden_yaml=FOUR_CASES,
        answerer=answerer,
        answer_settings=AnswerSettings(llm_model="m", tool_enabled=False, max_tool_rounds=0, workers=4),
        clock=time.perf_counter,
    )

    payload = json.loads(written.read_text(encoding="utf-8"))
    assert [case["answer"]["text"] for case in payload["cases"]] == [f"pergunta {i}?" for i in range(1, 5)]
    assert payload["answers"]["workers"] == 4


def _result_file(results_dir: Path, name: str, answers: dict | None, include_key: bool = True) -> None:
    payload = {
        "run": {"k": 5, "token_overlap_threshold": 0.6},
        "gates": {"recall_at_k": 0.5, "hit_rate_at_k": 0.5, "mrr_at_k": 0.5},
        "diagnostics": {"precision_at_k": 0.5, "requires_image": None},
        "slices": {"document": {}},
    }
    if include_key:
        payload["answers"] = answers
    (results_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _answers_block() -> dict:
    return {
        "gates": {"fact_recall": 0.5, "fact_cases": 1, "citation_precision": 0.5, "citation_recall": 0.5, "refusal_rate": 0.5, "unanswerable_cases": 1},
        "diagnostics": {"false_refusal_rate": 0.0, "errors": 0, "unmatched_citations": 0, "requires_image": None},
        "slices": {"document": {}},
    }


def test_answer_runs_compare_against_the_latest_run_that_also_has_answers(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _result_file(results_dir, "20260801-000000-with-answers.json", _answers_block())
    _result_file(results_dir, "20260901-000000-retrieval-only.json", None, include_key=False)

    _, _, retrieval_only = _execute(tmp_path, store_points=570)
    _, _, with_answers = _execute(tmp_path, store_points=570, answerer=lambda q: _answer("x"), answer_settings=SETTINGS)

    assert "compared against 20260801-000000-with-answers.json" in with_answers[1]
    assert "compared against 20260901-000000-retrieval-only.json" in retrieval_only[0]


def test_answer_run_without_an_answer_baseline_falls_back_to_the_retrieval_baseline(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _result_file(results_dir, "20260901-000000-retrieval-only.json", None)

    _, _, printed = _execute(tmp_path, store_points=570, answerer=lambda q: _answer("x"), answer_settings=SETTINGS)

    assert "compared against 20260901-000000-retrieval-only.json" in printed[1]
    assert "previous run has no answer layer" in printed[1]


def test_cli_parser_answer_flags_default_to_off_and_four_workers() -> None:
    args = build_parser().parse_args(["--label", "agent-tool-on"])

    assert args.answers is False
    assert args.workers == 4
    assert build_parser().parse_args(["--label", "x", "--answers", "--workers", "8"]).workers == 8


def test_each_answered_case_logs_its_progress(tmp_path: Path, caplog) -> None:
    caplog.set_level("INFO", logger="evaluation.run")

    _execute(tmp_path, store_points=570, answerer=lambda q: _answer("x"), answer_settings=SETTINGS)

    progress = [record.getMessage() for record in caplog.records if "answered" in record.getMessage()]
    assert progress == ["doc-001: answered in 0.0s (1 request(s))", "doc-002: answered in 0.0s (1 request(s))"]


def test_a_failing_case_logs_the_error(tmp_path: Path, caplog) -> None:
    caplog.set_level("INFO", logger="evaluation.run")

    def answerer(question: str) -> Answer:
        raise RuntimeError("boom")

    _execute(tmp_path, store_points=570, answerer=answerer, answer_settings=SETTINGS)

    assert "doc-001: error after 0.0s: RuntimeError('boom')" in [r.getMessage() for r in caplog.records]
