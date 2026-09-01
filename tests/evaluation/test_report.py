from domain.models import Chunk, RetrievedChunk
from evaluation.dataset import GoldenCase, GoldExcerpt
from evaluation.metrics import CaseResult
from evaluation.report import CaseRun, RunInfo, build_payload, render

RUN_INFO = RunInfo(
    at="2026-09-01T15:20:00Z",
    label="baseline",
    git_sha="f518762",
    git_dirty=False,
    k=5,
    token_overlap_threshold=0.6,
    embedding_model="text-embedding-3-small",
    collection="eval_chunks",
)


def _case(case_id: str, requires_image: bool = False) -> GoldenCase:
    return GoldenCase(
        id=case_id,
        question="qual o grau de proteção?",
        persona="operator",
        language="pt",
        category="spec_lookup",
        gold_excerpts=(GoldExcerpt(document="manual.pdf", page=34, text="grau de proteção IP55"),),
        reference_answer="resposta",
        requires_image=requires_image,
        notes="armadilha da tabela 8.6",
    )


def _retrieved(score: float, text: str = "trecho recuperado") -> RetrievedChunk:
    chunk = Chunk(
        id="c",
        document_id="d",
        filename="manual.pdf",
        text=text,
        page=34,
        section=None,
        index_in_doc=0,
    )
    return RetrievedChunk(chunk=chunk, score=score)


def test_build_payload_matches_results_schema() -> None:
    case_runs = [
        CaseRun(
            case=_case("weg-guia-012"),
            result=CaseResult(
                case_id="weg-guia-012",
                recall=1.0,
                hit=True,
                reciprocal_rank=0.5,
                precision=0.5,
                matched_excerpts=(0,),
                first_relevant_rank=2,
                chunk_matches=((), (0,)),
            ),
            retrieved=(
                _retrieved(0.61234),
                _retrieved(0.53882, text="o grau de proteção IP55 consta na tabela"),
            ),
            latency_ms=38.2,
        ),
        CaseRun(
            case=_case("mn414-016", requires_image=True),
            result=CaseResult(
                case_id="mn414-016",
                recall=0.0,
                hit=False,
                reciprocal_rank=0.0,
                precision=0.0,
                matched_excerpts=(),
                first_relevant_rank=None,
                chunk_matches=((),),
            ),
            retrieved=(_retrieved(0.11),),
            latency_ms=41.8,
        ),
    ]

    payload = build_payload(RUN_INFO, case_runs, unanswerable_excluded=1)

    assert payload == {
        "run": {
            "at": "2026-09-01T15:20:00Z",
            "label": "baseline",
            "git_sha": "f518762",
            "git_dirty": False,
            "k": 5,
            "token_overlap_threshold": 0.6,
            "embedding_model": "text-embedding-3-small",
            "collection": "eval_chunks",
            "cases": {
                "total": 3,
                "gated": 1,
                "image_diagnostic": 1,
                "unanswerable_excluded": 1,
            },
        },
        "gates": {"recall_at_k": 1.0, "hit_rate_at_k": 1.0, "mrr_at_k": 0.5},
        "diagnostics": {
            "precision_at_k": 0.5,
            "requires_image": {
                "recall_at_k": 0.0,
                "hit_rate_at_k": 0.0,
                "mrr_at_k": 0.0,
            },
        },
        "efficiency": {"retrieval_latency_ms": {"mean": 40.0, "p95": 41.8}},
        "slices": {
            "persona": {
                "operator": {
                    "cases": 1,
                    "recall_at_k": 1.0,
                    "hit_rate_at_k": 1.0,
                    "mrr_at_k": 0.5,
                    "precision_at_k": 0.5,
                }
            },
            "language": {
                "pt": {
                    "cases": 1,
                    "recall_at_k": 1.0,
                    "hit_rate_at_k": 1.0,
                    "mrr_at_k": 0.5,
                    "precision_at_k": 0.5,
                }
            },
            "category": {
                "spec_lookup": {
                    "cases": 1,
                    "recall_at_k": 1.0,
                    "hit_rate_at_k": 1.0,
                    "mrr_at_k": 0.5,
                    "precision_at_k": 0.5,
                }
            },
            "document": {
                "manual.pdf": {
                    "cases": 1,
                    "recall_at_k": 1.0,
                    "hit_rate_at_k": 1.0,
                    "mrr_at_k": 0.5,
                    "precision_at_k": 0.5,
                }
            },
        },
        "cases": [
            {
                "id": "weg-guia-012",
                "question": "qual o grau de proteção?",
                "category": "spec_lookup",
                "persona": "operator",
                "language": "pt",
                "notes": "armadilha da tabela 8.6",
                "recall": 1.0,
                "hit": True,
                "reciprocal_rank": 0.5,
                "precision": 0.5,
                "first_relevant_rank": 2,
                "latency_ms": 38.2,
                "gold_excerpts": [
                    {
                        "slot": 0,
                        "document": "manual.pdf",
                        "page": 34,
                        "matched_by_ranks": [2],
                        "excerpt": "grau de proteção IP55",
                    }
                ],
                "retrieved": [
                    {
                        "rank": 1,
                        "document": "manual.pdf",
                        "page": 34,
                        "score": 0.612,
                        "matches_slots": [],
                        "preview": "trecho recuperado",
                    },
                    {
                        "rank": 2,
                        "document": "manual.pdf",
                        "page": 34,
                        "score": 0.539,
                        "matches_slots": [0],
                        "preview": "o grau de proteção IP55 consta na tabela",
                    },
                ],
            },
            {
                "id": "mn414-016",
                "question": "qual o grau de proteção?",
                "category": "spec_lookup",
                "persona": "operator",
                "language": "pt",
                "notes": "armadilha da tabela 8.6",
                "recall": 0.0,
                "hit": False,
                "reciprocal_rank": 0.0,
                "precision": 0.0,
                "first_relevant_rank": None,
                "latency_ms": 41.8,
                "gold_excerpts": [
                    {
                        "slot": 0,
                        "document": "manual.pdf",
                        "page": 34,
                        "matched_by_ranks": [],
                        "excerpt": "grau de proteção IP55",
                    }
                ],
                "retrieved": [
                    {
                        "rank": 1,
                        "document": "manual.pdf",
                        "page": 34,
                        "score": 0.11,
                        "matches_slots": [],
                        "preview": "trecho recuperado",
                    }
                ],
            },
        ],
    }


def test_build_payload_truncates_long_excerpts_and_previews() -> None:
    long_text = "azul " * 60
    case_run = CaseRun(
        case=GoldenCase(
            id="doc-001",
            question="pergunta?",
            persona="operator",
            language="pt",
            category="spec_lookup",
            gold_excerpts=(GoldExcerpt(document="manual.pdf", page=1, text=long_text),),
            reference_answer="resposta",
        ),
        result=CaseResult(
            case_id="doc-001",
            recall=1.0,
            hit=True,
            reciprocal_rank=1.0,
            precision=1.0,
            matched_excerpts=(0,),
            first_relevant_rank=1,
            chunk_matches=((0,),),
        ),
        retrieved=(_retrieved(0.9, text=long_text),),
        latency_ms=10.0,
    )

    case = build_payload(RUN_INFO, [case_run], unanswerable_excluded=0)["cases"][0]

    assert len(case["gold_excerpts"][0]["excerpt"]) == 140
    assert case["gold_excerpts"][0]["excerpt"].endswith("…")
    assert len(case["retrieved"][0]["preview"]) == 140
    assert case["retrieved"][0]["preview"].endswith("…")


def _block(recall: float) -> dict:
    return {
        "cases": 8,
        "recall_at_k": recall,
        "hit_rate_at_k": recall,
        "mrr_at_k": recall,
        "precision_at_k": recall,
    }


def _payload(
    recall: float = 0.61,
    hit: float = 0.70,
    mrr: float = 0.55,
    k: int = 5,
    threshold: float = 0.6,
    dirty: bool = False,
) -> dict:
    return {
        "run": {
            "at": "2026-09-08T11:02:44Z",
            "label": "ocr-gate",
            "git_sha": "3ab9f01",
            "git_dirty": dirty,
            "k": k,
            "token_overlap_threshold": threshold,
            "embedding_model": "text-embedding-3-small",
            "collection": "eval_chunks",
            "cases": {
                "total": 93,
                "gated": 83,
                "image_diagnostic": 2,
                "unanswerable_excluded": 8,
            },
        },
        "gates": {"recall_at_k": recall, "hit_rate_at_k": hit, "mrr_at_k": mrr},
        "diagnostics": {
            "precision_at_k": 0.34,
            "requires_image": {"recall_at_k": 0.0, "hit_rate_at_k": 0.0, "mrr_at_k": 0.0},
        },
        "efficiency": {"retrieval_latency_ms": {"mean": 44.0, "p95": 91.0}},
        "slices": {
            "persona": {},
            "language": {},
            "category": {},
            "document": {"LB5001.pdf": _block(0.88)},
        },
        "cases": [],
    }


def test_render_without_compare_shows_header_gates_slice_and_notice() -> None:
    output = render(_payload(dirty=True), compare=None, compare_name=None, color=False)

    assert "eval run — ocr-gate · 3ab9f01 (dirty) · 2026-09-08T11:02:44Z" in output
    assert "k=5 · threshold=0.6 · collection=eval_chunks · text-embedding-3-small" in output
    assert "93 cases: 83 gated · 2 image-diagnostic · 8 unanswerable (skipped)" in output
    assert "no comparable previous run" in output
    assert "recall@5" in output
    assert "0.61" in output
    assert "LB5001.pdf" in output
    assert "precision@5 0.34" in output
    assert "mean 44 ms · p95 91 ms" in output
    assert "\x1b[" not in output


def test_render_with_comparable_run_shows_signed_deltas() -> None:
    current = _payload(recall=0.61, hit=0.70, mrr=0.55)
    previous = _payload(recall=0.54, hit=0.72, mrr=0.55)

    output = render(current, compare=previous, compare_name="20260901-154210-baseline.json", color=False)

    assert "compared against 20260901-154210-baseline.json" in output
    assert "0.61 (+0.07)" in output
    assert "0.70 (-0.02)" in output
    assert "0.55 (=)" in output


def test_render_suppresses_deltas_when_parameters_differ() -> None:
    output = render(_payload(), compare=_payload(k=10), compare_name="x.json", color=False)

    assert "different k/threshold" in output
    assert "(+" not in output


def test_render_colors_deltas_like_pytest() -> None:
    current = _payload(recall=0.61, hit=0.70, mrr=0.55)
    previous = _payload(recall=0.54, hit=0.72, mrr=0.55)

    output = render(current, compare=previous, compare_name="b.json", color=True)

    assert "\x1b[32m(+0.07)\x1b[0m" in output
    assert "\x1b[31m(-0.02)\x1b[0m" in output
    assert "\x1b[2m(=)\x1b[0m" in output
