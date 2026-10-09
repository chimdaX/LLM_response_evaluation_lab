"""End-to-end CLI behaviour: exit codes, messages and files written."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_response_eval.cli import EXIT_INVALID_DATA, EXIT_OK, EXIT_USAGE, main
from tests.conftest import EXAMPLES_DIR, REPO_CONFIG, REPO_RUBRIC, Records

CONFIG = ["--config", str(REPO_CONFIG)]


@pytest.mark.parametrize("command", [[], ["validate"], ["score"], ["compare"], ["report"]])
def test_help_for_every_command(command: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([*command, "--help"])
    assert exc.value.code == 0
    assert "usage: ai-eval" in capsys.readouterr().out


def test_validate_examples(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "--data-dir", str(EXAMPLES_DIR)]) == EXIT_OK
    assert "5 prompts, 10 responses, 10 evaluations, 5 preferences" in capsys.readouterr().out


def test_validate_invalid_data_exits_nonzero(
    records: Records, write_dataset, capsys: pytest.CaptureFixture[str]
) -> None:
    records["evaluations"][0]["scores"]["accuracy"] = 7
    code = main(["validate", "--data-dir", str(write_dataset(records))])
    assert code == EXIT_INVALID_DATA
    err = capsys.readouterr().err
    assert "ERROR: evaluations.json [0] E1: scores.accuracy" in err
    assert "FAILED: 1 error(s)" in err


def test_validate_strict_fails_on_warnings(records: Records, write_dataset) -> None:
    records["evaluations"][0]["reviewed_at"] = "2025-01-01"
    data_dir = str(write_dataset(records))
    assert main(["validate", "--data-dir", data_dir]) == EXIT_OK
    assert main(["validate", "--data-dir", data_dir, "--strict"]) == EXIT_INVALID_DATA


def test_score_table_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["score", "--data-dir", str(EXAMPLES_DIR), *CONFIG]) == EXIT_OK
    out = capsys.readouterr().out
    assert "E002" in out and "3.29" in out
    assert main(["score", "--data-dir", str(EXAMPLES_DIR), *CONFIG, "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert [p["evaluation_id"] for p in payload] == sorted(p["evaluation_id"] for p in payload)


def test_commands_refuse_invalid_data(records: Records, write_dataset) -> None:
    records["preferences"][0]["winner"] = "C"
    data_dir = str(write_dataset(records))
    for command in ("score", "compare"):
        assert main([command, "--data-dir", data_dir, *CONFIG]) == EXIT_INVALID_DATA


def test_compare_labels_human_vs_system(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["compare", "--data-dir", str(EXAMPLES_DIR), *CONFIG]) == EXIT_OK
    out = capsys.readouterr().out
    assert out.count("Human-recorded preference:") == 5
    assert "System-generated score suggestion (not a human judgment)" in out
    assert "A=2, B=2, tie=1" in out


def test_missing_config_is_usage_error(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(["score", "--data-dir", str(EXAMPLES_DIR), "--config", str(tmp_path / "x.json")])
    assert code == EXIT_USAGE
    assert "scoring config not found" in capsys.readouterr().err


def test_report_writes_files_and_protects_existing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "reports"
    args = ["report", "--data-dir", str(EXAMPLES_DIR), "--output-dir", str(out_dir), *CONFIG,
            "--rubric", str(REPO_RUBRIC)]  # fmt: skip
    assert main(args) == EXIT_OK
    assert sorted(p.name for p in out_dir.iterdir()) == [
        "evaluation_results.csv",
        "evaluation_results.json",
        "pairwise_results.csv",
        "summary.md",
    ]
    capsys.readouterr()
    assert main(args) == EXIT_USAGE
    assert "pass --overwrite" in capsys.readouterr().err
    assert main([*args, "--overwrite"]) == EXIT_OK
