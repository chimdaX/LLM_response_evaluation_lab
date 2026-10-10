"""Evaluation corrections: schema 1.2 fields, revision chains, the --revise flow, and reporting."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_response_eval.annotation import AnnotationError, revise_evaluation
from ai_response_eval.cli import EXIT_OK, EXIT_USAGE, main
from ai_response_eval.comparisons import build_pairwise_rows
from ai_response_eval.interactive import ScriptedConsole
from ai_response_eval.progress import compute_progress
from ai_response_eval.reporting import ReportInputs, build_reports
from ai_response_eval.rubric import DIMENSIONS
from ai_response_eval.schemas import Evaluation
from ai_response_eval.scoring import ScoringConfig, score_evaluations
from ai_response_eval.storage import DraftStore
from ai_response_eval.validation import validate_data_dir
from tests.conftest import REPO_CONFIG, REPO_RUBRIC, TODAY, Records, make_evaluation

TODAY_DT = datetime(2026, 10, 12, tzinfo=UTC)


def revision(evaluation_id: str, supersedes: str, **overrides) -> dict:
    return make_evaluation(
        evaluation_id,
        "R1A",
        schema_version="1.2",
        supersedes=supersedes,
        revision_reason=f"Corrected {supersedes}: rationales now cite evidence.",
        **overrides,
    )


# --- schema --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"supersedes": "E0"}, "must be given together"),
        ({"revision_reason": "Because."}, "must be given together"),
        ({"supersedes": "E0", "revision_reason": "x y", "schema_version": "1.1"}, "'1.2' or later"),
        ({"consistency_check_of": "E0", "schema_version": "1.0"}, "'1.2' or later"),
        (
            {"supersedes": "E9", "revision_reason": "Fix.", "consistency_check_of": "E0"},
            "both a correction",
        ),
        ({"supersedes": "E1", "revision_reason": "Fix."}, "cannot reference itself"),
    ],
)
def test_revision_field_rules(overrides: dict, message: str) -> None:
    record = make_evaluation("E1", schema_version="1.2") | overrides
    with pytest.raises(ValidationError, match=message):
        Evaluation.model_validate(record)


def test_older_versions_still_valid() -> None:
    for version in ("1.0", "1.1"):
        assert Evaluation.model_validate(make_evaluation(schema_version=version)).supersedes is None


# --- chain validation ----------------------------------------------------------------------


def _validate(records: Records, write_dataset):
    return validate_data_dir(write_dataset(records))


def _errors(result) -> list[str]:
    return [str(i) for i in result.errors]


def test_sequential_chain_is_valid(records: Records, write_dataset) -> None:
    records["evaluations"] += [revision("E1b", "E1"), revision("E1c", "E1b")]
    result = _validate(records, write_dataset)
    assert result.ok, _errors(result)
    d = result.dataset
    assert [e.evaluation_id for e in d.active_evaluations] == ["E2", "E1c"]
    assert d.revision_chain("E1c") == ["E1", "E1b", "E1c"]
    assert d.superseded_ids == {"E1", "E1b"}


def test_branching_is_rejected(records: Records, write_dataset) -> None:
    records["evaluations"] += [revision("E1b", "E1"), revision("E1c", "E1")]
    result = _validate(records, write_dataset)
    assert any("superseded by more than one record (E1b, E1c)" in e for e in _errors(result))


def test_cycle_is_rejected(records: Records, write_dataset) -> None:
    records["evaluations"][0] = revision("E1", "E1b")
    records["evaluations"].append(revision("E1b", "E1"))
    result = _validate(records, write_dataset)
    assert any("cycle" in e for e in _errors(result))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"supersedes": "E404"}, "unknown evaluation 'E404'"),
        ({"reviewer_id": "reviewer_02"}, "must be the same response and reviewer"),
        ({"reviewed_at": "2026-01-01"}, "earlier than the superseded record"),
    ],
)
def test_invalid_corrections(
    records: Records, write_dataset, overrides: dict, message: str
) -> None:
    records["evaluations"].append(revision("E1b", "E1") | overrides)
    assert any(message in e for e in _errors(_validate(records, write_dataset)))


def test_correction_must_target_same_response(records: Records, write_dataset) -> None:
    records["evaluations"].append(revision("E2b", "E1") | {"response_id": "R1B"})
    assert any(
        "must be the same response and reviewer" in e
        for e in _errors(_validate(records, write_dataset))
    )


def test_consistency_rereview_cannot_be_superseded(records: Records, write_dataset) -> None:
    records["evaluations"] += [
        make_evaluation("E3", "R1A", schema_version="1.2", consistency_check_of="E1"),
        revision("E3b", "E3"),
    ]
    assert any(
        "is a consistency re-review" in e for e in _errors(_validate(records, write_dataset))
    )


# --- scoring, comparison, progress and reports count each review once --------------------------


def test_only_latest_version_is_scored_and_reported(
    records: Records, write_dataset, config: ScoringConfig
) -> None:
    records["evaluations"] += [
        revision("E1b", "E1", scores={d: 2 for d in DIMENSIONS}),
        make_evaluation(
            "E1x",
            "R1A",
            schema_version="1.2",
            consistency_check_of="E1b",
            scores={d: 1 for d in DIMENSIONS},
        ),
    ]
    result = _validate(records, write_dataset)
    assert result.ok, _errors(result)
    d = result.dataset
    scored = score_evaluations(d, config)
    assert {s.evaluation.evaluation_id: s.overall for s in scored} == {"E1b": 2.0, "E2": 3.0}

    [row] = build_pairwise_rows(d, scored, config)
    assert row.a_overall == 2.0  # the corrected scores, not a mix with the original

    inputs = ReportInputs(
        d, scored, [row], config, result.files, REPO_CONFIG, REPO_RUBRIC, TODAY_DT
    )
    reports = build_reports(inputs)
    meta = json.loads(reports["evaluation_results.json"])["metadata"]
    assert meta["counts"]["evaluation_records"] == 2
    assert meta["revision_history"]["superseded_evaluations"] == 1
    assert meta["revision_history"]["consistency_rereviews"] == 1
    assert (
        "Revision history:** 1 superseded evaluation(s) and 1 consistency re-review(s)"
        in (reports["summary.md"])
    )
    csv_lines = reports["evaluation_results.csv"].splitlines()
    assert csv_lines[0].endswith(",supersedes")
    assert len(csv_lines) == 3 and csv_lines[1].startswith("E1b,") and csv_lines[1].endswith(",E1")


def test_progress_counts_history_separately(records: Records, write_dataset) -> None:
    records["evaluations"] += [revision("E1b", "E1")]
    progress = compute_progress(_validate(records, write_dataset).dataset)
    assert progress.non_human_evaluations == 2  # E1b and E2 (illustrative), not E1
    assert progress.superseded_evaluations == 1


# --- the interactive --revise flow ----------------------------------------------------------


@pytest.fixture
def reviewed_bench(bench_dir: Path) -> Path:
    """A benchmark with one saved human evaluation that has score digits as rationales."""
    flawed = make_evaluation(
        "EV0001",
        "P1-A",
        schema_version="1.1",
        reviewer_id="reviewer_01",
        annotation_source="human",
        scores={
            "accuracy": 4,
            "instruction_following": 5,
            "relevance": 4,
            "completeness": 4,
            "reasoning": 4,
            "clarity": 5,
            "safety": 5,
        },
        score_rationales={d: "4" for d in DIMENSIONS},
        overall_rationale="The model output is okay",
        reviewed_at="2026-10-10",
    )
    (bench_dir / "evaluations.json").write_text(json.dumps([flawed], indent=2), encoding="utf-8")
    return bench_dir


def keep_scores_answers(reason: str = "Original rationales were score digits.") -> list[str]:
    answers = [reason]
    for d in DIMENSIONS:
        answers += ["", f"Observed {d} detail in sentence one."]  # Enter keeps the score
    return [*answers, "n", "Accurate definition; two sentences as required.", ".", "s"]


def _revise(
    data_dir: Path, answers: list[str], evaluation_id: str = "EV0001", reviewer: str = "reviewer_01"
):
    dataset = validate_data_dir(data_dir).dataset
    console = ScriptedConsole(answers)
    record = revise_evaluation(
        console,
        data_dir,
        dataset,
        evaluation_id,
        reviewer,
        today=TODAY,
        drafts=DraftStore(data_dir),
    )
    return record, console


def _saved(data_dir: Path) -> list[dict]:
    return json.loads((data_dir / "evaluations.json").read_text(encoding="utf-8"))


def test_revise_appends_superseding_record_and_keeps_original(reviewed_bench: Path) -> None:
    original = _saved(reviewed_bench)[0]
    record, console = _revise(reviewed_bench, keep_scores_answers())
    assert "numeric_only: contains only a number" in console.text  # problems are listed first
    assert "must be rewritten" in console.text

    saved = _saved(reviewed_bench)
    assert saved[0] == original  # history preserved byte-for-byte (as parsed)
    assert saved[1] == record
    assert record["evaluation_id"] == "EV0002"
    assert record["supersedes"] == "EV0001"
    assert record["revision_reason"] == "Original rationales were score digits."
    assert record["schema_version"] == "1.2"
    assert record["scores"] == original["scores"]  # kept only because the reviewer pressed Enter

    result = validate_data_dir(reviewed_bench)
    assert result.ok, _errors(result)
    assert result.warnings == [w for w in result.warnings if "no candidate responses" in w.message]
    assert [e.evaluation_id for e in result.dataset.active_evaluations] == ["EV0002"]


def test_flagged_rationales_cannot_be_kept_with_enter(reviewed_bench: Path) -> None:
    answers = keep_scores_answers()
    # For accuracy: Enter keeps the score; Enter on the rationale must be refused because the
    # original "4" is not offered as a default; then a numeric answer is refused too.
    answers[1:3] = ["", "", "4", "Matches the WMO definition."]
    record, console = _revise(reviewed_bench, answers)
    assert console.text.count("A response is required here.") == 1
    assert "Not accepted: contains only a number" in console.text
    assert record["score_rationales"]["accuracy"] == "Matches the WMO definition."


def test_changed_score_is_shown_against_original(reviewed_bench: Path) -> None:
    answers = keep_scores_answers()
    answers[1] = "3"
    record, console = _revise(reviewed_bench, answers)
    assert record["scores"]["accuracy"] == 3
    assert "accuracy               3 (was 4)" in console.text


def test_generic_overall_rationale_warns_and_can_be_rewritten(reviewed_bench: Path) -> None:
    answers = keep_scores_answers()
    i = answers.index("Accurate definition; two sentences as required.")
    answers[i : i + 1] = [
        "The answer is good.",
        "n",
        "Accurate definition; two sentences as required.",
    ]
    record, console = _revise(reviewed_bench, answers)
    assert "WARNING: names no specific observation" in console.text
    assert record["overall_rationale"] == "Accurate definition; two sentences as required."


def test_generic_text_can_be_kept_after_confirmation(reviewed_bench: Path) -> None:
    answers = keep_scores_answers()
    i = answers.index("Accurate definition; two sentences as required.")
    answers[i : i + 1] = ["Fully correct and clear.", "y"]
    record, _ = _revise(reviewed_bench, answers)
    assert record["overall_rationale"] == "Fully correct and clear."
    assert any(
        "no_specific_content" in w.message for w in validate_data_dir(reviewed_bench).warnings
    )


def test_sequential_revisions_and_no_branching(reviewed_bench: Path) -> None:
    _revise(reviewed_bench, keep_scores_answers())
    with pytest.raises(AnnotationError, match="already been revised by EV0002; revise the latest"):
        _revise(reviewed_bench, keep_scores_answers())
    clean = keep_scores_answers("Second pass: verified the WMO period.")
    # EV0002's rationales are clean, so Enter now keeps both score and rationale.
    clean = [clean[0], *([""] * 2 * len(DIMENSIONS)), "n", "", ".", "s"]
    record, _ = _revise(reviewed_bench, clean, evaluation_id="EV0002")
    assert record["supersedes"] == "EV0002"
    assert record["score_rationales"]["accuracy"] == "Observed accuracy detail in sentence one."
    result = validate_data_dir(reviewed_bench)
    assert result.ok
    assert result.dataset.revision_chain("EV0003") == ["EV0001", "EV0002", "EV0003"]
    assert [e.evaluation_id for e in result.dataset.active_evaluations] == ["EV0003"]


@pytest.mark.parametrize(
    ("evaluation_id", "reviewer", "message"),
    [
        ("EV9999", "reviewer_01", "unknown evaluation_id"),
        ("EV0001", "reviewer_02", "only the original reviewer"),
    ],
)
def test_revise_refusals(
    reviewed_bench: Path, evaluation_id: str, reviewer: str, message: str
) -> None:
    with pytest.raises(AnnotationError, match=message):
        _revise(reviewed_bench, [], evaluation_id, reviewer)
    assert len(_saved(reviewed_bench)) == 1


def test_illustrative_records_cannot_be_revised(reviewed_bench: Path) -> None:
    records = _saved(reviewed_bench)
    records[0]["annotation_source"] = "illustrative_example"
    (reviewed_bench / "evaluations.json").write_text(json.dumps(records), encoding="utf-8")
    with pytest.raises(AnnotationError, match="not a human annotation"):
        _revise(reviewed_bench, [])


def test_interrupted_revision_resumes(reviewed_bench: Path) -> None:
    answers = keep_scores_answers()
    with pytest.raises(EOFError):
        _revise(reviewed_bench, answers[:5])  # reason + two dimensions
    assert DraftStore(reviewed_bench).keys() == ["revision__reviewer_01__EV0001"]
    assert len(_saved(reviewed_bench)) == 1
    record, console = _revise(reviewed_bench, answers[5:])
    assert "Resuming saved revision draft" in console.text
    assert record["supersedes"] == "EV0001"
    assert DraftStore(reviewed_bench).keys() == []


def test_original_error_labels_can_be_kept(reviewed_bench: Path) -> None:
    records = _saved(reviewed_bench)
    records[0]["errors"] = [
        {
            "label": "unclear",
            "evidence_status": "not_applicable",
            "note": "Second sentence is ambiguous.",
            "source": None,
        }
    ]
    (reviewed_bench / "evaluations.json").write_text(json.dumps(records), encoding="utf-8")
    answers = keep_scores_answers()
    i = answers.index("n")
    answers[i : i + 1] = ["y", "n"]  # keep original labels, add none
    record, _ = _revise(reviewed_bench, answers)
    assert record["errors"] == records[0]["errors"]


def test_cli_revise_end_to_end(reviewed_bench: Path, tmp_path: Path) -> None:
    console = ScriptedConsole(["y", *keep_scores_answers()])
    argv = [
        "annotate",
        "--data-dir",
        str(reviewed_bench),
        "--reviewer-id",
        "reviewer_01",
        "--revise",
        "EV0001",
    ]
    assert main(argv, console=console, today=TODAY) == EXIT_OK
    assert "Saved EV0002, superseding EV0001" in console.text
    out = tmp_path / "reports"
    argv = [
        "report",
        "--data-dir",
        str(reviewed_bench),
        "--output-dir",
        str(out),
        "--config",
        str(REPO_CONFIG),
    ]
    assert main(argv) == EXIT_OK
    rows = (out / "evaluation_results.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2 and rows[1].startswith("EV0002,")


def test_cli_revise_option_conflicts(reviewed_bench: Path) -> None:
    base = ["annotate", "--data-dir", str(reviewed_bench), "--reviewer-id", "reviewer_01"]
    assert (
        main([*base, "--revise", "EV0001", "--repeat"], console=ScriptedConsole([])) == EXIT_USAGE
    )
    with pytest.raises(SystemExit):
        main([*base, "--revise", "EV0001", "--response-id", "P1-A"])


def test_annotate_points_to_revise_for_existing_review(reviewed_bench: Path, capsys) -> None:
    argv = [
        "annotate",
        "--data-dir",
        str(reviewed_bench),
        "--reviewer-id",
        "reviewer_01",
        "--response-id",
        "P1-A",
    ]
    assert main(argv, console=ScriptedConsole(["y"]), today=TODAY) == EXIT_USAGE
    assert "--revise EV0001" in capsys.readouterr().err
