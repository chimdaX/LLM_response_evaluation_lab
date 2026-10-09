# AI Response Evaluation Lab

> A reproducible, human-first framework for evaluating AI-generated answers, comparing competing responses, and tracking quality regressions.

**Project type:** AI evaluation / generalist expert portfolio project  
**Primary language:** Python 3.11+  
**Status:** Phase 1 (foundation) is implemented and tested locally. Later phases are planned, not finished. See [Project status](#project-status).

## 1. Project overview

AI Response Evaluation Lab is a portfolio-ready tool for examining the quality of AI-generated answers across diverse subjects. It combines structured human review, transparent scoring, pairwise comparisons, error classification, reproducible reports, and automated checks. An optional later module compares automated LLM-judge scores against a carefully curated human-labeled benchmark.

The project's central question is:

**How can we systematically judge whether an AI answer is correct, helpful, safe, and faithful to the user's instructions—and explain the judgment with evidence?**

### What makes this project different

- **Human-first ground truth:** manual evaluations are the primary reference, not the outputs of another LLM.
- **Evidence-based judgments:** reviewers record reasons, error categories, and sources when factual checking is possible.
- **Two evaluation modes:** score one answer on its merits or compare two candidates against the same prompt.
- **Clear distinctions:** objective checks (e.g., word count) are separate from human judgments (e.g., factual accuracy).
- **Reproducibility:** input data, rubric version, validation rules, program version, and report generation are traceable.
- **Honest uncertainty:** unsupported claims are flagged for review; the program never pretends to verify factual truth automatically without supporting evidence.

## Project status

This README started as the implementation specification. The sections below record what actually exists.

### Implemented (Phase 1)

| Feature | Where |
|---|---|
| Versioned rubric v1.0 with dimension-specific anchors | `rubrics/rubric_v1.md`, `src/ai_response_eval/rubric.py` |
| Typed Pydantic schemas for prompts, responses, evaluations and preferences | `src/ai_response_eval/schemas.py` |
| Record-level and cross-file validation, plus a heuristic secret/PII scan | `src/ai_response_eval/validation.py` |
| Deterministic weighted scoring with null handling and review flags | `src/ai_response_eval/scoring.py`, `config/scoring.json` |
| Pairwise preferences with a separately labelled score-based suggestion | `src/ai_response_eval/comparisons.py` |
| CSV / JSON / Markdown reports with hashes and provenance metadata | `src/ai_response_eval/reporting.py` |
| CLI: `ai-eval validate`, `score`, `compare`, `report` | `src/ai_response_eval/cli.py` |
| Synthetic demonstration dataset (5 prompts, 10 responses, 10 evaluations, 5 preferences) | `data/examples/` |
| Unit and CLI tests (pytest) and Ruff lint config | `tests/`, `pyproject.toml` |

**Verified locally (Python 3.12, Linux/WSL):** `python -m pytest` passes (126 tests) and `ruff check .` reports no issues. CI is **not** set up yet, so there is no CI status.

**About the example data:** every response in `data/examples/` is a hand-written `synthetic_example` (model name `example-only`), and every evaluation and preference has `annotation_source: "illustrative_example"`. They demonstrate the workflow. They are **not** a human-reviewed benchmark and say nothing about any real model. `data/benchmark/` is empty until genuine reviews are added.

### Planned

- Phase 2: annotation guide, methodology notes, and the first 20 genuinely reviewed benchmark items.
- Phase 3: GitHub Actions (lint, tests, validation, report smoke test), example CLI transcript, release tag.
- Phase 4: larger benchmark; candidate-order bias study.

### Optional (v2)

LLM-as-a-judge with human-agreement analysis, blind A/B randomization, multiple reviewers and inter-rater reliability, dashboard, Docker.

### Quick start

See [`docs/SETUP.md`](docs/SETUP.md) for exact Windows PowerShell and Linux/macOS steps.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

ai-eval validate --data-dir data/examples
ai-eval score    --data-dir data/examples
ai-eval compare  --data-dir data/examples
ai-eval report   --data-dir data/examples --output-dir reports   # add --overwrite to regenerate
python -m pytest
ruff check .
```

### Deviations from the original specification

- **Added fields:** evaluations and preferences carry `annotation_source` (`human` | `illustrative_example`), so illustrative records can never be counted as human annotations. Response `provenance` is `synthetic_example` or `model_output`. A `model_output` must name its real model and `generated_at`; a `synthetic_example` must use `example-only`.
- **Rationales for every dimension:** null scores also need a rationale explaining why the dimension was not assessed.
- **Verified errors need a source:** `evidence_status: "verified"` requires a `source`.
- **Extra module and command:** `rubric.py` holds the machine-readable rubric, and `ai-eval score` prints per-evaluation results.
- **CLI library:** `argparse` (standard library) rather than Typer, to keep runtime dependencies to Pydantic only.

## 2. Goals and success criteria

### Primary goals

1. Build a dataset of diverse prompts and candidate responses.
2. Design a consistently interpretable 1–5 evaluation rubric.
3. Support human annotation with written rationales and traceable evidence.
4. Calculate per-dimension and aggregate scores transparently.
5. Compare two responses and explain which one is stronger, including ties.
6. Identify and categorize response failures, including hallucination risks.
7. Generate machine-readable outputs and a readable Markdown summary.
8. Run unit tests, data validation, and regression checks in GitHub Actions.
9. Optionally implement a judge-model integration and measure its agreement with human ratings.

### Milestones

| Milestone | Deliverable | Acceptance criteria |
|---|---|---|
| M1: Foundation | Project structure, rubric, schemas, CLI | Valid example input produces a deterministic result |
| M2: Human evaluation | Annotation workflow and sample benchmark | At least 20 **genuinely reviewed** items with rationales |
| M3: Reporting | CSV, JSON, Markdown outputs | Reports accurately summarize valid scored examples |
| M4: Comparisons | Pairwise preference workflow | A/B/tie decisions with reasons; position labels are not treated as quality evidence |
| M5: Quality engineering | Tests, lint, GitHub Actions | All automated checks run successfully on a clean clone |
| M6: Expanded dataset | Multiple domains and error types | Target 100–200 prompts, expanded only as time and review quality allow |
| M7: Optional AI judge | Provider-neutral judge interface | Human agreement and disagreement analysis, with missing/failed calls excluded |

**Important:** Milestone targets are goals, not completed results. Never invent dataset counts, agreement values, error rates, or CI successes.

## 3. Scope

### Included in v1 (minimum viable product)

- JSON and CSV input validation.
- A versioned evaluation rubric with anchored scoring definitions.
- Single-response human scoring.
- Pairwise human preference recording.
- Error labels and evidence fields.
- A Python command-line interface (CLI).
- Deterministic score aggregation and report generation.
- Unit tests and a continuous integration workflow.
- An example dataset clearly separated from the real human-reviewed benchmark.

### Optional in v2

- LLM-as-a-judge (opt-in, requires configured API credentials).
- Human–AI score and preference agreement analysis.
- Simple visual dashboard (Streamlit or static charts).
- Blind A/B order randomization for pairwise review.
- Multiple reviewers and inter-rater reliability analysis.
- Docker support.

### Out of scope for v1

- Guaranteeing factual truth from AI-generated text alone.
- Automated web-based fact-checking without an explicit verified retrieval pipeline.
- Claiming that a weighted average is an objective measure of intelligence.
- Making live model API calls without user opt-in.
- Scraping paid or private benchmarks.
- Using copyrighted or private user data without rights or authorization.

## 4. Evaluation domains

Create a diverse benchmark with domain labels such as:

- General knowledge
- Science and environment
- History and geography
- Mathematics and basic quantitative reasoning
- Coding and debugging
- Writing and editing
- Summarization
- Logical reasoning
- Multi-constraint instruction following
- Ambiguous or underspecified questions
- Unanswerable questions and uncertainty handling
- Safety-sensitive scenarios

Each record should have a prompt, domain, and at least one candidate response. Include benign negative examples designed to test unsupported claims and overconfidence, rather than relying solely on trivially correct answers.

## 5. Evaluation rubric

Rate each applicable dimension from **1 (poor)** to **5 (excellent)**. Every assigned score must have a written rationale. If a dimension cannot fairly be assessed, record `null` with a reason rather than forcing a number.

| Dimension | Definition | Example issue |
|---|---|---|
| Accuracy | Factual correctness supported by checkable evidence | False claim, incorrect calculation |
| Instruction following | Compliance with explicit user requirements | Ignores requested format or constraint |
| Relevance | Directly addresses the question | Off-topic content |
| Completeness | Covers all material parts of the request | Omits a required explanation |
| Reasoning | Logical coherence and support for conclusions | Non sequitur, inconsistent argument |
| Clarity | Understandable wording and suitable structure/tone | Unexplained jargon |
| Safety | Handles risks and sensitive requests appropriately | Unsafe instructions or unwarranted certainty |

### General scale (apply dimension-specific anchors as well)

| Score | Meaning |
|---|---|
| 5 | Excellent: meets the dimension with no meaningful issues |
| 4 | Good: a minor issue that does not seriously compromise usefulness |
| 3 | Mixed: noticeable shortcomings, but substantial value remains |
| 2 | Weak: significant shortcomings undermine usefulness |
| 1 | Very poor: fundamentally fails the dimension |

Provide separate dimension-specific anchor examples in `rubrics/rubric_v1.md`, especially for accuracy, instruction following, and safety. Reviewers must assess context: for example, a concise answer can be fully complete if the user asked for brevity.

### Scoring policy

**Default:** Use equal weights for applicable dimensions; document any changes in a versioned configuration. Do not treat an unassessed dimension as zero.

For an item with applicable scores `s_1 ... s_n` and normalized weights `w_1 ... w_n`:

`overall = sum(s_i * w_i) / sum(w_i)`

Round **only for display**, not during intermediate calculations. Return `null` for the overall score if nothing was scored. Validate values are integers 1–5 (unless explicitly extending the schema later).

The safety and accuracy dimensions must also be shown separately; a high mean must never silently override an identified critical safety or factual failure. A configurable *flag*, not a fabricated pass/fail judgment, should mark items that need review.

## 6. Error taxonomy

Use structured labels to support analysis. Labels flag suspected or substantiated issues; they are not proof by themselves.

| Category | Example labels |
|---|---|
| Factual | `incorrect_fact`, `incorrect_date`, `incorrect_number`, `false_attribution` |
| Hallucination | `unsupported_claim`, `fabricated_citation`, `fabricated_source`, `invented_entity` |
| Instruction | `missing_requirement`, `wrong_format`, `constraint_violation` |
| Reasoning | `logic_error`, `inconsistent_conclusion`, `invalid_calculation` |
| Quality | `off_topic`, `incomplete`, `unnecessarily_verbose`, `unclear` |
| Calibration | `overconfident`, `fails_to_acknowledge_uncertainty` |
| Safety | `unsafe_guidance`, `missing_necessary_caution` |

Use `evidence_status` values such as `verified`, `needs_verification`, and `not_applicable`. Where feasible, capture a source URL/title or a concise explanation of how a claim was checked. For time-dependent questions, store the date context and judge what was knowable at that time.

## 7. Data model

Keep IDs stable and separate prompts, candidate responses, and evaluations. Version the schema using `schema_version`.

### Prompt: `data/examples/prompts.json`

```json
[
  {
    "schema_version": "1.0",
    "prompt_id": "P001",
    "domain": "science",
    "prompt": "Explain why the sky looks blue to a 10-year-old in no more than 80 words.",
    "constraints": ["Age-appropriate language", "Maximum 80 words"],
    "reference_notes": "The explanation should mention scattering of shorter wavelengths in accessible terms.",
    "created_at": "2026-10-09"
  }
]
```

### Candidate responses: `data/examples/responses.json`

```json
[
  {
    "schema_version": "1.0",
    "response_id": "R001A",
    "prompt_id": "P001",
    "candidate_label": "A",
    "response_text": "Sunlight has many colors. As it passes through the air, blue light gets scattered around more than most other colors, so we see a blue sky.",
    "model_name": "example-only",
    "provenance": "synthetic_example",
    "generated_at": null
  },
  {
    "schema_version": "1.0",
    "response_id": "R001B",
    "prompt_id": "P001",
    "candidate_label": "B",
    "response_text": "The sky is blue because the ocean reflects its blue color onto the air.",
    "model_name": "example-only",
    "provenance": "synthetic_example",
    "generated_at": null
  }
]
```

Never assign a specific real model name unless the response genuinely came from that model and its provenance is recorded.

### Human evaluation: `data/examples/evaluations.json`

```json
[
  {
    "schema_version": "1.0",
    "evaluation_id": "E001",
    "prompt_id": "P001",
    "response_id": "R001B",
    "reviewer_id": "reviewer_01",
    "rubric_version": "1.0",
    "scores": {
      "accuracy": 1,
      "instruction_following": 5,
      "relevance": 4,
      "completeness": 2,
      "reasoning": 1,
      "clarity": 5,
      "safety": 5
    },
    "score_rationales": {
      "accuracy": "The explanation is scientifically incorrect.",
      "instruction_following": "The answer uses simple language and satisfies the word limit.",
      "relevance": "It addresses the sky color question but gives a false cause.",
      "completeness": "It does not explain scattering of sunlight.",
      "reasoning": "The causal explanation is unsupported and incorrect.",
      "clarity": "The wording is easy to understand.",
      "safety": "No safety concerns in this context."
    },
    "errors": [
      {
        "label": "incorrect_fact",
        "evidence_status": "verified",
        "note": "The sky's daytime blue color is primarily due to atmospheric scattering, not ocean reflection.",
        "source": "Reviewer reference note; add a reputable science reference during annotation."
      }
    ],
    "overall_rationale": "Easy to read and follows the length constraint but gives the wrong scientific explanation.",
    "improved_response": "Sunlight contains lots of colors. When it travels through the air, blue light spreads out in many directions more than most other colors. That scattered blue light is why the sky looks blue!",
    "reviewed_at": "2026-10-09"
  }
]
```

The sample above is **illustrative**, not a published benchmark finding. For actual benchmark data, preserve reviewer provenance and never represent model-generated labels as human annotations.

### Pairwise judgment: `data/examples/preferences.json`

```json
[
  {
    "schema_version": "1.0",
    "preference_id": "PW001",
    "prompt_id": "P001",
    "response_a_id": "R001A",
    "response_b_id": "R001B",
    "reviewer_id": "reviewer_01",
    "winner": "A",
    "reason": "A accurately explains light scattering; B attributes the sky's color to the ocean.",
    "rubric_version": "1.0",
    "reviewed_at": "2026-10-09"
  }
]
```

Allowed `winner` values: `A`, `B`, `tie`. In the CLI output, clearly distinguish a *human-recorded preference* from a *system-generated suggestion*. Do not automatically declare the highest numeric scorer the human-selected winner.

## 8. Proposed repository structure

> Phase 1 follows this layout, with these differences: `src/ai_response_eval/rubric.py` was added; `judge.py`, `.env.example`, `.github/workflows/ci.yml` and the `docs/` notes other than `SETUP.md` do not exist yet; tests also include `test_schemas.py` and `test_cli.py`.

```text
ai-response-evaluation-lab/
├── README.md
├── LICENSE
├── .gitignore
├── pyproject.toml
├── .env.example
├── .github/
│   └── workflows/
│       └── ci.yml
├── config/
│   └── scoring.json
├── rubrics/
│   └── rubric_v1.md
├── data/
│   ├── examples/
│   │   ├── prompts.json
│   │   ├── responses.json
│   │   ├── evaluations.json
│   │   └── preferences.json
│   └── benchmark/
│       └── .gitkeep
├── src/
│   └── ai_response_eval/
│       ├── __init__.py
│       ├── cli.py
│       ├── schemas.py
│       ├── validation.py
│       ├── scoring.py
│       ├── comparisons.py
│       ├── reporting.py
│       └── judge.py              # Optional in v2
├── tests/
│   ├── test_validation.py
│   ├── test_scoring.py
│   ├── test_comparisons.py
│   ├── test_reporting.py
│   └── fixtures/
├── reports/
│   └── .gitkeep
└── docs/
    ├── annotation_guide.md
    ├── methodology.md
    ├── limitations.md
    └── roadmap.md
```

Prefer a lightweight standard Python package with `pyproject.toml`, type hints, and no unnecessary web application framework in v1.

## 9. Technology stack

| Component | Choice |
|---|---|
| Language | Python 3.11+ |
| CLI | `argparse` or Typer (choose one and document it) |
| Schemas | Pydantic or standard-library validation (choose one consistently) |
| Data | JSON source, CSV exports |
| Analytics | Standard library first; optionally pandas for expanded reporting |
| Tests | pytest |
| Code quality | Ruff |
| Automation | GitHub Actions |
| Optional dashboard | Streamlit |
| Optional AI judge | Provider-neutral interface with opt-in API integration |
| Optional container | Docker |

Do not require a paid model API or external service for v1 installation, testing, or reporting.

## 10. CLI specification

Expose a documented entry point named `ai-eval`. The commands below are implemented and were run successfully during Phase 1 development. `ai-eval score --data-dir data/examples` additionally prints per-evaluation overall scores and review flags.

```bash
# Install for local development
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'

# Validate all sample data and cross-file references
ai-eval validate --data-dir data/examples

# Create score and issue reports from existing evaluations
ai-eval report --data-dir data/examples --output-dir reports

# List pairwise reviewer preferences, with rationales
ai-eval compare --data-dir data/examples

# Run checks
python -m pytest
ruff check .
```

CLI behavior requirements:

- `--help` for every command.
- Friendly actionable error messages and nonzero exit status for invalid inputs.
- No implicit network calls.
- Output sorted predictably for deterministic diffs.
- Never overwrite manually annotated source data during reporting.
- Require explicit flags for operations that overwrite generated report files.

## 11. Validation requirements

Validate at minimum:

1. Parseable JSON and expected top-level collection types.
2. Unique IDs within each collection.
3. Nonempty prompt and response texts.
4. Each response references an existing prompt.
5. Each evaluation references an existing response and its correct prompt.
6. Each preference refers to two different responses for the same prompt.
7. Score keys match the versioned rubric; ratings are 1–5 or `null`.
8. Every non-null score has a nonempty rationale.
9. Every error label belongs to the taxonomy.
10. Valid `winner` and evidence-status values.
11. No duplicate evaluation IDs or preference IDs.
12. Consistent date formatting and schema versions.
13. No accidental inclusion of secrets or personally identifying data in examples.

## 12. Reporting requirements

Generate:

- `reports/evaluation_results.csv` — one row per evaluation, including IDs, scores, computed overall, and error flags.
- `reports/evaluation_results.json` — equivalent structured information plus reproducibility metadata.
- `reports/summary.md` — human-readable count summaries, score distributions, domain breakdowns, commonly tagged issues, and limitations.
- `reports/pairwise_results.csv` — A/B/tie counts and review rationales.

Report counts should differentiate **prompts**, **candidate responses**, **scored evaluations**, **reviewers**, and **pairwise decisions**. They are not interchangeable.

Include denominator definitions for percentages. Exclude null scores appropriately rather than silently imputing them. Clearly label small samples. When practical, add the source data and rubric hashes, UTC generation timestamp, package version, and scoring configuration to metadata.

Do not publish fictional benchmark metrics. Reports must compute from the actual input records.

## 13. Tests and quality gates

Add unit tests for:

- Valid and invalid score ranges.
- Null scores and correct denominator handling.
- Stable weighted and unweighted calculations.
- Missing or invalid references between datasets.
- Incomplete rationales.
- Duplicate IDs.
- Pairwise ties and same-response comparison rejection.
- Empty datasets and zero-denominator cases.
- Deterministic output ordering and schema correctness.
- Accurate aggregation across domains.
- Critical error flags remaining visible even with high average scores.

Use small deterministic fixtures. Test expectations must not depend on a paid API, live website, current date, or nondeterministic model output.

### GitHub Actions

On pull requests and pushes to the main branch:

1. Check out repository.
2. Set up supported Python version.
3. Install the package and dev dependencies.
4. Run Ruff.
5. Run pytest.
6. Validate sample datasets using the CLI.
7. Generate reports into a temporary directory as a smoke test.
8. Optionally upload generated artifacts for review.

Fail CI on invalid inputs, broken tests, or lint errors. Do **not** fail CI on arbitrary human quality score thresholds until a stable, explicitly versioned benchmark and decision policy exist. Later, optional regression checks should use a documented baseline and explain every threshold.

## 14. Human annotation methodology

A credible generalist-expert portfolio needs strong reviewing practices:

1. Read the prompt and list explicit requirements before reading candidate responses.
2. Evaluate candidate responses independently where possible.
3. Verify factual or numerical claims using reputable references or calculations.
4. Score each applicable dimension using the written anchors.
5. Record a short rationale for each score and specific error evidence.
6. Mark uncertain claims `needs_verification`; do not guess.
7. Choose A/B/tie and explain the preference for pairwise tasks.
8. Propose a corrected answer if feasible without inventing facts.
9. Review a subset twice after a time gap to check scoring consistency.
10. Keep notes when the rubric or a judgment is revised.

When multiple reviewers are added, measure agreement appropriately (for example, weighted Cohen's kappa for two raters' ordinal scores, and preference agreement for pairwise judgments) and report sample size. Explain that agreement does not prove factual correctness.

## 15. Optional LLM-as-a-judge experiment (v2)

Once a human-labeled set exists, implement a separate optional judge module that:

- Accepts the same prompt, candidate response(s), and rubric definition.
- Requests structured scores and rationales from a configured model.
- Validates returned data and handles malformed outputs, retries, rate limits, and API failures.
- Logs provider, model identifier, judge prompt version, timestamp, and inference settings.
- Compares automated and human scores using MAE per dimension and rank/preference agreement.
- Tests response-order sensitivity by swapping candidate positions.
- Notes potential length and verbosity biases.
- Excludes failed calls from agreement calculations while reporting failure counts.
- Separately labels model-produced rationales from externally verified factual evidence.

Keep secrets in environment variables or CI secrets, never in git. Add `.env.example` with placeholder names and `.env` to `.gitignore`. A local-only, API-free workflow must continue working.

## 16. Ethical use and limitations

- A human evaluation is an informed judgment, not an infallible fact.
- An automated judge can be biased or factually mistaken; it is not ground truth.
- Factuality requires sources, calculations, or independent review.
- Rubric scores are ordinal judgments; averages are convenient summaries, not scientific guarantees.
- High aggregate scores can hide major failures; surface critical issues prominently.
- Poorly sampled benchmark examples do not establish broad model superiority.
- Never include sensitive user prompts, credentials, private information, or unverifiable model attributions.
- Domain-specific high-stakes assessments require qualified review; do not present the framework as a substitute for professional expertise.

## 17. Development roadmap

### Phase 1: Foundation
- [x] Initialize Python package and development environment.
- [x] Add complete rubric and schema definitions.
- [x] Add 3–5 realistic, clearly labeled demonstration prompts.
- [x] Implement validation and deterministic scoring.
- [x] Add CLI commands and focused unit tests.

### Phase 2: Evaluation workflow
- [x] Add error taxonomy and evidence tracking. *(delivered in Phase 1)*
- [x] Add pairwise preference handling. *(first version delivered in Phase 1)*
- [x] Add CSV, JSON, and Markdown reporting. *(first version delivered in Phase 1)*
- [ ] Write annotation guide and methodology notes.
- [ ] Manually review the first 20 benchmark items.

### Phase 3: GitHub-ready release
- [ ] Add GitHub Actions with lint, tests, and report smoke test.
- [ ] Add example CLI transcript using real computed output.
- [ ] Add screenshots or charts only after they exist.
- [ ] Add LICENSE, contribution guidance, and limitations. *(MIT LICENSE added; the rest is pending)*
- [ ] Tag an initial release.

### Phase 4: Research extension
- [ ] Grow the manually reviewed benchmark toward 100–200 prompts.
- [ ] Add optional LLM judge and agreement evaluation.
- [ ] Study disagreement patterns and candidate order bias.
- [ ] Add an optional dashboard or Docker image.

## 18. Portfolio presentation

Once the project is built and evaluated, the README should be updated with:

- A concise overview of what actually works.
- A demo showing one complete evaluation from input to report.
- Real dataset sizes and the number of genuinely human-reviewed items.
- Actual test and CI status.
- Sample analyses and failure cases, with verified evidence.
- A discussion of difficult evaluator decisions and remaining limitations.

**Suggested resume bullet (edit only after implementation):**

> Developed a Python-based AI response evaluation framework with rubric-based human annotation, pairwise candidate ranking, documented error taxonomy, reproducible reports, and GitHub Actions quality checks; extended it to study agreement between manual judgments and an optional LLM judge.

---

## 19. Instructions for Claude: build this repository

**Claude, treat this README as the project specification. Implement the project incrementally in the current repository.**

### Required behavior

1. **Start with Phase 1, not the entire roadmap in one pass.** Explain the implementation plan briefly, then create working files.
2. Use Python 3.11+, a conventional `src/` package, `pyproject.toml`, pytest, and Ruff. Keep dependencies small.
3. Build a **fully functional, offline MVP** before adding any AI APIs or dashboards.
4. Implement robust typed schemas, cross-file validation, rubric-based score aggregation, and CLI entry points.
5. Include coherent example datasets. Mark examples as synthetic/illustrative and never claim they were collected from real models or manually reviewed when they were not.
6. Implement actual tests, not placeholder tests. Test failure cases as well as normal operation.
7. Write readable code with docstrings for non-obvious logic, useful errors, and clear comments where needed.
8. Run tests and lint when execution is available. If execution is unavailable, say so; do not claim success.
9. After implementation, update this README to distinguish **Implemented**, **Planned**, and **Optional** sections and replace hypothetical commands with verified ones.
10. Create a separate `docs/SETUP.md` with exact Windows PowerShell and Linux/macOS setup instructions.
11. Keep report outputs generated from data, not hard-coded; compute all examples honestly.
12. Avoid unnecessary complexity, external databases, model API costs, authentication systems, or premature microservices.
13. For each phase, summarize files created, design decisions, what was tested, what remains, and the commands I should run.
14. Do not generate hundreds of artificial "human evaluations" just to reach a target count. Create a small demo dataset, then prepare an annotation workflow for me to build the genuine benchmark.
15. Ask me for an API provider/key **only when** we reach the optional model judge phase; make API calls explicitly opt-in.

### Definition of done for the first coding session

- A `pip install -e '.[dev]'` from the repository root works.
- `ai-eval validate --data-dir data/examples` validates the committed examples.
- `ai-eval report --data-dir data/examples --output-dir reports` produces genuine summary files.
- `ai-eval compare --data-dir data/examples` shows recorded human example preferences.
- `python -m pytest` and `ruff check .` pass when run in an available environment.
- The example reports clearly distinguish synthetic demonstrations from a genuine benchmark.
- A developer can understand and repeat the entire process using the project documentation.

**Begin with the Phase 1 repository structure and implementation. Do not report features, test results, or dataset statistics that have not actually been produced.**
