# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Before 1.0.0, minor versions may change behaviour.
Such changes are listed under **Changed**.

Versions describe the **software**. The human benchmark in `data/benchmark/` is data that
grows independently and is not a release artifact.

## [Unreleased]

## [0.4.0] - 2026-10-10

Public installation, CI, and documentation for first-time users.

### Added
- `ai-eval init DIR [--example]` creates a dataset folder with the four data files, record
  templates, and reference copies of the rubric and scoring configuration. It never
  overwrites existing files.
- Built-in package resources: the default scoring configuration, rubric, synthetic example
  dataset, and templates ship inside the wheel. The installed CLI works from any directory.
- `templates/prompt_template.json`.
- GitHub Actions CI: lint, tests, data validation, CLI smoke tests, and report generation on
  Ubuntu and Windows (Python 3.11–3.13) and macOS (Python 3.12). A packaging job builds the
  sdist and wheel and verifies a clean install.
- `scripts/verify_install.py` (clean-install verification) and `scripts/check_reports.py`.
- `docs/QUICKSTART.md`, `docs/RELEASING.md`, `CONTRIBUTING.md`, this changelog, and issue and
  pull-request templates.
- Package metadata: project URLs, classifiers, keywords.

### Changed
- The distribution is renamed to `llm-response-evaluation-lab` to match the project. The
  import package (`ai_response_eval`) and the `ai-eval` command are unchanged.
- `--config` and `--rubric` default to the built-in resources instead of paths relative to
  the current directory.
- A missing or non-directory `--data-dir` is now a usage error (exit code 2) with a hint to
  run `ai-eval init`. It was a validation failure (exit code 1).
- Running `ai-eval` without a command prints the full help with a quick start.
- `report` rejects an `--output-dir` that is an existing file and points to `summary.md` after
  writing.
- `build` is added to the `dev` extra.

### Fixed
- Tests no longer contain a credential-shaped literal, which could trip secret scanners.

## [0.3.0] - 2026-10-10

### Added
- Content-based rationale checks. Score-only and placeholder rationales are refused during
  annotation, generic ones produce a warning, and `validate` reports them on saved records.
- Evaluation corrections (`ai-eval annotate --revise ID`). A correction is a new record that
  supersedes the old one, forming a single revision chain. Data schema 1.2 adds the
  `supersedes`, `revision_reason`, and `consistency_check_of` fields.
- Report banners for revision history and rationale quality, and a `supersedes` column in the
  CSV.

### Changed
- `--repeat` records a consistency re-review (`consistency_check_of`) that is excluded from
  scoring.
- Two unrelated active evaluations of one response by the same reviewer are now an error. They
  were a warning, and were double-counted.
- Scoring, comparisons, progress, and reports use only active evaluations.

### Fixed
- The report banner no longer mentions "other illustrative records" when all records are human.
- Tests no longer read the live benchmark data.

## [0.2.0] - 2026-10-10

### Added
- Benchmark tools:
  - `ai-eval collect` imports real model responses with provenance;
  - `ai-eval annotate` and `ai-eval annotate-pair` run blind, resumable, append-only human
    annotation;
  - `ai-eval status` reports progress.
- 20 benchmark prompts with difficulty levels, evaluation objectives, and verifiable reference
  notes.
- Data schema 1.1, which adds prompt metadata and response collection metadata (optional and
  backward compatible).
- An annotation guide, a benchmark workflow guide, and JSON templates.
- "Incomplete annotation" and "No annotations yet" report banners.

## [0.1.0] - 2026-10-09

### Added
- Rubric v1.0: seven dimensions with score anchors, and a 22-label error taxonomy with
  evidence statuses.
- Pydantic schemas, cross-file validation, and a heuristic sensitive-content scan.
- Deterministic weighted scoring with null handling and review flags.
- Pairwise preferences with a labelled score-based suggestion.
- CSV, JSON, and Markdown reports with reproducibility metadata.
- The `ai-eval` CLI (`validate`, `score`, `compare`, `report`) and a synthetic demonstration
  dataset.

[Unreleased]: https://github.com/chimdaX/LLM_response_evaluation_lab/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/chimdaX/LLM_response_evaluation_lab/releases/tag/v0.4.0
