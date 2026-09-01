from pathlib import Path

import pytest
import yaml

from evaluation.dataset import ExcerptVariant, GoldenCase, GoldExcerpt, load_golden_cases

TWO_CASES_YAML = """\
- id: doc-001
  question: "qual o torque de aperto?"
  persona: operator
  language: pt
  category: table_lookup
  gold_excerpts:
    - document: manual.pdf
      page: 12
      text: "torque de aperto: 25 Nm"
      alternates:
        - document: manual.pdf
          page: 40
          text: "tightening torque: 25 Nm"
  reference_answer: "O torque de aperto é 25 Nm."
  expected_facts: ["25 Nm"]
  requires_image: false
  notes: "table row lookup"

- id: doc-002
  question: "qual a garantia do produto X?"
  persona: operator
  language: pt
  category: unanswerable
  gold_excerpts: []
  reference_answer: "Não há informação sobre isso nos documentos."
"""


VALID_CASE = {
    "id": "doc-001",
    "question": "qual o torque de aperto?",
    "persona": "operator",
    "language": "pt",
    "category": "table_lookup",
    "gold_excerpts": [
        {"document": "manual.pdf", "page": 12, "text": "torque de aperto: 25 Nm"}
    ],
    "reference_answer": "O torque de aperto é 25 Nm.",
}


def test_load_golden_cases_parses_cases_with_defaults_and_alternates(tmp_path: Path) -> None:
    (tmp_path / "doc.yaml").write_text(TWO_CASES_YAML, encoding="utf-8")

    cases = load_golden_cases(tmp_path)

    assert cases == (
        GoldenCase(
            id="doc-001",
            question="qual o torque de aperto?",
            persona="operator",
            language="pt",
            category="table_lookup",
            gold_excerpts=(
                GoldExcerpt(
                    document="manual.pdf",
                    page=12,
                    text="torque de aperto: 25 Nm",
                    alternates=(
                        ExcerptVariant(
                            document="manual.pdf",
                            page=40,
                            text="tightening torque: 25 Nm",
                        ),
                    ),
                ),
            ),
            reference_answer="O torque de aperto é 25 Nm.",
            expected_facts=("25 Nm",),
            requires_image=False,
            notes="table row lookup",
        ),
        GoldenCase(
            id="doc-002",
            question="qual a garantia do produto X?",
            persona="operator",
            language="pt",
            category="unanswerable",
            gold_excerpts=(),
            reference_answer="Não há informação sobre isso nos documentos.",
        ),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"persona": "expert"},
        {"language": "es"},
        {"category": "trivia"},
        {"gold_excerpts": []},
        {"category": "unanswerable"},
        {"gold_excerpts": [{"document": "manual.pdf", "page": 0, "text": "x"}]},
        {"gold_excerpts": [{"document": "manual.pdf", "page": 1, "text": "   "}]},
        {"gold_excerpts": [{"document": "", "page": 1, "text": "x"}]},
        {
            "gold_excerpts": [
                {
                    "document": "manual.pdf",
                    "page": 1,
                    "text": "x",
                    "alternates": [{"document": "manual.pdf", "page": 0, "text": "y"}],
                }
            ]
        },
    ],
)
def test_load_golden_cases_rejects_invalid_case_naming_it(
    tmp_path: Path, mutation: dict
) -> None:
    (tmp_path / "doc.yaml").write_text(
        yaml.safe_dump([VALID_CASE | mutation]), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="doc-001"):
        load_golden_cases(tmp_path)


def test_load_golden_cases_rejects_duplicate_ids_across_files(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(yaml.safe_dump([VALID_CASE]), encoding="utf-8")
    (tmp_path / "b.yaml").write_text(yaml.safe_dump([VALID_CASE]), encoding="utf-8")

    with pytest.raises(ValueError, match="doc-001"):
        load_golden_cases(tmp_path)


def test_real_golden_dataset_matches_shipped_shape() -> None:
    cases = load_golden_cases(Path(__file__).parents[2] / "evals" / "golden")

    assert len(cases) == 93
    assert sum(case.category == "unanswerable" for case in cases) == 8
    assert sum(case.requires_image for case in cases) == 2
