"""Content-based rationale checks: catch non-explanations, not short specific text."""

from __future__ import annotations

import pytest

from ai_response_eval.cli import EXIT_INVALID_DATA, EXIT_OK, main
from ai_response_eval.rationale_quality import check_rationale, repeated_rationales
from ai_response_eval.rubric import DIMENSIONS
from ai_response_eval.validation import validate_data_dir
from tests.conftest import EXAMPLES_DIR, Records, make_evaluation


def _codes(text: str) -> list[str]:
    return [issue.code for issue in check_rationale(text)]


@pytest.mark.parametrize(
    "text", ["4", " 5 ", "4/5", "4 / 5", "5.0", "score: 4", "Rated 3.", "4 out of 5"]
)
def test_score_like_text_is_blocking(text: str) -> None:
    [issue] = check_rationale(text)
    assert (issue.code, issue.severity) == ("numeric_only", "blocking")


@pytest.mark.parametrize(
    "text", ["n/a", "N/A", "ok", "Fine.", "same as above", "TBD", "-", "nothing"]
)
def test_placeholders_are_blocking(text: str) -> None:
    [issue] = check_rationale(text)
    assert (issue.code, issue.severity) == ("placeholder", "blocking")


@pytest.mark.parametrize(
    "text",
    [
        "The model output is okay",
        "Good answer.",
        "Correct.",
        "Accurate and clear.",
        "Missing stuff.",
        # Long but empty: length alone must not make a rationale acceptable.
        "Overall the response is really pretty good and quite clear and accurate, I think",
    ],
)
def test_generic_text_is_a_warning(text: str) -> None:
    [issue] = check_rationale(text)
    assert (issue.code, issue.severity) == ("no_specific_content", "warning")


@pytest.mark.parametrize(
    "text",
    [
        "Omits 2100.",  # very short, but names a specific omission
        "Two sentences, as asked.",
        "Not assessed: no inference requested.",
        "Recalculated: 80 x 0.75 = 60.",
        "Matches nobelprize.org dates.",
        "No safety concerns in this context.",
    ],
)
def test_short_specific_text_passes(text: str) -> None:
    assert check_rationale(text) == []


def test_repeated_rationales_need_three_dimensions() -> None:
    two = {"accuracy": "Same text.", "clarity": "Same text.", "safety": "Different."}
    assert repeated_rationales(two) == []
    three = two | {"safety": "same TEXT."}
    assert repeated_rationales(three) == [("same text.", ["accuracy", "clarity", "safety"])]


def _flawed(evaluation_id: str = "E1", response_id: str = "R1A", **overrides) -> dict:
    """Mirrors a real problem: scores typed into the rationale fields."""
    return make_evaluation(
        evaluation_id,
        response_id,
        score_rationales={d: "4" for d in DIMENSIONS},
        overall_rationale="The model output is okay",
        **overrides,
    )


def test_validate_warns_but_keeps_flawed_record_valid(records: Records, write_dataset) -> None:
    records["evaluations"][0] = _flawed()
    result = validate_data_dir(write_dataset(records))
    assert result.ok  # historical records are never invalidated retroactively
    messages = [w.message for w in result.warnings if w.location == "E1"]
    assert sum("numeric_only" in m for m in messages) == len(DIMENSIONS)
    assert any(m.startswith("overall_rationale: no_specific_content") for m in messages)
    assert any("repeated_rationale" in m for m in messages)


def test_strict_validation_fails_on_rationale_warnings(records: Records, write_dataset) -> None:
    records["evaluations"][0] = _flawed()
    data_dir = str(write_dataset(records))
    assert main(["validate", "--data-dir", data_dir]) == EXIT_OK
    assert main(["validate", "--data-dir", data_dir, "--strict"]) == EXIT_INVALID_DATA


def test_superseded_records_are_not_warned_about(records: Records, write_dataset) -> None:
    records["evaluations"][0] = _flawed()
    records["evaluations"].append(
        make_evaluation(
            "E1v2",
            "R1A",
            schema_version="1.2",
            supersedes="E1",
            revision_reason="Replaced score digits with explanations.",
        )
    )
    result = validate_data_dir(write_dataset(records))
    assert result.ok
    assert [w for w in result.warnings if w.location == "E1"] == []


def test_examples_have_no_rationale_warnings() -> None:
    assert validate_data_dir(EXAMPLES_DIR).warnings == []
