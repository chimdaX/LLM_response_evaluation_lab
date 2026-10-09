"""Score aggregation, null handling, review flags and configuration."""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from ai_response_eval.rubric import DIMENSIONS
from ai_response_eval.schemas import Evaluation
from ai_response_eval.scoring import (
    ConfigError,
    ReviewFlag,
    ScoringConfig,
    format_score,
    load_scoring_config,
    review_flags,
    score_evaluations,
    weighted_overall,
)
from ai_response_eval.validation import validate_data_dir
from tests.conftest import REPO_CONFIG, Records, make_evaluation, make_prompt, make_response

EQUAL = {d: 1.0 for d in DIMENSIONS}


def test_equal_weights_is_plain_mean() -> None:
    scores = dict(zip(DIMENSIONS, [5, 4, 3, 2, 1, 5, 4], strict=True))
    assert weighted_overall(scores, EQUAL) == pytest.approx(24 / 7)


def test_weighted_mean_matches_hand_calculation() -> None:
    weights = EQUAL | {"accuracy": 3.0, "safety": 2.0}
    scores = {d: 4 for d in DIMENSIONS} | {"accuracy": 1, "safety": 5}
    # (1*3 + 5*2 + 4*5 [five other dims at weight 1]) / (3 + 2 + 5) = 33 / 10
    assert weighted_overall(scores, weights) == pytest.approx(3.3)


def test_null_scores_leave_numerator_and_denominator() -> None:
    scores = {d: None for d in DIMENSIONS} | {"accuracy": 5, "clarity": 2}
    # Treating nulls as zero would give 7/7 = 1.0; the correct answer is 7/2.
    assert weighted_overall(scores, EQUAL) == pytest.approx(3.5)


def test_all_null_returns_none() -> None:
    assert weighted_overall({d: None for d in DIMENSIONS}, EQUAL) is None


def test_empty_scores_return_none() -> None:
    assert weighted_overall({}, EQUAL) is None


def test_result_independent_of_dimension_order() -> None:
    weights = {d: w for d, w in zip(DIMENSIONS, [0.1, 0.2, 0.3, 0.7, 1.1, 1.3, 0.05], strict=True)}
    scores = dict(zip(DIMENSIONS, [3, 5, 1, 4, 2, 5, 3], strict=True))
    results = {
        weighted_overall(dict(order), weights)
        for order in itertools.islice(itertools.permutations(scores.items()), 500)
    }
    assert len(results) == 1  # bit-for-bit identical, not merely approximately equal


@pytest.mark.parametrize("bad", [0, 6, 2.5, True])
def test_invalid_score_raises(bad: object) -> None:
    with pytest.raises(ValueError, match="integer 1-5"):
        weighted_overall({"accuracy": bad}, EQUAL)  # type: ignore[dict-item]


def test_missing_weight_raises() -> None:
    with pytest.raises(ValueError, match="no weight configured"):
        weighted_overall({"accuracy": 3}, {"clarity": 1.0})


def test_format_score_rounds_only_for_display() -> None:
    assert format_score(23 / 7, 2) == "3.29"
    assert format_score(None, 2) == "n/a"


def _evaluation(**overrides: object) -> Evaluation:
    return Evaluation.model_validate(make_evaluation(**overrides))


def test_critical_failure_flag_survives_high_average(config: ScoringConfig) -> None:
    scores = {d: 5 for d in DIMENSIONS} | {"accuracy": 1}
    evaluation = _evaluation(
        scores=scores,
        errors=[
            {"label": "incorrect_fact", "evidence_status": "verified", "note": "n", "source": "s"}
        ],
    )
    assert weighted_overall(evaluation.scores, config.weights) > 4.4
    flags = review_flags(evaluation, config.review_flags)
    assert ReviewFlag("low_critical_score", "accuracy=1") in flags
    assert ReviewFlag("critical_error", "incorrect_fact") in flags


def test_threshold_is_inclusive_and_only_for_critical_dimensions(config: ScoringConfig) -> None:
    scores = {d: 5 for d in DIMENSIONS} | {"safety": 2, "clarity": 1}
    flags = review_flags(_evaluation(scores=scores), config.review_flags)
    assert flags == (ReviewFlag("low_critical_score", "safety=2"),)


def test_needs_verification_flag_and_toggle(config: ScoringConfig) -> None:
    evaluation = _evaluation(
        errors=[
            {"label": "unsupported_claim", "evidence_status": "needs_verification", "note": "n"}
        ]
    )
    assert review_flags(evaluation, config.review_flags) == (
        ReviewFlag("needs_verification", "unsupported_claim"),
    )
    policy = config.review_flags.model_copy(update={"flag_needs_verification": False})
    assert review_flags(evaluation, policy) == ()


def test_all_null_evaluation_is_flagged(config: ScoringConfig) -> None:
    evaluation = _evaluation(scores={d: None for d in DIMENSIONS})
    assert ReviewFlag("no_scored_dimensions", "all dimensions null") in review_flags(
        evaluation, config.review_flags
    )


def test_score_evaluations_sorted_and_joined(
    records: Records, write_dataset: Callable[[Records], Path], config: ScoringConfig
) -> None:
    records["prompts"].append(make_prompt("P2", domain="mathematics"))
    records["responses"].append(make_response("R2A", prompt_id="P2"))
    records["evaluations"].insert(
        0,
        make_evaluation(
            "E0", "R2A", prompt_id="P2", scores={d: None for d in DIMENSIONS} | {"accuracy": 2}
        ),
    )
    dataset = validate_data_dir(write_dataset(records)).dataset
    scored = score_evaluations(dataset, config)
    assert [s.evaluation.evaluation_id for s in scored] == ["E0", "E1", "E2"]
    assert scored[0].domain == "mathematics"
    assert scored[0].n_scored == 1
    assert scored[0].overall == 2.0
    assert scored[0].needs_review


def test_repo_config_loads() -> None:
    config = load_scoring_config(REPO_CONFIG)
    assert set(config.weights) == set(DIMENSIONS)


def _write_config(tmp_path: Path, **changes: object) -> Path:
    raw = json.loads(REPO_CONFIG.read_text(encoding="utf-8")) | changes
    path = tmp_path / "scoring.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"weights": EQUAL | {"accuracy": 0}}, "greater than 0"),
        ({"weights": EQUAL | {"humor": 1.0}}, "unknown: \\['humor'\\]"),
        ({"rubric_version": "2.0"}, "rubric_version"),
        ({"pairwise_tie_margin": -1}, "pairwise_tie_margin"),
    ],
)
def test_invalid_config_rejected(tmp_path: Path, changes: dict, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_scoring_config(_write_config(tmp_path, **changes))


def test_config_with_unknown_critical_label_rejected(tmp_path: Path) -> None:
    raw = json.loads(REPO_CONFIG.read_text(encoding="utf-8"))
    raw["review_flags"]["critical_error_labels"] = ["made_up_label"]
    path = tmp_path / "scoring.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ConfigError, match="made_up_label"):
        load_scoring_config(path)


def test_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_scoring_config(tmp_path / "missing.json")
