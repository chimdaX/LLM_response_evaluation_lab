# Roadmap

This document records what has been built, what is planned next, and the design intent for
optional extensions. Milestone targets are goals, not results. No dataset counts, agreement
values, error rates, or CI results are reported here until they actually exist.

## Status at a glance

| Phase | Status |
|---|---|
| 1. Foundation | **Complete** (v0.1.0) |
| 2. Evaluation workflow | Partly complete: reporting, pairwise handling, and taxonomy were delivered in Phase 1; the annotation guide and the genuine benchmark are pending |
| 3. GitHub-ready release | Not started (MIT license added) |
| 4. Research extension | Not started |

## Phase 1: Foundation (complete)

- [x] Python package, `pyproject.toml`, `src/` layout, and dev dependencies (pytest, Ruff).
- [x] Rubric v1.0 with score anchors for each dimension (`rubrics/rubric_v1.md`).
- [x] Typed schemas for prompts, responses, evaluations, and preferences.
- [x] Record-level and cross-file validation, including a heuristic secret/PII scan.
- [x] Deterministic weighted scoring with null handling and review flags.
- [x] Five clearly labelled synthetic demonstration prompts with ten responses.
- [x] CLI commands `validate`, `score`, `compare`, `report`, with unit and CLI tests.

## Phase 2: Evaluation workflow

- [x] Error taxonomy and evidence tracking. *(Delivered in Phase 1.)*
- [x] Pairwise preference handling. *(First version delivered in Phase 1.)*
- [x] CSV, JSON, and Markdown reporting. *(First version delivered in Phase 1.)*
- [ ] Annotation guide (`docs/annotation_guide.md`): a step-by-step reviewer workflow, a record
      template, and worked edge cases.
- [ ] Methodology notes: sampling of prompts, the reviewer consistency check, and the rubric
      revision log.
- [ ] Manually review the first 20 benchmark items into `data/benchmark/`, each with
      `annotation_source: "human"` and genuine sources. These must be real reviews; artificial
      "human evaluations" will not be generated to reach a target count.

## Phase 3: GitHub-ready release

- [ ] GitHub Actions workflow, run on pushes and pull requests to `main`:
  1. check out the repository and set up a supported Python version;
  2. install the package with dev dependencies;
  3. run `ruff check .` and `python -m pytest`;
  4. run `ai-eval validate --data-dir data/examples`;
  5. generate reports into a temporary directory as a smoke test;
  6. optionally upload the generated reports as build artifacts.
- [ ] An example CLI transcript built from real computed output.
- [ ] Screenshots or charts, added only once they exist.
- [x] LICENSE (MIT).
- [ ] Contribution guidance.
- [ ] Tag an initial release.

CI should fail on invalid inputs, broken tests, or lint errors. It should **not** fail on human
quality-score thresholds until a stable, explicitly versioned benchmark and decision policy
exist. Any later regression thresholds must use a documented baseline and explain each threshold.

## Phase 4: Research extension

- [ ] Grow the manually reviewed benchmark toward 100–200 prompts, only as fast as review quality
      allows, across the [evaluation domains](specification.md#3-evaluation-domains).
- [ ] Optional LLM judge and human-agreement analysis (see below).
- [ ] Study disagreement patterns and candidate-order bias.
- [ ] Optional dashboard (e.g. Streamlit) or Docker image.

## Milestones

| Milestone | Deliverable | Acceptance criteria | Status |
|---|---|---|---|
| M1: Foundation | Structure, rubric, schemas, CLI | Valid example input produces a deterministic result | Done |
| M2: Human evaluation | Annotation workflow and benchmark | At least 20 genuinely reviewed items with rationales | Pending |
| M3: Reporting | CSV, JSON, Markdown outputs | Reports accurately summarize valid scored examples | Done (first version) |
| M4: Comparisons | Pairwise preference workflow | A/B/tie decisions with reasons; position labels not treated as quality evidence | Done (first version) |
| M5: Quality engineering | Tests, lint, GitHub Actions | All automated checks pass on a clean clone in CI | Tests and lint done; CI pending |
| M6: Expanded dataset | Multiple domains and error types | 100–200 prompts as review quality allows | Pending |
| M7: Optional AI judge | Provider-neutral judge interface | Human agreement and disagreement analysis, excluding failed calls | Pending |

## Optional extension: LLM-as-a-judge

Planned only after a human-labelled benchmark exists. Design requirements:

- **Opt-in only.** It runs only when explicitly requested and credentials are configured. The
  offline, API-free workflow must keep working without it.
- **Provider-neutral interface.** The judge receives the same prompt, candidate responses, and
  rubric definition as a human reviewer.
- **Structured output.** The judge returns scores and rationales, which are validated against
  the same schema. The design must handle malformed outputs, retries, rate limits, and API
  failures.
- **Logging.** Record the provider, model identifier, judge prompt version, timestamp, and
  inference settings.
- **Agreement analysis.** Compare judge scores with human scores using MAE per dimension and
  rank/preference agreement. Exclude failed calls from these calculations, but report their count.
- **Bias checks.** Test position sensitivity by swapping candidate order. Look for length and
  verbosity bias.
- **Provenance.** Model-produced rationales are labelled separately from externally verified
  evidence and are never stored as human annotations.
- **Secrets.** Keep secrets in environment variables or CI secrets, never in git. Add a
  `.env.example` with placeholder names; `.env` is already in `.gitignore`.

## Other optional extensions

- Blind A/B order randomization for pairwise review.
- Multiple reviewers, with inter-rater reliability (e.g. weighted Cohen's kappa for ordinal
  scores, preference agreement for pairwise decisions).
- Objective automated checks, such as word or bullet counts, reported separately from human
  judgments.
- Docker support.

## Development principles

These apply to every phase:

1. Keep the core workflow fully functional offline. Add no paid API, external database, or
   service as a requirement.
2. Keep dependencies small.
3. Compute every number in reports and documentation from real input data. Never publish
   invented metrics, dataset sizes, or CI results.
4. Keep synthetic examples clearly labelled. Never attribute text to a real model unless it
   genuinely came from that model and its provenance is recorded.
5. Write real tests that cover failure cases as well as normal operation.
6. Update the README's *Current functionality* section and this roadmap whenever a phase lands.

## Before presenting the project

Once the benchmark exists, the README should be updated with:

- the real dataset size and the number of genuinely human-reviewed items;
- actual CI status;
- sample analyses and failure cases, with verified evidence;
- a discussion of difficult evaluator decisions and remaining limitations.
