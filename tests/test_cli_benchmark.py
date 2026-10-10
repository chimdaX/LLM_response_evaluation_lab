"""End-to-end CLI behaviour of the Phase 2 commands: status, collect, annotate, annotate-pair."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_response_eval.cli import EXIT_INTERRUPTED, EXIT_OK, EXIT_USAGE, main
from ai_response_eval.interactive import ScriptedConsole
from tests.conftest import REPO_CONFIG, TODAY
from tests.test_annotation import full_evaluation


def _run(argv: list[str], answers: list[str] | None = None) -> tuple[int, ScriptedConsole]:
    console = ScriptedConsole(answers or [])
    return main(argv, console=console, today=TODAY), console


def test_status_of_unannotated_benchmark(
    fresh_benchmark: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = _run(["status", "--data-dir", str(fresh_benchmark)])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "0 of 40 slots" in out
    assert "INCOMPLETE" in out


def test_collect_text_file_import(
    fresh_benchmark: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = fresh_benchmark
    text_file = tmp_path / "answer.txt"
    text_file.write_text("Weather is short-term; climate is long-term.", encoding="utf-8")
    argv = [
        "collect",
        "--data-dir",
        str(data_dir),
        "--prompt-id",
        "B001",
        "--label",
        "A",
        "--model-name",
        "vendor-model-x",
        "--provider",
        "Vendor",
        "--method",
        "web_chat",
        "--generated-at",
        "2026-10-10",
        "--text-file",
        str(text_file),
    ]
    code, _ = _run(argv)
    assert code == EXIT_OK
    [record] = json.loads((data_dir / "responses.json").read_text(encoding="utf-8"))
    assert record["response_id"] == "B001-A"
    # Re-importing the same slot must fail without changing the file.
    code, _ = _run(argv)
    assert code == EXIT_USAGE
    assert "already has a response" in capsys.readouterr().err


def test_collect_text_file_requires_all_metadata(
    fresh_benchmark: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text_file = tmp_path / "a.txt"
    text_file.write_text("x", encoding="utf-8")
    code, _ = _run(["collect", "--data-dir", str(fresh_benchmark), "--text-file", str(text_file)])
    assert code == EXIT_USAGE
    assert (
        "--prompt-id, --label, --model-name, --provider, --method, --generated-at"
        in capsys.readouterr().err
    )


def test_annotate_full_session(bench_dir: Path) -> None:
    answers = ["y", *full_evaluation(), "n"]  # attest, evaluate P1-A, stop before P1-B
    code, console = _run(
        ["annotate", "--data-dir", str(bench_dir), "--reviewer-id", "reviewer_01"], answers
    )
    assert code == EXIT_OK
    assert "1 evaluation(s) saved this session" in console.text
    saved = json.loads((bench_dir / "evaluations.json").read_text(encoding="utf-8"))
    assert [e["response_id"] for e in saved] == ["P1-A"]

    # The analysis commands work on the partially annotated benchmark.
    for command in ("validate", "score", "compare"):
        extra = [] if command == "validate" else ["--config", str(REPO_CONFIG)]
        assert main([command, "--data-dir", str(bench_dir), *extra]) == EXIT_OK
    code = main(
        [
            "report",
            "--data-dir",
            str(bench_dir),
            "--output-dir",
            str(bench_dir.parent / "r"),
            "--config",
            str(REPO_CONFIG),
        ]
    )
    assert code == EXIT_OK
    summary = (bench_dir.parent / "r" / "summary.md").read_text(encoding="utf-8")
    assert "Incomplete annotation" in summary


def test_annotate_requires_attestation(bench_dir: Path) -> None:
    code, console = _run(["annotate", "--data-dir", str(bench_dir), "--reviewer-id", "r1"], ["n"])
    assert code == EXIT_USAGE
    assert "nothing was recorded" in console.text
    assert json.loads((bench_dir / "evaluations.json").read_text(encoding="utf-8")) == []


def test_annotate_interrupted_exit_code(bench_dir: Path) -> None:
    code, _ = _run(
        ["annotate", "--data-dir", str(bench_dir), "--reviewer-id", "r1"], ["y", "", "4"]
    )
    assert code == EXIT_INTERRUPTED
    assert (bench_dir / ".drafts" / "evaluation__r1__P1-A.json").exists()


def test_annotate_rejects_bad_reviewer_id(bench_dir: Path) -> None:
    code, _ = _run(["annotate", "--data-dir", str(bench_dir), "--reviewer-id", "bad id!"])
    assert code == EXIT_USAGE


def test_annotate_nothing_to_do(fresh_benchmark: Path) -> None:
    data_dir = fresh_benchmark
    code, console = _run(["annotate", "--data-dir", str(data_dir), "--reviewer-id", "r1"])
    assert code == EXIT_OK
    assert "Nothing to annotate" in console.text


def test_annotate_pair_session(bench_dir: Path) -> None:
    code, console = _run(
        ["annotate-pair", "--data-dir", str(bench_dir), "--reviewer-id", "r1"],
        ["y", "a", "A states the mechanism correctly.", "s"],
    )
    assert code == EXIT_OK
    [pref] = json.loads((bench_dir / "preferences.json").read_text(encoding="utf-8"))
    assert pref["winner"] == "A"
    assert "vendor-model-x" not in console.text
