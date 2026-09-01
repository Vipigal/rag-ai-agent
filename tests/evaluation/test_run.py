import json
from datetime import datetime, timezone
from pathlib import Path

from domain.models import Chunk, RetrievedChunk
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

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        raise NotImplementedError

    def search(self, vector: list[float], k: int) -> list[RetrievedChunk]:
        raise NotImplementedError


def _execute(tmp_path: Path, store_points: int, **overrides) -> tuple[Path, list[str], list[str]]:
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    (golden_dir / "doc.yaml").write_text(GOLDEN_YAML, encoding="utf-8")
    results_dir = tmp_path / "results"
    ingested: list[str] = []
    printed: list[str] = []
    ticks = iter(range(1000))

    written = execute_run(
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
        clock=lambda: next(ticks) * 0.01,
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
