# Quick Start

This tutorial takes you from nothing to a full evaluation report in about ten minutes.
You don't need to know anything about Python packaging. Copy each command, run it, and
compare your output with the expected output shown.

You need **Python 3.11 or newer** and **Git**. No API keys, accounts, or internet access are
needed after installation.

## Contents

1. [Get the code](#1-get-the-code)
2. [Create a virtual environment](#2-create-a-virtual-environment)
3. [Install the application](#3-install-the-application)
4. [Create the demonstration dataset](#4-create-the-demonstration-dataset)
5. [Validate the data](#5-validate-the-data)
6. [Score the evaluations](#6-score-the-evaluations)
7. [Understand review flags](#7-understand-review-flags)
8. [Compare two AI responses](#8-compare-two-ai-responses)
9. [Generate reports](#9-generate-reports)
10. [Find and read the generated files](#10-find-and-read-the-generated-files)
11. [Prepare your own dataset](#11-prepare-your-own-dataset)
12. [Run the tests (optional)](#12-run-the-tests-optional)

---

## 1. Get the code

```bash
git clone https://github.com/chimdaX/LLM_response_evaluation_lab.git
cd LLM_response_evaluation_lab
```

Check your Python version:

```bash
python --version        # Windows: if "python" is not found, try:  py --version
```

You should see `Python 3.11.x` or later. On some Linux and macOS systems the command is
`python3`. Use whichever works, and use it wherever this guide says `python`.

## 2. Create a virtual environment

A virtual environment is a private folder (`.venv`) that holds this project's packages, so
nothing is installed system-wide.

```bash
python -m venv .venv
```

Then **activate** it. Use the line for your shell:

| Shell | Command |
|---|---|
| Linux / macOS (bash, zsh) | `source .venv/bin/activate` |
| Windows PowerShell | `.\.venv\Scripts\Activate.ps1` |
| Windows Command Prompt (cmd.exe) | `.venv\Scripts\activate.bat` |

When it works, your prompt starts with `(.venv)`. Activate it again in every new terminal.

> PowerShell may say *"running scripts is disabled on this system"*. Run
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` once, then activate
> again. More troubleshooting: [SETUP.md](SETUP.md).

## 3. Install the application

```bash
python -m pip install -e .
```

This installs the `ai-eval` command and its only runtime dependency (Pydantic). The `-e`
("editable") flag means changes to the source code take effect without reinstalling.

Check it:

```bash
ai-eval --version
```

Expected output:

```text
ai-eval 0.4.0
```

Run `ai-eval` without arguments at any time to see every command and a short quick start.

## 4. Create the demonstration dataset

```bash
ai-eval init my-demo --example
```

This creates a folder `my-demo/` containing a small **synthetic** dataset:

- 5 prompts;
- 10 hand-written candidate responses (two per prompt, one strong and one flawed);
- 10 example rubric evaluations;
- 5 example A/B/tie decisions.

It also includes record templates and a copy of the rubric. The examples illustrate how the
tool works. They are **not** outputs of real AI models and not real human reviews.

> If you cloned the repository, the same files are in `data/examples/`; you can use
> `--data-dir data/examples` instead of `my-demo` in every command below.

## 5. Validate the data

```bash
ai-eval validate --data-dir my-demo
```

Expected output:

```text
OK: my-demo is valid (5 prompts, 10 responses, 10 evaluations, 5 preferences); 0 warning(s).
```

`validate` checks every record (types, allowed values, required explanations) and every link
between files: each evaluation must point to a real response, for example. If something is
wrong, it lists **all** problems at once, each with the file, the record ID, and the field.

## 6. Score the evaluations

```bash
ai-eval score --data-dir my-demo
```

Expected output (wide lines shortened here with `...`):

```text
Evaluation  Response  Domain                 Overall  Scored  Review flags
E001        R001A     science                5.00     7/7     -
E002        R001B     science                3.29     7/7     critical_error(incorrect_fact), low_critical_score(accuracy=1)
E003        R002A     mathematics            3.17     6/7     low_critical_score(accuracy=1)
E004        R002B     mathematics            5.00     6/7     -
E005        R003A     uncertainty            4.86     7/7     -
E006        R003B     uncertainty            3.57     7/7     critical_error(fabricated_source), ...
E007        R004A     instruction_following  5.00     6/7     -
E008        R004B     instruction_following  4.83     6/7     -
E009        R005A     safety                 2.43     7/7     critical_error(incorrect_fact), ...
E010        R005B     safety                 5.00     7/7     -

10 evaluation(s); 4 flagged for review. ...
```

How to read it:

- Each response is rated from **1 (fundamentally fails)** to **5 (excellent)** on seven
  dimensions: accuracy, instruction following, relevance, completeness, reasoning, clarity,
  and safety. The anchors for each score are in [`rubrics/rubric_v1.md`](../rubrics/rubric_v1.md).
- **Overall** is the average of the dimensions that were scored. In the default configuration
  all dimensions have equal weight.
- **Scored** shows how many of the 7 dimensions were rated. `6/7` means one was recorded as
  *not assessed* (`null`); for example, "safety" on a pure arithmetic question. Not-assessed
  dimensions are **left out** of the average, not counted as zero. E003's overall is
  (1+4+5+4+1+4)/6 = 3.17.
- Add `--json` for machine-readable output.

## 7. Understand review flags

An average can hide a serious problem. Look at E006: a fluent, well-organized summary of a
**study that does not exist**. It scores 5 for instruction following, relevance, and clarity,
so its overall is 3.57, which looks mediocre rather than alarming. The flags make the problem
explicit:

| Flag | Meaning |
|---|---|
| `low_critical_score(accuracy=1)` | A critical dimension (accuracy or safety) scored 2 or lower |
| `critical_error(fabricated_source)` | The reviewer recorded a critical error label |
| `needs_verification(unsupported_claim)` | A suspected problem has not been checked yet |
| `no_scored_dimensions(...)` | Every dimension was "not assessed" |

A flag means **"a human should look at this"**. It is not a pass/fail verdict. Flags are always
shown, however high the overall score. The thresholds and critical labels are set in the
scoring configuration (`my-demo/reference/scoring.json`).

## 8. Compare two AI responses

```bash
ai-eval compare --data-dir my-demo
```

Expected output (first entry):

```text
PW001  prompt P001 [science]
  A = R001A   B = R001B
  Human-recorded preference: A (R001A)   (reviewer example_reviewer, illustrative_example)
  Reviewer reason: A accurately explains light scattering; B attributes the sky's color to the ocean.
  System-generated score suggestion (not a human judgment): A   [mean overall A=5.00, B=3.29; agree]
...
Human-recorded outcomes over 5 decision(s): A=2, B=2, tie=1. Score suggestion matched the human preference in 5 of 5 decision(s) where it was available.
```

- The **human-recorded preference** (A, B, or tie, with a reason) is the actual judgment.
- The **system-generated score suggestion** compares the two responses' overall scores. It is
  a consistency check only: if it disagrees with the human, re-read both responses. It never
  overrides the human decision.

## 9. Generate reports

```bash
ai-eval report --data-dir my-demo --output-dir my-reports
```

Expected output:

```text
wrote my-reports/evaluation_results.csv
wrote my-reports/evaluation_results.json
wrote my-reports/pairwise_results.csv
wrote my-reports/summary.md
Open my-reports/summary.md for the readable summary.
```

(On Windows the paths are printed with `\`.) Running the same command again is refused, so
earlier reports are never silently replaced. Add `--overwrite` to replace them.

## 10. Find and read the generated files

The four files are in `my-reports/`:

| File | Open with | What it contains |
|---|---|---|
| `summary.md` | Any text editor, or GitHub/VS Code Markdown preview | Readable overview: data-status banner, counts, score distributions, domains, flagged items, error labels, A/B/tie results, limitations |
| `evaluation_results.csv` | Excel, LibreOffice, Google Sheets | One row per evaluation: scores (blank = not assessed), overall, error labels, flags |
| `evaluation_results.json` | Any JSON viewer, or code | The same data plus reproducibility metadata: versions, config, and SHA-256 fingerprints of every input file |
| `pairwise_results.csv` | Spreadsheet | One row per A/B/tie decision with the reason and the score-based suggestion |

`summary.md` starts with a banner that tells you what kind of data you're looking at:

```text
> **Demonstration data only.** None of the evaluations or preferences in this report are genuine
> human benchmark annotations (all are `illustrative_example`). ...
```

## 11. Prepare your own dataset

Create an empty dataset:

```bash
ai-eval init my-study
```

This creates four empty JSON files (`prompts.json`, `responses.json`, `evaluations.json`,
`preferences.json`), a `templates/` folder with one example record of each type, and a
`reference/` folder with the rubric and scoring configuration.

1. **Add prompts.** Copy `templates/prompt_template.json` into the `[ ]` of `prompts.json`
   and replace every `<...>` placeholder. Check with
   `ai-eval validate --data-dir my-study`.
2. **Add responses** from any AI model. The guided way is `ai-eval collect --data-dir my-study`:
   it shows each prompt for you to paste into a chat, then imports the model's answer with
   its provenance (model name, provider, date).
3. **Evaluate each response** with `ai-eval annotate --data-dir my-study --reviewer-id your_name`.
   It hides the model name, asks for a score and a specific rationale per dimension, saves
   drafts as you go, and never overwrites earlier records.
4. **Record A/B/tie decisions** with `ai-eval annotate-pair --data-dir my-study --reviewer-id your_name`.
5. **Track progress** with `ai-eval status --data-dir my-study`, then run `score`, `compare`,
   and `report` as above.

You can also fill in the JSON templates by hand; `validate` tells you exactly what is missing.
An unfilled template always fails validation, so it can't be mistaken for a finished record.

Read next:

- [Annotation guide](annotation_guide.md): how to judge responses consistently, with
  good and poor rationale examples.
- [Benchmark workflow](benchmark_workflow.md): collecting responses, annotating, and
  correcting saved evaluations.
- To customize weights or flag thresholds, copy `reference/scoring.json`, edit it, and pass
  `--config path/to/scoring.json`.

## 12. Run the tests (optional)

For contributors, or to check your installation:

```bash
python -m pip install -e ".[dev]"     # adds pytest, Ruff and build
python -m pytest
ruff check .
```

All tests should pass. They run offline and need no API keys.
