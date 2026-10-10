# Releasing

This document defines when a version is ready to release and how to publish it. Releases
are created only by the maintainer. Nothing in CI publishes automatically.

## Versioning

- The version lives in one place: `__version__` in `src/ai_response_eval/__init__.py`
  (`pyproject.toml` reads it dynamically).
- [Semantic Versioning](https://semver.org/). `0.x` releases may change behaviour.
  **1.0.0** is reserved for the first release whose readiness checklist is fully met,
  including a green CI run on GitHub.
- Software versions are independent of benchmark progress. The release notes must not
  present the in-progress human benchmark as a completed study.

## Release-readiness checklist

Every item must be checked for the commit being released.

| # | Check | How to verify |
|---|---|---|
| 1 | Lint and formatting clean | `ruff check . && ruff format --check .` |
| 2 | All tests pass locally | `python -m pytest` |
| 3 | **CI green on GitHub** for the release commit, on every matrix job | Actions tab → CI workflow → the run for the release commit |
| 4 | Package builds and metadata is valid | CI "Build and verify package" job (or `python -m build` and `twine check --strict dist/*`) |
| 5 | Wheel installs and works in a clean environment | `python scripts/verify_install.py` (CI runs it on Ubuntu and Windows) |
| 6 | CLI smoke tests | Covered by CI and `verify_install.py`: `--help`, `init`, `validate`, `score`, `compare`, `report`, `status` |
| 7 | Documentation matches behaviour | Commands in README and QUICKSTART run as shown; links are valid; version numbers updated |
| 8 | LICENSE present and included in the wheel | `verify_install.py` builds the wheel; the license is in its metadata |
| 9 | No credentials or private information | Credential and personal-path scan in `verify_install.py`; review `git diff` since the last tag |
| 10 | Human benchmark data preserved and valid | `ai-eval validate --data-dir data/benchmark` passes; no records removed (`git diff <last-tag> -- data/benchmark`) |
| 11 | Benchmark status described honestly | README status block says the benchmark is in progress unless `ai-eval status` reports COMPLETE |
| 12 | CHANGELOG updated | New version section with the date; `[Unreleased]` emptied |
| 13 | Supported platforms verified | CI matrix: Ubuntu and Windows (3.11–3.13), macOS (3.12) |

## Process

These steps publish to GitHub. Run them only when you intend to release.

1. **Merge to `main`.** Open a pull request from the feature branch to `main`, wait for CI to
   pass, and merge it.
2. **Prepare the release commit on `main`.** If the version changes, edit `__version__` and
   the `CHANGELOG.md` heading, commit (`release: v0.4.0`), push, and wait for CI to pass.
3. **Tag the exact commit that passed CI:**
   ```bash
   git switch main && git pull
   git tag -a v0.4.0 -m "v0.4.0"
   git push origin v0.4.0
   ```
4. **Create the GitHub Release.** Either:
   - on the web: Releases → *Draft a new release* → choose tag `v0.4.0` → paste the release
     notes → attach the `dist` artifact from the CI run (optional) → *Publish*; or
   - with the GitHub CLI:
     ```bash
     gh release create v0.4.0 --title "v0.4.0" --notes-file release-notes.md
     ```
     Add `--prerelease` for `0.x` versions if you want GitHub to mark them as pre-releases.
5. **Verify the release.** Clone the tag into a new folder and follow
   [QUICKSTART.md](QUICKSTART.md) from step 1.

Publishing to PyPI is **not** part of this process. If it is added later, use a separate,
manually triggered workflow with PyPI trusted publishing (OIDC). Never store API tokens in
the repository.

## Release notes for v0.4.0 (draft)

> **LLM Response Evaluation Lab v0.4.0**
>
> A human-first command-line framework for evaluating AI-generated answers, with rubric
> scoring, evidence-based error labels, blind annotation tools, revision history, and
> reproducible reports.
>
> **Highlights**
> - Installable from a clean environment. The only runtime dependency is Pydantic.
> - The default configuration, rubric, example dataset, and templates are built in, so the
>   installed CLI works from any directory.
> - New `ai-eval init DIR [--example]` creates a demo dataset or an empty dataset with
>   templates.
> - Friendlier CLI: help with a quick start, and clear errors for missing paths and bad
>   arguments.
> - GitHub Actions CI covers Linux, Windows, and macOS on Python 3.11–3.13, plus wheel
>   build and clean-install verification.
> - New Quick Start guide, setup guide, contributing guide, and changelog.
>
> **Also included (from 0.1–0.3):**
> - seven-dimension rubric with anchors, a 22-label error taxonomy, and weighted scoring with
>   review flags;
> - pairwise comparisons and CSV/JSON/Markdown reports;
> - response collection with provenance, and blind resumable annotation;
> - rationale quality checks and append-only evaluation corrections.
>
> **Breaking changes:**
> - The distribution is renamed to `llm-response-evaluation-lab`. Reinstall with
>   `pip install -e .`.
> - A missing `--data-dir` now exits with code 2.
>
> **Data status:** the repository includes a *synthetic* demonstration dataset (illustrative
> only) and an *in-progress* human benchmark. No benchmark results are claimed in this release.
>
> Full details: [CHANGELOG.md](../CHANGELOG.md)
