"""Pairwise preferences and the system-generated score suggestion."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from ai_response_eval.comparisons import (
    build_pairwise_rows,
    score_based_suggestion,
    summarize_pairwise,
)
from ai_response_eval.rubric import DIMENSIONS
from ai_response_eval.scoring import ScoringConfig, score_evaluations
from ai_response_eval.validation import validate_data_dir
from tests.conftest import Records, make_evaluation, make_preference


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (4.0, 3.0, "A"),
        (3.0, 4.0, "B"),
        (4.0, 3.8, "tie"),  # within the 0.25 margin
        (4.0, 3.75, "tie"),  # exactly on the margin counts as a tie
        (None, 3.0, None),
        (4.0, None, None),
    ],
)
def test_score_based_suggestion(a: float | None, b: float | None, expected: str | None) -> None:
    assert score_based_suggestion(a, b, tie_margin=0.25) == expected


def _rows(records: Records, write_dataset: Callable[[Records], Path], config: ScoringConfig):
    dataset = validate_data_dir(write_dataset(records)).dataset
    return build_pairwise_rows(dataset, score_evaluations(dataset, config), config)


def test_human_winner_kept_when_scores_disagree(
    records: Records, write_dataset: Callable[[Records], Path], config: ScoringConfig
) -> None:
    # Scores favour A (5 vs 3) but the reviewer preferred B: the human decision is the record.
    records["preferences"] = [make_preference(winner="B", reason="B is safer in context.")]
    [row] = _rows(records, write_dataset, config)
    assert row.human_winner == "B"
    assert row.winner_response_id == "R1B"
    assert row.score_suggestion == "A"
    assert row.agreement == "disagree"


def test_tie_is_a_first_class_outcome(
    records: Records, write_dataset: Callable[[Records], Path], config: ScoringConfig
) -> None:
    records["evaluations"][1]["scores"] = {d: 5 for d in DIMENSIONS}
    records["preferences"] = [make_preference(winner="tie", reason="Equivalent.")]
    [row] = _rows(records, write_dataset, config)
    assert row.winner_response_id is None
    assert row.score_suggestion == "tie"
    assert row.agreement == "agree"


def test_missing_scores_give_no_suggestion(
    records: Records, write_dataset: Callable[[Records], Path], config: ScoringConfig
) -> None:
    records["evaluations"] = [records["evaluations"][0]]  # R1B has no evaluation
    [row] = _rows(records, write_dataset, config)
    assert row.b_overall is None
    assert row.score_suggestion is None
    assert row.agreement == "n/a"


def test_mean_over_multiple_evaluations(
    records: Records, write_dataset: Callable[[Records], Path], config: ScoringConfig
) -> None:
    records["evaluations"].append(
        make_evaluation("E3", "R1A", reviewer_id="reviewer_02", scores={d: 1 for d in DIMENSIONS})
    )
    [row] = _rows(records, write_dataset, config)
    assert row.a_overall == pytest.approx(3.0)  # mean of 5.0 and 1.0
    assert row.score_suggestion == "tie"


def test_rows_sorted_and_summary_counts(
    records: Records, write_dataset: Callable[[Records], Path], config: ScoringConfig
) -> None:
    records["preferences"] = [
        make_preference("PW3", winner="tie", reviewer_id="r3"),
        make_preference("PW1", winner="A"),
        make_preference("PW2", winner="B", reviewer_id="r2"),
    ]
    rows = _rows(records, write_dataset, config)
    assert [r.preference.preference_id for r in rows] == ["PW1", "PW2", "PW3"]
    summary = summarize_pairwise(rows)
    assert (summary.decisions, summary.a_wins, summary.b_wins, summary.ties) == (3, 1, 1, 1)
    assert summary.with_suggestion == 3
    assert summary.agreements == 1  # suggestion is "A" for all three


def test_empty_summary() -> None:
    summary = summarize_pairwise([])
    assert (summary.decisions, summary.with_suggestion, summary.agreements) == (0, 0, 0)
