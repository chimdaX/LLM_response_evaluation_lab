"""Public-install behaviour: packaged resources, `init`, CLI argument handling, portability."""

from __future__ import annotations

import json
import sys
import tomllib
from importlib.metadata import distribution, version
from pathlib import Path

import pytest

from ai_response_eval import __version__, resources
from ai_response_eval.cli import EXIT_INVALID_DATA, EXIT_OK, EXIT_USAGE, main
from ai_response_eval.scaffold import ScaffoldError, init_dataset
from ai_response_eval.scoring import load_scoring_config
from ai_response_eval.validation import validate_data_dir
from tests.conftest import EXAMPLES_DIR, REPO_CONFIG, REPO_ROOT, REPO_RUBRIC

PYPROJECT = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
DATA_FILES = ("prompts.json", "responses.json", "evaluations.json", "preferences.json")


# --- packaging metadata --------------------------------------------------------------------


def test_runtime_dependencies_are_minimal() -> None:
    project = PYPROJECT["project"]
    assert project["dependencies"] == ["pydantic>=2.6,<3"]
    dev = " ".join(project["optional-dependencies"]["dev"])
    assert "pytest" in dev and "ruff" in dev  # dev tools are optional, never required


def test_console_script_is_declared_and_installed() -> None:
    assert PYPROJECT["project"]["scripts"] == {"ai-eval": "ai_response_eval.cli:main"}
    dist = distribution(PYPROJECT["project"]["name"])
    [script] = [ep for ep in dist.entry_points if ep.group == "console_scripts"]
    assert script.name == "ai-eval"
    assert script.value == "ai_response_eval.cli:main"


def test_installed_version_matches_package() -> None:
    assert version(PYPROJECT["project"]["name"]) == __version__


def test_package_data_globs_cover_resources() -> None:
    globs = PYPROJECT["tool"]["setuptools"]["package-data"]["ai_response_eval.resources"]
    assert {"*.json", "*.md", "examples/*.json", "templates/*.json"} <= set(globs)


# --- packaged resources stay identical to the repository copies ------------------------------


@pytest.mark.parametrize(
    ("packaged", "repo_copy"),
    [
        (("scoring.json",), REPO_CONFIG),
        (("rubric_v1.md",), REPO_RUBRIC),
        *[(("examples", name), EXAMPLES_DIR / name) for name in DATA_FILES],
        *[(("templates", p.name), p) for p in sorted((REPO_ROOT / "templates").glob("*.json"))],
    ],
    ids=lambda v: "/".join(v) if isinstance(v, tuple) else None,
)
def test_packaged_resource_matches_repository(packaged: tuple[str, ...], repo_copy: Path) -> None:
    assert resources.resource_path(*packaged).read_bytes() == repo_copy.read_bytes(), (
        f"src/ai_response_eval/resources/{'/'.join(packaged)} differs from {repo_copy}; "
        "update both copies together"
    )


def test_every_repo_template_is_packaged() -> None:
    repo = {p.name for p in (REPO_ROOT / "templates").glob("*.json")}
    packaged = {p.name for p in resources.resource_path("templates").glob("*.json")}
    assert repo == packaged and "prompt_template.json" in repo


def test_default_config_loads_from_package() -> None:
    assert load_scoring_config(resources.default_config_path()).rubric_version == "1.0"


def test_cli_works_outside_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No --config/--rubric and a foreign working directory: defaults come from the package."""
    monkeypatch.chdir(tmp_path)
    assert main(["init", "demo", "--example"]) == EXIT_OK
    assert main(["score", "--data-dir", "demo"]) == EXIT_OK
    assert "4 flagged for review" in capsys.readouterr().out
    assert main(["report", "--data-dir", "demo", "--output-dir", "out"]) == EXIT_OK
    meta = json.loads((tmp_path / "out" / "evaluation_results.json").read_text("utf-8"))
    assert meta["metadata"]["rubric_sha256"]  # built-in rubric was found and fingerprinted
    assert meta["metadata"]["scoring_config_sha256"]


# --- ai-eval init ---------------------------------------------------------------------------


def test_init_example_creates_valid_demo(tmp_path: Path) -> None:
    written = init_dataset(tmp_path / "demo", example=True)
    assert len(written) == 4 + len(list((REPO_ROOT / "templates").glob("*.json"))) + 2
    result = validate_data_dir(tmp_path / "demo")
    assert result.ok and result.warnings == []
    for name in DATA_FILES:
        assert (tmp_path / "demo" / name).read_bytes() == (EXAMPLES_DIR / name).read_bytes()


def test_init_empty_dataset_is_valid_and_has_templates(tmp_path: Path) -> None:
    init_dataset(tmp_path / "mine", example=False)
    result = validate_data_dir(tmp_path / "mine")
    assert result.ok and len(result.dataset.prompts) == 0
    assert (tmp_path / "mine" / "templates" / "prompt_template.json").is_file()
    assert (tmp_path / "mine" / "reference" / "rubric_v1.md").is_file()


def test_init_never_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "data"
    target.mkdir()
    (target / "evaluations.json").write_text('[{"precious": true}]', encoding="utf-8")
    with pytest.raises(ScaffoldError, match=r"already contains evaluations\.json"):
        init_dataset(target, example=True)
    assert (target / "evaluations.json").read_text(encoding="utf-8") == '[{"precious": true}]'
    assert not (target / "prompts.json").exists()  # nothing partially written


def test_init_into_existing_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert main(["init", str(tmp_path / "empty")]) == EXIT_OK


def test_init_target_is_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "f").write_text("x", encoding="utf-8")
    assert main(["init", str(tmp_path / "f")]) == EXIT_USAGE
    assert "is not a directory" in capsys.readouterr().err


# --- argument handling and missing paths --------------------------------------------------------


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == EXIT_USAGE
    out = capsys.readouterr().out
    assert "quick start" in out and "ai-eval init my-demo --example" in out


@pytest.mark.parametrize(
    "argv",
    [
        ["frobnicate"],
        ["score"],
        ["validate", "--data-dir"],
        ["report", "--data-dir", "x"],
        ["collect", "--data-dir", "x", "--label", "C"],
        ["annotate", "--data-dir", "x"],
    ],
)
def test_invalid_arguments_exit_2(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == EXIT_USAGE
    assert "usage: ai-eval" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command", ["validate", "score", "compare", "status", "collect", "report", "annotate"]
)
def test_missing_data_dir_is_a_usage_error_with_hint(
    command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [command, "--data-dir", str(tmp_path / "nope")]
    argv += {
        "report": ["--output-dir", str(tmp_path / "o")],
        "annotate": ["--reviewer-id", "r"],
    }.get(command, [])
    assert main(argv) == EXIT_USAGE
    err = capsys.readouterr().err
    assert "does not exist" in err and "ai-eval init" in err
    assert not (tmp_path / "o").exists()


def test_data_dir_that_is_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "file.json").write_text("[]", encoding="utf-8")
    assert main(["validate", "--data-dir", str(tmp_path / "file.json")]) == EXIT_USAGE
    assert "is a file, not a directory" in capsys.readouterr().err


def test_missing_data_files_get_a_hint(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "prompts.json").write_text("[]", encoding="utf-8")
    assert main(["validate", "--data-dir", str(tmp_path)]) == EXIT_INVALID_DATA
    assert "'ai-eval init DIR' creates them" in capsys.readouterr().err


def test_report_output_dir_that_is_a_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "out").write_text("x", encoding="utf-8")
    argv = ["report", "--data-dir", str(EXAMPLES_DIR), "--output-dir", str(tmp_path / "out")]
    assert main(argv) == EXIT_USAGE
    assert "is a file, not a directory" in capsys.readouterr().err


def test_missing_explicit_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["score", "--data-dir", str(EXAMPLES_DIR), "--config", str(tmp_path / "none.json")]
    assert main(argv) == EXIT_USAGE
    assert "scoring config not found" in capsys.readouterr().err


# --- cross-platform behaviour ----------------------------------------------------------------


def test_paths_with_spaces_and_unicode(tmp_path: Path) -> None:
    data = tmp_path / "my data — évaluations"
    out = tmp_path / "rapports finals"
    assert main(["init", str(data), "--example"]) == EXIT_OK
    assert main(["report", "--data-dir", str(data), "--output-dir", str(out)]) == EXIT_OK
    assert (out / "summary.md").is_file()


def test_crlf_data_files_validate_and_reports_use_lf(tmp_path: Path) -> None:
    """Files saved by Windows editors (CRLF) are accepted; generated files are always LF."""
    data = tmp_path / "crlf"
    data.mkdir()
    for name in DATA_FILES:
        text = (EXAMPLES_DIR / name).read_text(encoding="utf-8")
        (data / name).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert validate_data_dir(data).ok
    assert main(["report", "--data-dir", str(data), "--output-dir", str(tmp_path / "r")]) == EXIT_OK
    assert b"\r\n" not in (tmp_path / "r" / "summary.md").read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path form")
def test_windows_backslash_paths(tmp_path: Path) -> None:  # pragma: no cover - CI on Windows
    data = str(tmp_path / "demo").replace("/", "\\")
    assert main(["init", data, "--example"]) == EXIT_OK
    assert main(["validate", "--data-dir", data]) == EXIT_OK


# --- backward compatibility with existing data -----------------------------------------------


def test_all_schema_versions_coexist_in_one_dataset(tmp_path: Path) -> None:
    """1.0 example records, 1.1 benchmark-style records and 1.2 corrections together."""
    init_dataset(tmp_path / "mixed", example=True)  # schema 1.0 records
    evaluations = json.loads((tmp_path / "mixed" / "evaluations.json").read_text("utf-8"))
    correction = dict(
        evaluations[0],
        schema_version="1.2",
        evaluation_id="E001b",
        supersedes="E001",
        revision_reason="Recorded a specific accuracy check.",
    )
    (tmp_path / "mixed" / "evaluations.json").write_text(
        json.dumps([*evaluations, correction]), encoding="utf-8"
    )
    result = validate_data_dir(tmp_path / "mixed")
    assert result.ok, [str(i) for i in result.errors]
    assert "E001" not in {e.evaluation_id for e in result.dataset.active_evaluations}
