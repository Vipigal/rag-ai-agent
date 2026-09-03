from domain.models import Answer, Chunk, Reference, RetrievedChunk, Usage
from evaluation.answers import AnswerRun, AnswerSettings
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
        "answers": None,
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


SETTINGS = AnswerSettings(
    llm_model="openai:gpt-5-mini", tool_enabled=True, max_tool_rounds=3, workers=4, thinking="low"
)
FULL_HIT = CaseResult(
    case_id="x",
    recall=1.0,
    hit=True,
    reciprocal_rank=1.0,
    precision=1.0,
    matched_excerpts=(0,),
    first_relevant_rank=1,
    chunk_matches=((0,),),
)


def _facts_case(case_id: str, facts: tuple[str, ...], category: str = "spec_lookup") -> GoldenCase:
    return GoldenCase(
        id=case_id,
        question="qual o grau de proteção?",
        persona="operator",
        language="pt",
        category=category,
        gold_excerpts=() if category == "unanswerable" else _case(case_id).gold_excerpts,
        reference_answer="IP55.",
        expected_facts=facts,
    )


def test_build_payload_with_answers_adds_the_answers_block_and_per_case_answer() -> None:
    cited = Reference(chunk=_retrieved(0.9).chunk, quote="grau de proteção IP55", retrieval_source="tool")
    case_runs = [
        CaseRun(
            case=_facts_case("doc-001", ("IP55",)),
            result=FULL_HIT,
            retrieved=(_retrieved(0.9),),
            latency_ms=38.2,
            answer=AnswerRun(
                answer=Answer(
                    text="O grau é IP55.",
                    references=[cited],
                    usage=Usage(
                        requests=2,
                        tool_calls=1,
                        input_tokens=6412,
                        cache_read_tokens=2304,
                        output_tokens=812,
                        reasoning_tokens=640,
                        cost_usd=0.0030,
                    ),
                    unmatched_citations=["uma passagem que o modelo inventou"],
                ),
                latency_ms=6821.44,
            ),
        ),
        CaseRun(
            case=_facts_case("neg-001", (), category="unanswerable"),
            result=None,
            retrieved=(),
            latency_ms=None,
            answer=AnswerRun(
                answer=Answer(
                    text="Não há.", references=[], has_answer=False,
                    usage=Usage(requests=1, input_tokens=2000, output_tokens=50, cost_usd=0.0004),
                ),
                latency_ms=3000.0,
            ),
        ),
        CaseRun(
            case=_facts_case("doc-003", ("IP66",)),
            result=FULL_HIT,
            retrieved=(_retrieved(0.9),),
            latency_ms=41.8,
            answer=AnswerRun(answer=None, latency_ms=120.0, error="RuntimeError('cap')"),
        ),
    ]

    payload = build_payload(RUN_INFO, case_runs, unanswerable_excluded=1, answers=SETTINGS)

    assert payload["run"]["cases"] == {
        "total": 3, "gated": 2, "image_diagnostic": 0, "unanswerable_excluded": 1, "answered": 3
    }
    assert payload["gates"]["recall_at_k"] == 1.0
    assert payload["efficiency"]["retrieval_latency_ms"] == {"mean": 40.0, "p95": 41.8}
    block = {
        "cases": 2, "fact_recall": 0.5, "citation_precision": 0.5, "citation_recall": 0.5,
        "false_refusal_rate": 0.0,
    }
    assert payload["answers"] == {
        "llm_model": "openai:gpt-5-mini",
        "tool_enabled": True,
        "max_tool_rounds": 3,
        "workers": 4,
        "thinking": "low",
        "gates": {
            "fact_recall": 0.5, "fact_cases": 2,
            "citation_precision": 0.5, "citation_recall": 0.5,
            "refusal_rate": 1.0, "unanswerable_cases": 1,
        },
        "diagnostics": {
            "false_refusal_rate": 0.0, "errors": 1, "unmatched_citations": 1, "requires_image": None
        },
        "efficiency": {
            "latency_ms": {"mean": 3313.8, "p95": 6821.4},
            "usage": {
                "requests": 3, "tool_calls": 1, "input_tokens": 8412,
                "cache_read_tokens": 2304, "output_tokens": 862,
                "reasoning_tokens": 640, "cost_usd": 0.0034,
            },
            "per_question": {
                "requests": 1.5, "input_tokens": 4206.0, "output_tokens": 431.0,
                "reasoning_tokens": 320.0, "cost_usd": 0.0017,
            },
        },
        "slices": {
            "persona": {"operator": block},
            "language": {"pt": block},
            "category": {"spec_lookup": block},
            "document": {"manual.pdf": block},
        },
    }
    answered, refused, errored = payload["cases"]
    assert answered["answer"] == {
        "text": "O grau é IP55.",
        "has_answer": True,
        "reference_answer": "IP55.",
        "facts": [{"fact": "IP55", "found": True}],
        "fact_recall": 1.0,
        "cited": [{"document": "manual.pdf", "page": 34, "in_gold": True, "source": "tool"}],
        "quotes": ["grau de proteção IP55"],
        "unmatched_citations": ["uma passagem que o modelo inventou"],
        "citation_precision": 1.0,
        "citation_recall": 1.0,
        "latency_ms": 6821.4,
        "usage": {
            "requests": 2, "tool_calls": 1, "input_tokens": 6412,
            "cache_read_tokens": 2304, "output_tokens": 812,
            "reasoning_tokens": 640, "cost_usd": 0.003,
        },
        "error": None,
    }
    assert refused["id"] == "neg-001"
    assert {key: refused[key] for key in ("recall", "hit", "reciprocal_rank", "precision", "first_relevant_rank", "latency_ms", "retrieved")} == {
        "recall": None, "hit": None, "reciprocal_rank": None, "precision": None,
        "first_relevant_rank": None, "latency_ms": None, "retrieved": None,
    }
    assert refused["gold_excerpts"] == []
    assert refused["answer"]["has_answer"] is False
    assert refused["answer"]["facts"] == []
    assert (refused["answer"]["fact_recall"], refused["answer"]["citation_precision"], refused["answer"]["citation_recall"]) == (None, None, None)
    assert errored["answer"] == {
        "text": None,
        "has_answer": False,
        "reference_answer": "IP55.",
        "facts": [{"fact": "IP66", "found": False}],
        "fact_recall": 0.0,
        "cited": [],
        "quotes": [],
        "unmatched_citations": None,
        "citation_precision": 0.0,
        "citation_recall": 0.0,
        "latency_ms": 120.0,
        "usage": None,
        "error": "RuntimeError('cap')",
    }


def _answers_block(
    fact_recall: float = 0.72, errors: int = 0, latency_mean: float = 6800.0, cost: float = 0.2134
) -> dict:
    slice_block = {
        "cases": 8, "fact_recall": 0.75, "citation_precision": 0.7, "citation_recall": 0.88,
        "false_refusal_rate": 0.0,
    }
    return {
        "llm_model": "openai:gpt-5-mini",
        "tool_enabled": True,
        "max_tool_rounds": 3,
        "workers": 4,
        "thinking": "low",
        "gates": {
            "fact_recall": fact_recall, "fact_cases": 57,
            "citation_precision": 0.61, "citation_recall": 0.79,
            "refusal_rate": 0.875, "unanswerable_cases": 8,
        },
        "diagnostics": {
            "false_refusal_rate": 0.06, "errors": errors, "unmatched_citations": 3,
            "requires_image": {"fact_recall": 0.0, "citation_precision": 0.5, "citation_recall": 0.5},
        },
        "efficiency": {
            "latency_ms": {"mean": latency_mean, "p95": 14200.0},
            "usage": {
                "requests": 158, "tool_calls": 65, "input_tokens": 498000,
                "cache_read_tokens": 121000, "output_tokens": 112000,
                "reasoning_tokens": 98000, "cost_usd": cost,
            },
            "per_question": {
                "requests": 1.7, "input_tokens": 5400.0, "output_tokens": 1200.0,
                "reasoning_tokens": 1054.0, "cost_usd": 0.0023,
            },
        },
        "slices": {"persona": {}, "language": {}, "category": {}, "document": {"LB5001.pdf": slice_block}},
    }


def test_render_with_answers_appends_the_answer_sections() -> None:
    payload = _payload()
    payload["answers"] = _answers_block()
    payload["run"]["cases"]["answered"] = 93

    output = render(payload, compare=None, compare_name=None, color=False)

    assert "93 answered" in output
    assert "ANSWER GATES (83 cases)" in output
    assert "fact_recall(57)" in output and "refusal_rate(8)" in output
    assert "0.72" in output and "0.88" in output
    assert "ANSWERS BY DOCUMENT" in output
    assert "ANSWER DIAG   false_refusal 0.06 · errors 0 · unmatched quotes 3 · requires_image (2): fact_recall 0.00" in output
    assert "answer latency: mean 6.8 s · p95 14.2 s (4 workers) · llm calls 158 · tool calls 65" in output
    assert "tokens: in 498.0k (cached 121.0k) · out 112.0k (reasoning 98.0k) · per question in 5.4k / out 1.2k" in output
    assert "cost: $0.21 · per question $0.0023" in output


def test_render_without_answers_prints_no_answer_sections() -> None:
    output = render(_payload(), compare=None, compare_name=None, color=False)

    assert "ANSWER" not in output


def test_render_answer_deltas_only_against_a_previous_run_with_answers() -> None:
    current, previous = _payload(), _payload()
    current["answers"] = _answers_block(fact_recall=0.72)
    previous["answers"] = _answers_block(fact_recall=0.67, latency_mean=16000.0, cost=0.30)
    retrieval_only = _payload()
    retrieval_only["answers"] = None

    with_deltas = render(current, compare=previous, compare_name="a.json", color=False)
    without = render(current, compare=retrieval_only, compare_name="b.json", color=False)

    assert "0.72 (+0.05)" in with_deltas
    assert "0.88 (=)" in with_deltas
    assert "answer latency: mean 6.8 s (-9.2 s) · p95 14.2 s (=)" in with_deltas
    assert "cost: $0.21 (-$0.09) · per question $0.0023" in with_deltas
    assert "previous run has no answer layer — answer deltas omitted" in without
    assert "0.72 (+" not in without
    assert "mean 6.8 s · p95 14.2 s" in without


def test_render_paints_lower_latency_and_cost_green() -> None:
    current, previous = _payload(), _payload()
    current["answers"] = _answers_block()
    previous["answers"] = _answers_block(latency_mean=16000.0, cost=0.30)

    output = render(current, compare=previous, compare_name="a.json", color=True)

    assert "\x1b[32m(-9.2 s)\x1b[0m" in output
    assert "\x1b[32m(-$0.09)\x1b[0m" in output


def test_render_paints_errors_red_only_when_present() -> None:
    clean, failing = _payload(), _payload()
    clean["answers"] = _answers_block(errors=0)
    failing["answers"] = _answers_block(errors=2)

    assert "\x1b[31merrors 2\x1b[0m" in render(failing, compare=None, compare_name=None, color=True)
    assert "\x1b[31merrors 0" not in render(clean, compare=None, compare_name=None, color=True)
