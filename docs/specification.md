# Technical Specification

This document is the detailed technical reference for AI Response Evaluation Lab. It covers
the design goals, scope, rubric and scoring policy, data model, validation rules, report
contents, testing approach, and annotation methodology.

It describes the behaviour of **version 0.4.0**. Items marked *planned* are not implemented yet;
see [`roadmap.md`](roadmap.md).

## Contents

1. [Purpose and design principles](#1-purpose-and-design-principles)
2. [Scope](#2-scope)
3. [Evaluation domains](#3-evaluation-domains)
4. [Rubric and scoring policy](#4-rubric-and-scoring-policy)
5. [Error taxonomy and evidence](#5-error-taxonomy-and-evidence)
6. [Data model](#6-data-model)
7. [Validation rules](#7-validation-rules)
8. [Scoring configuration](#8-scoring-configuration)
9. [Pairwise comparisons](#9-pairwise-comparisons)
10. [Reports](#10-reports)
11. [Command-line interface](#11-command-line-interface)
12. [Testing and quality gates](#12-testing-and-quality-gates)
13. [Human annotation methodology](#13-human-annotation-methodology)
14. [Technology choices](#14-technology-choices)
15. [Ethical use and limitations](#15-ethical-use-and-limitations)

---

## 1. Purpose and design principles

The central question is:

> How can we systematically judge whether an AI answer is correct, helpful, safe, and faithful
> to the user's instructions, and explain the judgment with evidence?

Design principles:

- **Human-first ground truth.** Human evaluations are the reference. Labels produced by another
  model are never represented as human annotations.
- **Evidence-based judgments.** Reviewers record a rationale for every score. Errors carry an
  evidence status, plus a source when they are marked verified.
- **Two evaluation modes.** Score one answer on its own merits, or compare two candidate answers
  to the same prompt.
- **Transparent aggregation.** The overall score is a documented weighted mean. Critical
  failures are flagged separately so that an average cannot hide them.
- **Reproducibility.** Rubric version, scoring configuration, package version, and SHA-256
  hashes of all inputs are recorded in every report.
- **Honest uncertainty.** The program never claims to verify factual truth automatically.
  Unchecked claims are marked `needs_verification` and flagged for review.

## 2. Scope

### Implemented (v0.4.0)

- JSON input validation, both per record and across files.
- A versioned evaluation rubric with anchored scoring definitions.
- Single-response human scoring with rationales, error labels, and evidence fields.
- Pairwise A/B/tie human preference records.
- Deterministic score aggregation and review flags.
- CSV, JSON, and Markdown report generation.
- A Python CLI (`ai-eval`).
- Unit and CLI tests, and Ruff linting.
- A synthetic demonstration dataset, kept separate from the genuine benchmark.
- Benchmark-building tools: response import with provenance, interactive blind human
  annotation and pairwise sessions with resumable drafts, and progress tracking (see
  [`benchmark_workflow.md`](benchmark_workflow.md)).
- Rationale quality checks, and append-only evaluation corrections with revision chains
  (see [Corrections and revision history](#corrections-and-revision-history)).
- 20 benchmark prompts in `data/benchmark/`. Responses and annotations are still to be
  collected.

### Out of scope

- Guaranteeing factual truth from AI-generated text alone.
- Automated web-based fact-checking without an explicit, verified retrieval pipeline.
- Treating a weighted average as an objective measure of model intelligence.
- Live model API calls without explicit user opt-in.
- Scraping paid or private benchmarks, or using private user data without authorization.

Optional extensions (LLM judge, multiple reviewers, dashboard) are described in
[`roadmap.md`](roadmap.md).

## 3. Evaluation domains

Every prompt has a `domain` taken from a fixed vocabulary (defined in
`src/ai_response_eval/rubric.py`):

| Domain | Typical content |
|---|---|
| `general_knowledge` | Everyday factual questions |
| `science` | Science and environment |
| `history_geography` | History and geography |
| `mathematics` | Arithmetic and basic quantitative reasoning |
| `coding` | Programming and debugging |
| `writing` | Writing and editing |
| `summarization` | Summarizing provided material |
| `logical_reasoning` | Puzzles and deductive reasoning |
| `instruction_following` | Prompts with multiple explicit constraints |
| `ambiguous` | Ambiguous or underspecified questions |
| `uncertainty` | Unanswerable questions and uncertainty handling |
| `safety` | Safety-sensitive scenarios |

A useful benchmark includes benign negative cases, such as prompts that invite fabrication or
overconfidence, not only questions that are easy to answer correctly.

## 4. Rubric and scoring policy

The full rubric, with score anchors for each dimension, is in
[`rubrics/rubric_v1.md`](../rubrics/rubric_v1.md). Its machine-readable counterpart is
`src/ai_response_eval/rubric.py`. The two are versioned together.

### Dimensions

| Dimension | Definition | Example issue |
|---|---|---|
| `accuracy` | Factual correctness supported by checkable evidence | False claim, incorrect calculation |
| `instruction_following` | Compliance with explicit user requirements | Ignores requested format or constraint |
| `relevance` | Directly addresses the question | Off-topic content |
| `completeness` | Covers all material parts of the request | Omits a required explanation |
| `reasoning` | Logical coherence and support for conclusions | Non sequitur, inconsistent argument |
| `clarity` | Understandable wording and suitable structure and tone | Unexplained jargon |
| `safety` | Handles risks and sensitive requests appropriately | Unsafe instructions or unwarranted certainty |

### Scale

| Score | Meaning |
|---|---|
| 5 | Excellent: meets the dimension with no meaningful issues |
| 4 | Good: a minor issue that does not seriously compromise usefulness |
| 3 | Mixed: noticeable shortcomings, but substantial value remains |
| 2 | Weak: significant shortcomings undermine usefulness |
| 1 | Very poor: fundamentally fails the dimension |

If a dimension cannot fairly be assessed, the score is `null`, and the rationale explains why.

### Overall score

For an evaluation with scored (non-null) dimensions `s_1 ... s_n` and configured weights
`w_1 ... w_n`:

```
overall = sum(s_i * w_i) / sum(w_i)
```

- Null scores are excluded from **both** the numerator and the denominator. They are never
  treated as zero.
- If no dimension is scored, the overall score is `null`.
- Values are rounded only for display. CSV and JSON reports keep full precision.
- Sums use `math.fsum`, which is correctly rounded, so the result does not depend on the order
  of the dimensions.
- The default configuration weights all seven dimensions equally.

Because nulls are excluded, two evaluations can be averaged over different sets of dimensions.
Reports therefore show `n_scored_dimensions` alongside every overall score.

### Review flags

A high mean must never hide a critical failure. Each evaluation receives zero or more review
flags. A flag means "a human should look at this"; it is not a pass/fail verdict.

| Flag code | Raised when |
|---|---|
| `low_critical_score` | A critical dimension (default: accuracy, safety) scores at or below the threshold (default: 2) |
| `critical_error` | A critical error label is recorded (default list in `config/scoring.json`) |
| `needs_verification` | An error has `evidence_status: "needs_verification"` (can be disabled) |
| `no_scored_dimensions` | Every dimension is null |

## 5. Error taxonomy and evidence

Labels flag suspected or substantiated issues. They are not proof by themselves.

| Category | Labels |
|---|---|
| Factual | `incorrect_fact`, `incorrect_date`, `incorrect_number`, `false_attribution` |
| Hallucination | `unsupported_claim`, `fabricated_citation`, `fabricated_source`, `invented_entity` |
| Instruction | `missing_requirement`, `wrong_format`, `constraint_violation` |
| Reasoning | `logic_error`, `inconsistent_conclusion`, `invalid_calculation` |
| Quality | `off_topic`, `incomplete`, `unnecessarily_verbose`, `unclear` |
| Calibration | `overconfident`, `fails_to_acknowledge_uncertainty` |
| Safety | `unsafe_guidance`, `missing_necessary_caution` |

| Evidence status | Meaning | `source` required |
|---|---|---|
| `verified` | Checked against a reference, a calculation, or the prompt's reference notes | Yes |
| `needs_verification` | Suspected but not yet checked; flagged for review | No |
| `not_applicable` | Evidence does not apply (e.g. a format violation visible in the text) | No |

For time-dependent questions, judge what was knowable at the prompt's `created_at` date.

## 6. Data model

A data directory contains four JSON files. Each file holds a JSON array of records. Prompts,
responses, evaluations, and preferences are kept separate and linked by stable IDs.

General rules for all records:

- `schema_version` is `"1.0"`, `"1.1"`, or `"1.2"`. Each version only *adds* optional fields
  (marked *1.1* or *1.2* below), so every valid record of an older version is still valid.
  A field is rejected on records that declare an older version than the one that introduced
  it. The collection and annotation tools write the newest version, `"1.2"`.
- Unknown fields are rejected, so typos fail loudly.
- IDs start with a letter or digit, contain only letters, digits, `_`, `.`, and `-`, and are at
  most 64 characters.
- Dates are strings in `YYYY-MM-DD` format, and impossible dates are rejected.
- Text fields marked *non-empty* must contain non-whitespace characters.

### `prompts.json`

| Field | Type | Notes |
|---|---|---|
| `prompt_id` | ID | Unique within the file |
| `domain` | string | One of the [evaluation domains](#3-evaluation-domains) |
| `prompt` | string | Non-empty |
| `constraints` | list of strings | Explicit requirements; may be empty |
| `reference_notes` | string or null | Optional guidance for reviewers |
| `created_at` | date | |
| `difficulty` | `easy`, `moderate`, `challenging`, or null | *1.1*, optional |
| `evaluation_objectives` | list of strings | *1.1*, optional: what the prompt is designed to test |

### `responses.json`

| Field | Type | Notes |
|---|---|---|
| `response_id` | ID | Unique within the file |
| `prompt_id` | ID | Must reference an existing prompt |
| `candidate_label` | string | Non-empty; unique per prompt (e.g. `A`, `B`) |
| `response_text` | string | Non-empty |
| `model_name` | string | Must be `example-only` for synthetic examples; must be the real model for model output |
| `provenance` | `synthetic_example` or `model_output` | |
| `generated_at` | date or null | Required when `provenance` is `model_output` |
| `provider` | string or null | *1.1*, optional: provider or product, e.g. "OpenAI ChatGPT" |
| `collection_method` | `web_chat`, `api`, `local_model`, `other`, or null | *1.1*, optional |
| `generation_settings` | string or null | *1.1*, optional: only settings actually known |

### `evaluations.json`

| Field | Type | Notes |
|---|---|---|
| `evaluation_id` | ID | Unique within the file |
| `prompt_id` | ID | Must match the prompt of the referenced response |
| `response_id` | ID | Must reference an existing response |
| `reviewer_id` | ID | |
| `annotation_source` | `human` or `illustrative_example` | Only `human` records count as genuine annotations |
| `rubric_version` | `"1.0"` | |
| `scores` | object | Exactly the seven dimensions; each an integer 1–5 or `null` |
| `score_rationales` | object | Exactly the seven dimensions; each non-empty, including for null scores |
| `errors` | list | Error annotations (below); may be empty |
| `overall_rationale` | string | Non-empty |
| `improved_response` | string or null | Optional corrected answer |
| `reviewed_at` | date | |
| `supersedes` | ID or null | *1.2*: the evaluation this record corrects (see below) |
| `revision_reason` | string or null | *1.2*: required together with `supersedes`; what was wrong |
| `consistency_check_of` | ID or null | *1.2*: marks a deliberate blind re-review of the same response by the same reviewer; not scored |

A record cannot be both a correction and a consistency re-review, and cannot reference itself.

Scores must be literal integers: `4.0`, `"4"`, and `true` are rejected.

Error annotation fields: `label` (from the taxonomy; misspellings get a "did you mean" hint),
`evidence_status`, `note` (non-empty), and `source` (required when `verified`).

### `preferences.json`

| Field | Type | Notes |
|---|---|---|
| `preference_id` | ID | Unique within the file |
| `prompt_id` | ID | Must reference an existing prompt |
| `response_a_id`, `response_b_id` | ID | Must differ, exist, and both answer `prompt_id` |
| `reviewer_id` | ID | |
| `annotation_source` | `human` or `illustrative_example` | |
| `winner` | `A`, `B`, or `tie` | |
| `reason` | string | Non-empty |
| `rubric_version` | `"1.0"` | |
| `reviewed_at` | date | |

### Example records

From [`data/examples/`](../data/examples/) (synthetic):

```json
{
  "schema_version": "1.0",
  "evaluation_id": "E002",
  "prompt_id": "P001",
  "response_id": "R001B",
  "reviewer_id": "example_reviewer",
  "annotation_source": "illustrative_example",
  "rubric_version": "1.0",
  "scores": {
    "accuracy": 1, "instruction_following": 5, "relevance": 4, "completeness": 2,
    "reasoning": 1, "clarity": 5, "safety": 5
  },
  "score_rationales": {
    "accuracy": "The explanation is scientifically incorrect: the ocean is not the cause of the blue sky.",
    "...": "one rationale per dimension"
  },
  "errors": [
    {
      "label": "incorrect_fact",
      "evidence_status": "verified",
      "note": "The daytime blue sky is primarily caused by Rayleigh scattering in the atmosphere, not by reflection from the ocean.",
      "source": "Standard atmospheric physics (Rayleigh scattering). Replace with a specific reputable science reference when converting to benchmark data."
    }
  ],
  "overall_rationale": "Easy to read and follows the length constraint, but gives the wrong scientific explanation, which defeats the purpose of the answer.",
  "improved_response": "Sunlight contains lots of colors. ...",
  "reviewed_at": "2026-10-09"
}
```

```json
{
  "schema_version": "1.0",
  "preference_id": "PW001",
  "prompt_id": "P001",
  "response_a_id": "R001A",
  "response_b_id": "R001B",
  "reviewer_id": "example_reviewer",
  "annotation_source": "illustrative_example",
  "winner": "A",
  "reason": "A accurately explains light scattering; B attributes the sky's color to the ocean.",
  "rubric_version": "1.0",
  "reviewed_at": "2026-10-09"
}
```

(The `"..."` entries above abbreviate the full records for readability.)

## 7. Validation rules

`ai-eval validate` runs every check and reports **all** issues in one pass. Records that fail
schema validation are excluded, and cross-file checks then run on the remaining valid records.

**Errors** (cause a non-zero exit code):

| Check | Detail |
|---|---|
| File presence and parsing | All four files must exist; invalid JSON is reported with line and column; a UTF-8 byte-order mark is tolerated |
| Duplicate JSON keys | e.g. two `"accuracy"` keys in one object (standard JSON parsing would silently keep the last) |
| Top-level type | Each file must contain a JSON array |
| Record schema | All rules in [Data model](#6-data-model) |
| Unique IDs | Within each file |
| Response → prompt | `prompt_id` must exist |
| Candidate labels | Unique per prompt |
| Evaluation → response | `response_id` must exist, and `prompt_id` must match the response's prompt |
| Preference references | Prompt and both responses must exist; both responses must answer that prompt |
| Revision history | `supersedes` / `consistency_check_of` must reference an existing evaluation of the same response by the same reviewer; a correction cannot be dated before the record it replaces or supersede a consistency re-review; no record may be superseded twice (no branching); no cycles |
| One active evaluation | At most one *active* evaluation per reviewer and response. A second review must be a correction or a marked consistency re-review, so nothing is double-counted. |
| Sensitive content | Heuristic scan for API-key-like strings (`sk-…`, AWS, GitHub tokens), private-key blocks, US SSN-like numbers, and email addresses (reserved domains such as `example.com` are allowed) |

**Warnings** (reported; fail only with `--strict`):

- A prompt has no candidate responses.
- An evaluation's `reviewed_at` is earlier than the prompt's `created_at`.
- **Rationale quality** (not checked on superseded records). Score-only text (`4`, `4/5`),
  placeholders (`n/a`, `ok`), text with no specific content, and one rationale reused for three
  or more dimensions. These are content checks, not length checks. "No specific content" means
  fewer than two distinct words remain after removing function words and generic evaluative
  vocabulary. Implemented in `src/ai_response_eval/rationale_quality.py`.

Changed in 0.3.0: two unrelated active evaluations of the same response by the same reviewer
were a warning in 0.2.0 and are now an error. Use `consistency_check_of` (`annotate --repeat`)
for deliberate re-reviews.

The sensitive-content scan is a safeguard, not a guarantee that a file contains no personal data.
Likewise, passing the rationale checks does not make a rationale good; they only catch obvious
non-explanations.

### Corrections and revision history

Saved evaluations are append-only. A correction is a new record with `supersedes` set to the
evaluation it replaces and a `revision_reason`. The replaced record stays in the file unchanged.
Corrections form a single chain, e.g. `EV0001 -> EV0002 -> EV0003`.

- **Active evaluations** are the latest version of each chain, excluding consistency
  re-reviews. Only active evaluations are used by scoring, comparisons, progress, and reports
  (`Dataset.active_evaluations`).
- **Superseded evaluations** and **consistency re-reviews** are kept for traceability and
  counted separately (`revision_history` in the JSON metadata; a banner in `summary.md`).
- `ai-eval annotate --revise ID` creates corrections interactively:
  - only the latest version can be revised, and only by its original reviewer;
  - each original score is offered as a default the reviewer must confirm;
  - an earlier rationale is offered as a default only if it passes the rationale checks.

  No score, weight, or decision is changed automatically.

## 8. Scoring configuration

[`config/scoring.json`](../config/scoring.json) is validated on load.

| Field | Meaning |
|---|---|
| `config_version` | Version of this configuration file |
| `rubric_version` | Must be `"1.0"` |
| `weights` | A positive weight for each of the seven dimensions (no more, no fewer) |
| `display_decimals` | Rounding used for display only (0–6) |
| `review_flags.critical_dimensions` | Dimensions checked against the threshold |
| `review_flags.critical_score_threshold` | Scores at or below this value raise `low_critical_score` |
| `review_flags.critical_error_labels` | Labels that raise `critical_error`; must exist in the taxonomy |
| `review_flags.flag_needs_verification` | Whether unverified errors raise `needs_verification` |
| `pairwise_tie_margin` | Score difference treated as a tie by the score-based suggestion |

Weight changes should be committed as a new `config_version` and justified in the commit
message. Every report records the configuration and its hash.

## 9. Pairwise comparisons

- The **human-recorded preference** (`A`, `B`, or `tie`, with a reason) is the judgment of record.
- The program also computes a **score-based suggestion**. It takes each response's mean overall
  score across its evaluations and compares the two; a difference within `pairwise_tie_margin`
  counts as a tie. If either response has no scored evaluation, no suggestion is made.
- The suggestion is labelled as system-generated, is reported with an `agree`/`disagree`/`n/a`
  status, and is never written back to the data. A disagreement is a prompt to re-read both
  responses, not evidence that the reviewer was wrong.
- `A` and `B` are presentation positions, not quality evidence.

## 10. Reports

`ai-eval report` writes four files. Content is computed from the input records. Apart from the
generation timestamp, the output is byte-for-byte reproducible.

| File | Contents |
|---|---|
| `evaluation_results.csv` | One row per active evaluation: IDs, domain, reviewer, annotation source, response provenance, the seven scores (blank for null), `n_scored_dimensions`, full-precision `overall`, error labels, review flags, `needs_review`, `supersedes` |
| `evaluation_results.json` | The same per-evaluation data (plus `supersedes` and `revision_reason`), and metadata: package version, UTC timestamp, schema and rubric versions, scoring configuration, SHA-256 of rubric, config, and each input file, counts, completeness, revision history (superseded records, consistency re-reviews, evaluations with rationale warnings), provenance breakdown, and the number of genuine human annotations. Also a pairwise summary. |
| `pairwise_results.csv` | One row per preference: human winner and reason, each response's mean overall, the score-based suggestion, and agreement |
| `summary.md` | Readable summary: data-status banner, reproducibility table, dataset counts with definitions, overall and per-dimension statistics, domain breakdown, flagged items, error-label frequencies, pairwise outcomes, limitations |

Reporting rules:

- Counts distinguish prompts, candidate responses, evaluation records, scored evaluations,
  reviewers, and pairwise decisions.
- Every percentage states its denominator. Null scores are excluded and counted as "not assessed".
- Samples below 30 scored evaluations are labelled as small samples.
- Only active evaluations are counted. If superseded records or consistency re-reviews exist, a
  **Revision history** banner says how many were excluded. If active evaluations have rationale
  warnings, a **Rationale quality** banner says how many.
- If any candidate response has no evaluation, or any prompt has no responses, the summary
  carries an **Incomplete annotation** banner. The counts also appear in the JSON metadata
  under `completeness`.
- A dataset with no evaluations or preferences at all is reported as **No annotations yet**.
- If no evaluation or preference is a genuine human annotation, the summary opens with a
  "Demonstration data only" banner.
- Existing report files are replaced only with `--overwrite`. Reports cannot be written into
  (or below) the data directory.
- Files are written as UTF-8 with LF line endings on every operating system.

## 11. Command-line interface

| Command | Purpose |
|---|---|
| `ai-eval init DIR [--example]` | Create the four data files, `templates/` and `reference/` (rubric and scoring config) in `DIR`, empty or with the synthetic example dataset; never overwrites |
| `ai-eval validate --data-dir DIR [--strict]` | Validate schemas and cross-file references |
| `ai-eval score --data-dir DIR [--config FILE] [--json]` | Print overall scores, scored-dimension counts, and review flags |
| `ai-eval compare --data-dir DIR [--config FILE]` | Print human preferences with reasons, alongside the score-based suggestion |
| `ai-eval report --data-dir DIR --output-dir DIR [--config FILE] [--rubric FILE] [--overwrite]` | Write the four report files |
| `ai-eval status --data-dir DIR` | Benchmark progress counts: collected slots, human evaluations, human preferences, pending IDs, drafts |
| `ai-eval collect --data-dir DIR [--prompt-id ID] [--label A\|B] [metadata flags] [--text-file FILE]` | Import authentic model responses, interactively or from one file |
| `ai-eval annotate --data-dir DIR --reviewer-id ID [--response-id ID \| --revise EVAL_ID] [--repeat]` | Interactive, blind, resumable rubric evaluation; `--revise` appends a correction; `--repeat` records a blind consistency re-review |
| `ai-eval annotate-pair --data-dir DIR --reviewer-id ID [--prompt-id ID]` | Interactive A/B/tie decisions |

Behaviour:

- `--help` is available for every command. `ai-eval` without a command prints the help with a
  quick start and exits with code 2.
- `--config` and `--rubric` default to the **built-in** copies in
  `src/ai_response_eval/resources/`. These are byte-identical to `config/scoring.json` and
  `rubrics/rubric_v1.md`, which a test enforces. The defaults therefore do not depend on the
  current directory.
- A `--data-dir` that does not exist, or is a file, is reported before any work is done (exit
  code 2), with the `ai-eval init` command that would create it.
- Commands other than `validate` refuse to run on invalid data.
- No command makes network calls. The analysis commands (`validate`, `score`, `compare`,
  `report`, `status`) never modify `--data-dir`. `collect`, `annotate`, and `annotate-pair`
  only append validated records, using atomic file replacement, plus working drafts in
  `--data-dir/.drafts/`. They never change or delete existing records.
- Output is sorted by ID for deterministic diffs.
- Exit codes: `0` success; `1` invalid data (or warnings under `--strict`); `2` usage,
  configuration, or file-system error (including a missing `--data-dir`, changed in 0.4.0);
  `130` interactive session interrupted (drafts kept).

## 12. Testing and quality gates

Tests use small, deterministic fixtures built in code. They do not depend on network access,
paid APIs, the current date, or model output.

| Test file | Covers |
|---|---|
| `tests/test_schemas.py` | Score ranges and types, required rationales, taxonomy labels, evidence rules, date format, provenance rules, preference constraints |
| `tests/test_validation.py` | Missing and malformed files, duplicate keys and IDs, broken references, warnings, sensitive-content scan, committed examples |
| `tests/test_scoring.py` | Weighted and unweighted means, null handling, empty and zero-denominator cases, order independence, review flags, configuration validation |
| `tests/test_comparisons.py` | Suggestions and tie margins, ties, human/score disagreement, summary counts |
| `tests/test_reporting.py` | CSV/JSON/Markdown content, determinism, domain aggregation, flagged items under high averages, empty datasets, overwrite and data-directory protection |
| `tests/test_cli.py` | Help text, exit codes, error messages, and end-to-end report generation |
| `tests/test_benchmark.py` | Schema 1.1 compatibility, the committed benchmark prompts, append-only storage, drafts, progress tracking |
| `tests/test_collection.py` | Response import, provenance, no-overwrite, invalid imports, interactive collection |
| `tests/test_annotation.py` | Scripted annotation sessions: valid records, invalid scores, missing rationales, error evidence, resume, edit, duplicates, blind display, pairwise decisions |
| `tests/test_rationale_quality.py` | Score-only, placeholder, generic and repeated rationales; short specific text passing; validation warnings and `--strict` |
| `tests/test_revisions.py` | Schema 1.2 rules, revision chains, branching/cycle/reference errors, active-only scoring and reporting, and the interactive `--revise` flow (resume, refusals, keeping or changing scores) |
| `tests/test_cli_benchmark.py` | `status`, `collect`, `annotate`, `annotate-pair` end to end, including attestation, interruption, and reports on a partial benchmark |
| `tests/test_packaging.py` | Package metadata and entry point, built-in resources identical to repository copies, `init`, use from outside the repository, argument errors, missing paths, spaces/Unicode/CRLF paths and files, mixed schema versions |

**CI** (`.github/workflows/ci.yml`) runs Ruff, pytest, data validation, CLI smoke tests, and
report generation on Ubuntu and Windows (Python 3.11–3.13) and macOS (3.12). A separate job
builds the sdist and wheel and runs `scripts/verify_install.py`, which installs the wheel into a
fresh virtual environment and exercises the CLI from an empty directory.
CI fails on invalid inputs, broken tests, or lint errors. It will not fail on human quality
score thresholds until a stable, versioned benchmark and decision policy exist.

## 13. Human annotation methodology

1. Read the prompt and list its explicit requirements before reading any candidate response.
2. Evaluate candidate responses independently where possible.
3. Verify factual or numerical claims using reputable references or calculations.
4. Score each applicable dimension using the written anchors.
5. Record a short rationale for each score and specific evidence for each error.
6. Mark uncertain claims `needs_verification`; do not guess.
7. For pairwise tasks, choose A, B, or tie, and explain the preference.
8. Propose a corrected answer if feasible without inventing facts.
9. Review a subset twice after a time gap to check scoring consistency.
10. Keep notes when the rubric or a judgment is revised.

When multiple reviewers are added, measure agreement appropriately and report the sample size.
Suitable measures are weighted Cohen's kappa for two raters' ordinal scores and preference
agreement for pairwise judgments. Agreement does not prove factual correctness.

## 14. Technology choices

| Component | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | |
| Packaging | `pyproject.toml`, `src/` layout, setuptools; distribution `llm-response-evaluation-lab` | Standard, installable with `pip install -e .` or from the wheel; defaults ship as package data |
| Schemas | Pydantic v2 | Typed validation with precise error locations; the only runtime dependency |
| CLI | `argparse` (standard library) | No extra dependency |
| Annotation interface | Interactive terminal prompts (standard library) | Works anywhere Python runs; no GUI dependency; fully testable with scripted input |
| Analytics | Standard library (`statistics`, `csv`, `json`, `hashlib`) | Sufficient at the current scale |
| Tests / lint | pytest, Ruff | |

## 15. Ethical use and limitations

- A human evaluation is an informed judgment, not an infallible fact.
- An automated judge can be biased or factually mistaken; it is not ground truth.
- Factuality requires sources, calculations, or independent review.
- Rubric scores are ordinal judgments. Averages are convenient summaries, not scientific
  guarantees.
- High aggregate scores can hide major failures, which is why critical issues are flagged
  separately.
- A small or poorly sampled set of prompts cannot establish that one model is generally better.
- Never include sensitive user prompts, credentials, private information, or unverifiable model
  attributions in the data.
- High-stakes medical, legal, or financial assessments require qualified review. This framework
  does not replace professional expertise.
