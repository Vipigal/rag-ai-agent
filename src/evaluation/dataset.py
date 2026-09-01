from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import yaml

PERSONAS = frozenset({"operator", "technical"})
LANGUAGES = frozenset({"pt", "en"})
CATEGORIES = frozenset(
    {
        "spec_lookup",
        "table_lookup",
        "figure",
        "image_content",
        "procedure",
        "safety",
        "conceptual",
        "unanswerable",
    }
)


@dataclass(frozen=True)
class ExcerptVariant:
    document: str
    page: int
    text: str


@dataclass(frozen=True)
class GoldExcerpt:
    document: str
    page: int
    text: str
    alternates: tuple[ExcerptVariant, ...] = ()


@dataclass(frozen=True)
class GoldenCase:
    id: str
    question: str
    persona: str
    language: str
    category: str
    gold_excerpts: tuple[GoldExcerpt, ...]
    reference_answer: str
    expected_facts: tuple[str, ...] = ()
    requires_image: bool = False
    notes: str | None = None


def load_golden_cases(directory: Path) -> tuple[GoldenCase, ...]:
    cases: list[GoldenCase] = []
    seen_ids: set[str] = set()
    for path in sorted(directory.glob("*.yaml")):
        for raw in yaml.safe_load(path.read_text(encoding="utf-8")):
            case = _parse_case(raw)
            if case.id in seen_ids:
                _fail(case.id, "duplicate id")
            seen_ids.add(case.id)
            _validate(case)
            cases.append(case)
    return tuple(cases)


def _validate(case: GoldenCase) -> None:
    if case.persona not in PERSONAS:
        _fail(case.id, f"unknown persona '{case.persona}'")
    if case.language not in LANGUAGES:
        _fail(case.id, f"unknown language '{case.language}'")
    if case.category not in CATEGORIES:
        _fail(case.id, f"unknown category '{case.category}'")
    if (case.category == "unanswerable") != (not case.gold_excerpts):
        _fail(case.id, "gold_excerpts must be empty exactly when category is 'unanswerable'")
    for excerpt in case.gold_excerpts:
        for variant in (excerpt, *excerpt.alternates):
            if not variant.document:
                _fail(case.id, "excerpt with empty document")
            if variant.page < 1:
                _fail(case.id, f"excerpt page {variant.page} is not a 1-based page index")
            if not variant.text.strip():
                _fail(case.id, "excerpt with empty text")


def _fail(case_id: str, problem: str) -> NoReturn:
    raise ValueError(f"golden case '{case_id}': {problem}")


def _parse_case(raw: dict) -> GoldenCase:
    return GoldenCase(
        id=raw["id"],
        question=raw["question"],
        persona=raw["persona"],
        language=raw["language"],
        category=raw["category"],
        gold_excerpts=tuple(_parse_excerpt(e) for e in raw["gold_excerpts"]),
        reference_answer=raw["reference_answer"],
        expected_facts=tuple(raw.get("expected_facts") or ()),
        requires_image=raw.get("requires_image", False),
        notes=raw.get("notes"),
    )


def _parse_excerpt(raw: dict) -> GoldExcerpt:
    return GoldExcerpt(
        document=raw["document"],
        page=raw["page"],
        text=raw["text"],
        alternates=tuple(
            ExcerptVariant(document=a["document"], page=a["page"], text=a["text"])
            for a in raw.get("alternates") or ()
        ),
    )
