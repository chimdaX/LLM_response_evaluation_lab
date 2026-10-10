"""Clean-install check: build the package, install the wheel in a fresh venv, run the CLI.

This proves the published artifacts work on their own -- without the repository's
virtual environment, its working directory, or any file outside the wheel. It is run
in CI and can be run locally:

    python -m pip install build
    python scripts/verify_install.py                 # build into a temp dir
    python scripts/verify_install.py --dist-dir dist # keep the built files

Steps:
  1. build an sdist and a wheel (python -m build);
  2. inspect both archives: required files present, no local absolute paths or
     credentials, no development-only files;
  3. create a fresh virtual environment and install the wheel (runtime deps only);
  4. confirm pytest and ruff were NOT installed (they are dev-only);
  5. from an empty working directory, run: --version, --help, init --example, validate,
     score, score --json, compare, status, report, and validate against the repository's
     example data passed explicitly with --data-dir.

Exit status 0 means every check passed. Needs network access for pip to fetch Pydantic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REQUIRED_IN_WHEEL = (
    "ai_response_eval/cli.py",
    "ai_response_eval/resources/scoring.json",
    "ai_response_eval/resources/rubric_v1.md",
    "ai_response_eval/resources/examples/prompts.json",
    "ai_response_eval/resources/examples/responses.json",
    "ai_response_eval/resources/examples/evaluations.json",
    "ai_response_eval/resources/examples/preferences.json",
    "ai_response_eval/resources/templates/prompt_template.json",
    "ai_response_eval/resources/templates/evaluation_template.json",
)
FORBIDDEN_IN_ARCHIVES = (".venv/", "__pycache__/", ".pytest_cache/", ".drafts/", "/.env")
# Patterns that indicate a leaked local path or credential inside packaged text files.
LEAK_PATTERNS = (
    re.compile(r"/mnt/[a-z]/Users/", re.IGNORECASE),
    re.compile(r"[A-Z]:\\Users\\", re.IGNORECASE),
    re.compile(r"/home/[a-z_][a-z0-9_-]*/", re.IGNORECASE),
    re.compile(r"/Users/[A-Za-z0-9_-]+/(?:Desktop|Documents|Downloads)"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
)

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  ok    " if condition else "  FAIL  ") + message)
    if not condition:
        failures.append(message)


def run(cmd: list[str], cwd: Path, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    shown = " ".join(Path(c).name if i == 0 else c for i, c in enumerate(cmd))
    check(result.returncode == expect, f"`{shown}` exits {expect} (got {result.returncode})")
    if result.returncode != expect:
        print(result.stdout[-2000:], result.stderr[-2000:], sep="\n")
    return result


def scan_text(name: str, data: bytes) -> list[str]:
    if not name.endswith((".py", ".json", ".md", ".txt", ".toml", ".cfg", "METADATA", "RECORD")):
        return []
    text = data.decode("utf-8", errors="replace")
    return [f"{name}: matches {p.pattern}" for p in LEAK_PATTERNS if p.search(text)]


def inspect_archives(dist: Path) -> Path:
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    check(len(wheels) == 1 and len(sdists) == 1, "exactly one wheel and one sdist were built")
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        for required in REQUIRED_IN_WHEEL:
            check(required in names, f"wheel contains {required}")
        check(
            not any(n.startswith(("tests/", "data/", "docs/")) for n in names),
            "wheel has no tests/, data/ or docs/ (only the package and its resources)",
        )
        leaks = [hit for n in names for hit in scan_text(n, zf.read(n))]
        metadata = next(zf.read(n).decode() for n in names if n.endswith(".dist-info/METADATA"))
    check(not leaks, "wheel contains no local absolute paths or credential-like strings")
    for leak in leaks:
        print("        " + leak)
    requires = [line for line in metadata.splitlines() if line.startswith("Requires-Dist:")]
    runtime = [r for r in requires if "extra ==" not in r]
    check(
        len(runtime) == 1 and "pydantic" in runtime[0],
        f"only runtime dependency is pydantic ({runtime})",
    )
    check(any('extra == "dev"' in r and "pytest" in r for r in requires), "pytest is a dev extra")

    with tarfile.open(sdists[0]) as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        bad = [m.name for m in members if any(f in m.name for f in FORBIDDEN_IN_ARCHIVES)]
        check(not bad, f"sdist contains no virtualenv, cache or draft files {bad or ''}")
        leaks = []
        for m in members:
            handle = tf.extractfile(m)
            if handle is not None:
                leaks += scan_text(m.name, handle.read())
    check(not leaks, "sdist contains no local absolute paths or credential-like strings")
    for leak in leaks:
        print("        " + leak)
    return wheel


def venv_executable(env: Path, name: str) -> Path:
    scripts = env / ("Scripts" if os.name == "nt" else "bin")
    suffix = ".exe" if os.name == "nt" else ""
    return scripts / f"{name}{suffix}"


def smoke_test(wheel: Path, work: Path) -> None:
    env = work / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(env)
    python = venv_executable(env, "python")
    run([str(python), "-m", "pip", "install", "--quiet", str(wheel)], cwd=work)
    for module in ("pytest", "ruff"):
        probe = subprocess.run([str(python), "-c", f"import {module}"], capture_output=True)
        check(probe.returncode != 0, f"{module} is not installed by a regular install")

    ai_eval = venv_executable(env, "ai-eval")
    check(ai_eval.exists(), f"console script installed at {ai_eval.relative_to(work)}")
    home = work / "user-home"  # empty directory: proves nothing depends on the repository
    home.mkdir()
    exe = str(ai_eval)

    version = run([exe, "--version"], home)
    check("ai-eval" in version.stdout, "--version prints the program name")
    check("quick start" in run([exe, "--help"], home).stdout, "--help shows the quick start")
    run([exe], home, expect=2)  # no command: help + usage exit code
    run([exe, "validate", "--data-dir", "missing"], home, expect=2)

    run([exe, "init", "demo", "--example"], home)
    validate = run([exe, "validate", "--data-dir", "demo"], home)
    check("5 prompts, 10 responses" in validate.stdout, "example dataset validates")
    score = run([exe, "score", "--data-dir", "demo"], home)
    check("4 flagged for review" in score.stdout, "score uses the built-in config")
    scored = json.loads(run([exe, "score", "--data-dir", "demo", "--json"], home).stdout)
    check(len(scored) == 10, "score --json returns 10 evaluations")
    compare = run([exe, "compare", "--data-dir", "demo"], home)
    check("A=2, B=2, tie=1" in compare.stdout, "compare reports human decisions")
    run([exe, "status", "--data-dir", "demo"], home)
    run([exe, "report", "--data-dir", "demo", "--output-dir", "reports"], home)
    for name in ("evaluation_results.csv", "evaluation_results.json", "pairwise_results.csv",
                 "summary.md"):  # fmt: skip
        check((home / "reports" / name).is_file(), f"report file {name} written")
    meta = json.loads((home / "reports" / "evaluation_results.json").read_text("utf-8"))
    check(bool(meta["metadata"]["rubric_sha256"]), "report fingerprints the built-in rubric")
    run([exe, "report", "--data-dir", "demo", "--output-dir", "reports"], home, expect=2)

    run([exe, "init", "mine"], home)
    run([exe, "validate", "--data-dir", "mine"], home)
    # Repository data still works when its path is supplied explicitly.
    run([exe, "validate", "--data-dir", str(REPO / "data" / "examples")], home)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist-dir", type=Path, help="build into this directory and keep it")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="ai-eval-verify-") as tmp:
        work = Path(tmp)
        dist = (args.dist_dir or work / "dist").resolve()
        print(f"1. Building sdist and wheel into {dist}")
        build = subprocess.run(
            [sys.executable, "-m", "build", "--outdir", str(dist), str(REPO)],
            capture_output=True,
            text=True,
        )
        check(build.returncode == 0, "python -m build succeeded")
        if build.returncode != 0:
            print(build.stdout[-3000:], build.stderr[-3000:], sep="\n")
            return 1
        print("2. Inspecting archives")
        wheel = inspect_archives(dist)
        print("3-5. Installing the wheel in a fresh virtual environment and running the CLI")
        smoke_test(wheel, work)

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s) failed")
        return 1
    print("PASSED: clean-install verification succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
