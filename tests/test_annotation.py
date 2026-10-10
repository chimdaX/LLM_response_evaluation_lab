"""Interactive annotation: saving, validation of entries, resume, duplicates, blind review."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_response_eval.annotation import (
    AnnotationError,
    annotate_pair,
    annotate_response,
    candidate_pairs,
    evaluation_queue,
    preference_queue,
)
from ai_response_eval.interactive import ScriptedConsole
from ai_response_eval.rubric import DIMENSIONS
from ai_response_eval.storage import DraftStore
from ai_response_eval.validation import validate_data_dir
from tests.conftest import TODAY


def dimension_answers(scores: dict[str, str] | None = None) -> list[str]:
    """Score + rationale answers for all seven dimensions, in rubric order."""
    scores = scores or {}
    answers = []
    for d in DIMENSIONS:
        answers += [scores.get(d, "4"), f"Rationale for {d}."]
    return answers


def full_evaluation(
    scores: dict[str, str] | None = None, errors: list[list[str]] | None = None
) -> list[str]:
    answers = ["", *dimension_answers(scores)]  # "" reveals the response
    for error in errors or []:
        answers += ["y", *error]
    answers += ["n", "Overall rationale.", ".", "s"]
    return answers


def _run(bench_dir: Path, answers: list[str], response_id: str = "P1-A", **kwargs):
    dataset = validate_data_dir(bench_dir).dataset
    console = ScriptedConsole(answers)
    record = annotate_response(
        console,
        bench_dir,
        dataset,
        dataset.responses_by_id[response_id],
        "reviewer_01",
        today=TODAY,
        drafts=DraftStore(bench_dir),
        **kwargs,
    )
    return record, console


def _saved(bench_dir: Path, name: str = "evaluations.json") -> list[dict]:
    return json.loads((bench_dir / name).read_text(encoding="utf-8"))


def test_complete_evaluation_is_saved_as_valid_human_record(bench_dir: Path) -> None:
    record, _ = _run(bench_dir, full_evaluation(scores={"reasoning": "n"}))
    assert record is not None
    [saved] = _saved(bench_dir)
    assert saved == record
    assert saved["evaluation_id"] == "EV0001"
    assert saved["annotation_source"] == "human"
    assert saved["schema_version"] == "1.1"
    assert saved["reviewed_at"] == "2026-10-12"
    assert saved["scores"]["reasoning"] is None
    assert saved["score_rationales"]["reasoning"] == "Rationale for reasoning."
    assert validate_data_dir(bench_dir).ok


def test_invalid_score_entries_are_reprompted(bench_dir: Path) -> None:
    answers = full_evaluation()
    # Replace the accuracy score ("4", index 1) with invalid attempts followed by a valid one.
    answers[1:2] = ["7", "4.5", "abc", "0", "?", "2"]
    record, console = _run(bench_dir, answers)
    assert record["scores"]["accuracy"] == 2
    assert console.text.count("Enter a whole number 1-5") == 4
    assert "Full anchors: rubrics/rubric_v1.md" in console.text


def test_empty_rationale_is_rejected(bench_dir: Path) -> None:
    answers = full_evaluation()
    answers[2:3] = ["", "   ", "Accuracy rationale."]
    record, console = _run(bench_dir, answers)
    assert record["score_rationales"]["accuracy"] == "Accuracy rationale."
    assert console.text.count("A response is required here.") == 2


def test_error_label_and_evidence_validation(bench_dir: Path) -> None:
    error = [
        "incorect_fact",
        "?",
        "incorrect_fact",
        "v",
        "The date is wrong.",
        "",
        "nobelprize.org",
    ]
    record, console = _run(bench_dir, full_evaluation(scores={"accuracy": "2"}, errors=[error]))
    assert "did you mean 'incorrect_fact'" in console.text
    assert "hallucination" in console.text  # taxonomy listing shown for '?'
    assert record["errors"] == [
        {
            "label": "incorrect_fact",
            "evidence_status": "verified",
            "note": "The date is wrong.",
            "source": "nobelprize.org",
        }
    ]


def test_unverified_error_source_is_optional(bench_dir: Path) -> None:
    error = ["unsupported_claim", "n", "Claim about study size not checked.", ""]
    record, _ = _run(bench_dir, full_evaluation(errors=[error]))
    assert record["errors"][0]["source"] is None
    assert record["errors"][0]["evidence_status"] == "needs_verification"


def test_interrupted_evaluation_resumes_from_draft(bench_dir: Path) -> None:
    answers = full_evaluation()
    first_part = answers[:7]  # reveal + accuracy, instruction_following, relevance (score+why)
    with pytest.raises(EOFError):
        _run(bench_dir, first_part)
    drafts = DraftStore(bench_dir)
    assert drafts.keys() == ["evaluation__reviewer_01__P1-A"]
    assert _saved(bench_dir) == []  # nothing saved to the data file yet

    record, console = _run(bench_dir, answers[7:])  # no reveal prompt, starts at completeness
    assert "Resuming saved draft" in console.text
    assert "accuracy score" not in console.text
    assert set(record["scores"]) == set(DIMENSIONS)
    assert drafts.keys() == []


def test_quit_keeps_draft_and_saves_nothing(bench_dir: Path) -> None:
    answers = full_evaluation()
    answers[-1] = "q"
    record, _ = _run(bench_dir, answers)
    assert record is None
    assert _saved(bench_dir) == []
    assert DraftStore(bench_dir).keys() == ["evaluation__reviewer_01__P1-A"]


def test_edit_before_saving(bench_dir: Path) -> None:
    answers = full_evaluation()
    answers[-1:] = ["e", "clarity", "2", "Hard to follow.", "s"]
    record, _ = _run(bench_dir, answers)
    assert record["scores"]["clarity"] == 2
    assert record["score_rationales"]["clarity"] == "Hard to follow."


def test_duplicate_evaluation_refused_unless_repeat(bench_dir: Path) -> None:
    _run(bench_dir, full_evaluation())
    with pytest.raises(AnnotationError, match="already evaluated"):
        _run(bench_dir, full_evaluation())
    record, _ = _run(bench_dir, full_evaluation(), allow_repeat=True)
    assert record["evaluation_id"] == "EV0002"
    result = validate_data_dir(bench_dir)
    assert result.ok
    assert any("evaluated this response 2 times" in w.message for w in result.warnings)


def test_existing_records_are_preserved(bench_dir: Path) -> None:
    _run(bench_dir, full_evaluation())
    first = _saved(bench_dir)[0]
    _run(bench_dir, full_evaluation(), response_id="P1-B")
    saved = _saved(bench_dir)
    assert saved[0] == first
    assert [r["evaluation_id"] for r in saved] == ["EV0001", "EV0002"]


def test_review_is_blind_to_model_identity(bench_dir: Path) -> None:
    _, console = _run(bench_dir, full_evaluation())
    assert "vendor-model-x" not in console.text
    assert "Vendor Chat" not in console.text
    assert "Blue light is scattered" in console.text


def test_consistency_warning_for_low_accuracy_without_error(bench_dir: Path) -> None:
    _, console = _run(bench_dir, full_evaluation(scores={"accuracy": "1"}))
    assert (
        "CHECK: accuracy is 1 but no factual/hallucination/reasoning error is labelled"
        in console.text
    )


def test_evaluation_queue_puts_drafts_first(bench_dir: Path) -> None:
    drafts = DraftStore(bench_dir)
    dataset = validate_data_dir(bench_dir).dataset
    assert [r.response_id for r in evaluation_queue(dataset, "reviewer_01", drafts)] == [
        "P1-A",
        "P1-B",
    ]
    drafts.save("evaluation__reviewer_01__P1-B", {"scores": {}})
    assert [r.response_id for r in evaluation_queue(dataset, "reviewer_01", drafts)] == [
        "P1-B",
        "P1-A",
    ]


# --- pairwise ---------------------------------------------------------------------------


def _run_pair(bench_dir: Path, answers: list[str]):
    dataset = validate_data_dir(bench_dir).dataset
    [pair] = candidate_pairs(dataset)
    console = ScriptedConsole(answers)
    record = annotate_pair(
        console, bench_dir, dataset, pair, "reviewer_01", today=TODAY, drafts=DraftStore(bench_dir)
    )
    return record, console


def test_pairwise_decision_saved(bench_dir: Path) -> None:
    record, console = _run_pair(bench_dir, ["t", "Both are equally accurate.", "s"])
    assert "have not evaluated P1-A, P1-B individually" in console.text
    assert record["winner"] == "tie"
    assert (record["response_a_id"], record["response_b_id"]) == ("P1-A", "P1-B")
    assert record["preference_id"] == "PF0001"
    assert record["annotation_source"] == "human"
    assert validate_data_dir(bench_dir).ok


def test_pairwise_requires_valid_winner_and_reason(bench_dir: Path) -> None:
    record, console = _run_pair(bench_dir, ["c", "a", "", "A is correct.", "s"])
    assert record["winner"] == "A"
    assert "Please enter one of: a, b, t." in console.text
    assert "A response is required here." in console.text


def test_pairwise_duplicate_refused(bench_dir: Path) -> None:
    _run_pair(bench_dir, ["b", "B is correct.", "s"])
    with pytest.raises(AnnotationError, match="already compared"):
        _run_pair(bench_dir, ["a", "x", "s"])


def test_pairwise_interrupted_then_resumed(bench_dir: Path) -> None:
    with pytest.raises(EOFError):
        _run_pair(bench_dir, ["b"])
    record, _ = _run_pair(bench_dir, ["B handles the edge case.", "s"])
    assert record["winner"] == "B"
    assert DraftStore(bench_dir).keys() == []


def test_pairs_need_both_candidates(bench_dir: Path) -> None:
    dataset = validate_data_dir(bench_dir).dataset
    assert [p.prompt.prompt_id for p in candidate_pairs(dataset)] == ["P1"]  # P2 has no responses
    assert len(preference_queue(dataset, "reviewer_01", DraftStore(bench_dir))) == 1
