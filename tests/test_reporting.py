"""Report content, determinism and file-writing safety."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_response_eval.comparisons import build_pairwise_rows
from ai_response_eval.reporting import (
    REPORT_FILES,
    ReportInputs,
    ReportWriteError,
    build_reports,
    write_reports,
)
from ai_response_eval.rubric import DIMENSIONS
from ai_response_eval.scoring import ScoringConfig, score_evaluations
from ai_response_eval.validation import validate_data_dir
from tests.conftest import (
    EXAMPLES_DIR,
    REPO_CONFIG,
    REPO_RUBRIC,
    Records,
    make_evaluation,
    make_prompt,
    make_response,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _reports(data_dir: Path, config: ScoringConfig) -> dict[str, str]:
    result = validate_data_dir(data_dir)
    assert result.ok, [str(i) for i in result.issues]
    scored = score_evaluations(result.dataset, config)
    inputs = ReportInputs(
        dataset=result.dataset,
        scored=scored,
        pairwise=build_pairwise_rows(result.dataset, scored, config),
        config=config,
        input_files=result.files,
        config_path=REPO_CONFIG,
        rubric_path=REPO_RUBRIC,
        generated_at=FIXED_TIME,
    )
    return build_reports(inputs)


def _csv_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_all_report_files_built(records: Records, write_dataset, config: ScoringConfig) -> None:
    assert set(_reports(write_dataset(records), config)) == set(REPORT_FILES)


def test_reports_are_deterministic(records: Records, write_dataset, config: ScoringConfig) -> None:
    data_dir = write_dataset(records)
    assert _reports(data_dir, config) == _reports(data_dir, config)


def test_evaluation_csv_rows_and_null_cells(
    records: Records, write_dataset, config: ScoringConfig
) -> None:
    records["evaluations"][1]["scores"]["safety"] = None
    rows = _csv_rows(_reports(write_dataset(records), config)["evaluation_results.csv"])
    assert [r["evaluation_id"] for r in rows] == ["E1", "E2"]
    assert list(rows[0])[7 : 7 + len(DIMENSIONS)] == list(DIMENSIONS)
    assert rows[1]["safety"] == ""  # not assessed is blank, never 0
    assert rows[1]["n_scored_dimensions"] == "6"
    assert float(rows[1]["overall"]) == pytest.approx(3.0)
    assert float(rows[0]["overall"]) == 5.0


def test_json_metadata(records: Records, write_dataset, config: ScoringConfig) -> None:
    doc = json.loads(_reports(write_dataset(records), config)["evaluation_results.json"])
    meta = doc["metadata"]
    assert meta["generated_at_utc"] == "2026-01-01T12:00:00Z"
    assert meta["rubric_version"] == "1.0"
    assert len(meta["rubric_sha256"]) == 64
    assert set(meta["input_files_sha256"]) == {
        "prompts.json", "responses.json", "evaluations.json", "preferences.json"
    }  # fmt: skip
    assert meta["counts"] == {
        "prompts": 1,
        "candidate_responses": 2,
        "evaluation_records": 2,
        "scored_evaluations": 2,
        "reviewers": 1,
        "pairwise_decisions": 1,
    }
    assert meta["genuine_human_evaluations"] == 0
    assert doc["pairwise_summary"]["a_wins"] == 1


def test_counts_distinguish_records_from_scored(
    records: Records, write_dataset, config: ScoringConfig
) -> None:
    records["evaluations"].append(
        make_evaluation(
            "E3", "R1B", reviewer_id="reviewer_02", scores={d: None for d in DIMENSIONS}
        )
    )
    doc = json.loads(_reports(write_dataset(records), config)["evaluation_results.json"])
    counts = doc["metadata"]["counts"]
    assert counts["evaluation_records"] == 3
    assert counts["scored_evaluations"] == 2
    assert counts["reviewers"] == 2


def test_domain_aggregation(records: Records, write_dataset, config: ScoringConfig) -> None:
    records["prompts"].append(make_prompt("P2", domain="mathematics"))
    records["responses"].append(make_response("R2A", prompt_id="P2"))
    records["evaluations"].append(
        make_evaluation("E3", "R2A", prompt_id="P2", scores={d: 2 for d in DIMENSIONS})
    )
    summary = _reports(write_dataset(records), config)["summary.md"]
    # science: E1=5.0 and E2=3.0 -> mean 4.00; mathematics: E3=2.0, flagged (accuracy=2).
    assert "| mathematics | 1 | 1 | 2.00 | 1 of 1 |" in summary
    assert "| science | 1 | 2 | 4.00 | 0 of 2 |" in summary


def test_flagged_item_listed_despite_high_average(
    records: Records, write_dataset, config: ScoringConfig
) -> None:
    records["evaluations"][0]["scores"]["safety"] = 1  # others stay 5 -> overall 4.43
    summary = _reports(write_dataset(records), config)["summary.md"]
    assert "| E1 | R1A | science | 4.43 | low_critical_score(safety=1) |" in summary


def test_summary_states_denominators_and_demo_status(
    records: Records, write_dataset, config: ScoringConfig
) -> None:
    summary = _reports(write_dataset(records), config)["summary.md"]
    assert "Demonstration data only" in summary
    assert "Small sample" in summary
    assert "Denominator: 1 pairwise decisions" in summary
    assert "| A preferred | 1 | 100.0% |" in summary


def test_human_annotations_change_banner(
    records: Records, write_dataset, config: ScoringConfig
) -> None:
    records["evaluations"][0]["annotation_source"] = "human"
    summary = _reports(write_dataset(records), config)["summary.md"]
    assert "Genuine human annotations: 1 of 2 evaluation records" in summary
    assert "Demonstration data only" not in summary


def test_empty_dataset_has_no_division_errors(write_dataset, config: ScoringConfig) -> None:
    empty: Records = {"prompts": [], "responses": [], "evaluations": [], "preferences": []}
    reports = _reports(write_dataset(empty), config)
    assert "No scored evaluations." in reports["summary.md"]
    assert "| A preferred | 0 | n/a |" in reports["summary.md"]
    assert reports["evaluation_results.csv"].count("\n") == 1  # header only


def test_example_reports_compute_from_data(config: ScoringConfig) -> None:
    reports = _reports(EXAMPLES_DIR, config)
    rows = {r["evaluation_id"]: r for r in _csv_rows(reports["evaluation_results.csv"])}
    assert len(rows) == 10
    assert float(rows["E002"]["overall"]) == pytest.approx(23 / 7)
    assert float(rows["E003"]["overall"]) == pytest.approx(19 / 6)  # safety is null
    assert rows["E009"]["needs_review"] == "true"


# --- writing ---------------------------------------------------------------------------


def test_write_refuses_overwrite_without_flag(tmp_path: Path) -> None:
    data_dir, out = tmp_path / "data", tmp_path / "reports"
    data_dir.mkdir()
    reports = {"summary.md": "first\n"}
    write_reports(reports, out, data_dir)
    with pytest.raises(ReportWriteError, match="--overwrite"):
        write_reports({"summary.md": "second\n"}, out, data_dir)
    assert (out / "summary.md").read_text(encoding="utf-8") == "first\n"
    write_reports({"summary.md": "second\n"}, out, data_dir, overwrite=True)
    assert (out / "summary.md").read_text(encoding="utf-8") == "second\n"


@pytest.mark.parametrize("subdir", ["", "reports"])
def test_write_refuses_data_directory(tmp_path: Path, subdir: str) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with pytest.raises(ReportWriteError, match="inside the data directory"):
        write_reports({"summary.md": "x\n"}, data_dir / subdir, data_dir)


def test_written_files_use_lf_newlines(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    [path] = write_reports({"summary.md": "a\nb\n"}, tmp_path / "out", data_dir)
    assert path.read_bytes() == b"a\nb\n"


def test_build_reports_does_not_touch_source_files(
    records: Records,
    write_dataset: Callable[[Records], Path],
    config: ScoringConfig,
    tmp_path: Path,
) -> None:
    data_dir = write_dataset(records)
    before = {p.name: p.read_bytes() for p in data_dir.iterdir()}
    write_reports(_reports(data_dir, config), tmp_path / "out", data_dir)
    assert {p.name: p.read_bytes() for p in data_dir.iterdir()} == before


# --- Phase 2: completeness banners ----------------------------------------------------------


def test_no_annotations_banner(write_dataset, config: ScoringConfig) -> None:
    records: Records = {"prompts": [make_prompt()], "responses": [make_response()],
                        "evaluations": [], "preferences": []}  # fmt: skip
    summary = _reports(write_dataset(records), config)["summary.md"]
    assert "No annotations yet" in summary
    assert "Demonstration data only" not in summary  # must not claim the data is illustrative
    assert "Incomplete annotation:** 1 of 1 candidate responses have no evaluation" in summary


def test_incomplete_banner_and_metadata(
    records: Records, write_dataset, config: ScoringConfig
) -> None:
    records["prompts"].append(make_prompt("P2"))
    records["evaluations"] = records["evaluations"][:1]
    reports = _reports(write_dataset(records), config)
    assert (
        "1 of 2 candidate responses have no evaluation and 1 of 2 prompts" in reports["summary.md"]
    )
    meta = json.loads(reports["evaluation_results.json"])["metadata"]
    assert meta["completeness"] == {
        "responses_without_evaluation": 1,
        "prompts_without_responses": 1,
    }


def test_complete_dataset_has_no_incomplete_banner(config: ScoringConfig) -> None:
    assert "Incomplete annotation" not in _reports(EXAMPLES_DIR, config)["summary.md"]


def test_all_human_banner_does_not_mention_illustrative_records(
    records: Records, write_dataset, config: ScoringConfig
) -> None:
    for e in records["evaluations"]:
        e["annotation_source"] = "human"
    records["preferences"][0]["annotation_source"] = "human"
    summary = _reports(write_dataset(records), config)["summary.md"]
    assert "Genuine human annotations: 2 of 2 evaluation records and 1 of 1" in summary
    assert "Other records are illustrative examples" not in summary
