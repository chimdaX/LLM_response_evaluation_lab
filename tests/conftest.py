"""Shared fixtures: a tiny, fully valid dataset built in code so each test can break one thing."""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from ai_response_eval.rubric import DIMENSIONS
from ai_response_eval.scoring import ReviewFlagPolicy, ScoringConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "data" / "examples"
REPO_CONFIG = REPO_ROOT / "config" / "scoring.json"
REPO_RUBRIC = REPO_ROOT / "rubrics" / "rubric_v1.md"

Records = dict[str, list[dict[str, Any]]]


def make_prompt(prompt_id: str = "P1", domain: str = "science", **overrides: Any) -> dict[str, Any]:
    record = {
        "schema_version": "1.0",
        "prompt_id": prompt_id,
        "domain": domain,
        "prompt": "Why is the sky blue?",
        "constraints": [],
        "reference_notes": None,
        "created_at": "2026-01-01",
    }
    return record | overrides


def make_response(
    response_id: str = "R1A", prompt_id: str = "P1", label: str = "A", **overrides: Any
) -> dict[str, Any]:
    record = {
        "schema_version": "1.0",
        "response_id": response_id,
        "prompt_id": prompt_id,
        "candidate_label": label,
        "response_text": "Blue light is scattered more by air molecules.",
        "model_name": "example-only",
        "provenance": "synthetic_example",
        "generated_at": None,
    }
    return record | overrides


def make_evaluation(
    evaluation_id: str = "E1",
    response_id: str = "R1A",
    prompt_id: str = "P1",
    scores: dict[str, int | None] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    scores = {d: 4 for d in DIMENSIONS} if scores is None else scores
    record = {
        "schema_version": "1.0",
        "evaluation_id": evaluation_id,
        "prompt_id": prompt_id,
        "response_id": response_id,
        "reviewer_id": "reviewer_01",
        "annotation_source": "illustrative_example",
        "rubric_version": "1.0",
        "scores": scores,
        "score_rationales": {
            d: f"Checked {d} against the prompt requirements." for d in DIMENSIONS
        },
        "errors": [],
        "overall_rationale": "States the scattering mechanism correctly.",
        "improved_response": None,
        "reviewed_at": "2026-01-02",
    }
    return record | overrides


def make_preference(
    preference_id: str = "PW1",
    prompt_id: str = "P1",
    a: str = "R1A",
    b: str = "R1B",
    winner: str = "A",
    **overrides: Any,
) -> dict[str, Any]:
    record = {
        "schema_version": "1.0",
        "preference_id": preference_id,
        "prompt_id": prompt_id,
        "response_a_id": a,
        "response_b_id": b,
        "reviewer_id": "reviewer_01",
        "annotation_source": "illustrative_example",
        "winner": winner,
        "reason": "A is accurate.",
        "rubric_version": "1.0",
        "reviewed_at": "2026-01-02",
    }
    return record | overrides


def base_records() -> Records:
    """One prompt, two responses, one evaluation each, one preference -- all valid."""
    return {
        "prompts": [make_prompt()],
        "responses": [make_response("R1A", label="A"), make_response("R1B", label="B")],
        "evaluations": [
            make_evaluation("E1", "R1A", scores={d: 5 for d in DIMENSIONS}),
            make_evaluation("E2", "R1B", scores={d: 3 for d in DIMENSIONS}),
        ],
        "preferences": [make_preference()],
    }


def write_records(directory: Path, records: Records) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for collection, items in records.items():
        (directory / f"{collection}.json").write_text(json.dumps(items, indent=2), encoding="utf-8")
    return directory


@pytest.fixture
def records() -> Records:
    return copy.deepcopy(base_records())


@pytest.fixture
def write_dataset(tmp_path: Path) -> Callable[[Records], Path]:
    def _write(recs: Records) -> Path:
        return write_records(tmp_path / "data", recs)

    return _write


@pytest.fixture
def config() -> ScoringConfig:
    return ScoringConfig(
        config_version="test",
        rubric_version="1.0",
        weights={d: 1.0 for d in DIMENSIONS},
        display_decimals=2,
        review_flags=ReviewFlagPolicy(
            critical_dimensions=("accuracy", "safety"),
            critical_score_threshold=2,
            critical_error_labels=("incorrect_fact", "unsafe_guidance", "fabricated_source"),
            flag_needs_verification=True,
        ),
        pairwise_tie_margin=0.25,
    )


# --- Phase 2 (benchmark workflow) helpers ------------------------------------------------

BENCHMARK_DIR = REPO_ROOT / "data" / "benchmark"
TODAY = date(2026, 10, 12)


def make_model_response(
    prompt_id: str = "P1", label: str = "A", **overrides: Any
) -> dict[str, Any]:
    record = {
        "schema_version": "1.1",
        "response_id": f"{prompt_id}-{label}",
        "prompt_id": prompt_id,
        "candidate_label": label,
        "response_text": "Blue light is scattered more strongly by air molecules.",
        "model_name": "vendor-model-x",
        "provider": "Vendor Chat",
        "collection_method": "web_chat",
        "generation_settings": None,
        "provenance": "model_output",
        "generated_at": "2026-10-10",
    }
    return record | overrides


def benchmark_records() -> Records:
    """Two prompts; P1 has both candidates collected, P2 has none. No annotations yet."""
    return {
        "prompts": [make_prompt("P1"), make_prompt("P2", domain="mathematics")],
        "responses": [make_model_response("P1", "A"), make_model_response("P1", "B")],
        "evaluations": [],
        "preferences": [],
    }


@pytest.fixture
def bench_dir(tmp_path: Path) -> Path:
    return write_records(tmp_path / "bench", copy.deepcopy(benchmark_records()))


@pytest.fixture
def fresh_benchmark(tmp_path: Path) -> Path:
    """The committed benchmark prompts with empty response/annotation files.

    Tests must never depend on (or modify) the reviewer's real, evolving annotations in
    data/benchmark, so they work on this copy instead.
    """
    data_dir = tmp_path / "benchmark"
    data_dir.mkdir()
    shutil.copy(BENCHMARK_DIR / "prompts.json", data_dir / "prompts.json")
    for name in ("responses", "evaluations", "preferences"):
        (data_dir / f"{name}.json").write_text("[]\n", encoding="utf-8")
    return data_dir
