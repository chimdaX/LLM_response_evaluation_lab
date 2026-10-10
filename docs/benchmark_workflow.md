# Benchmark Workflow

This document explains how to build the human-reviewed benchmark in
[`data/benchmark/`](../data/benchmark/):

1. collect authentic AI responses;
2. evaluate each response against the rubric;
3. record pairwise preferences;
4. track progress and generate reports.

Everything runs locally. No paid API or network access is needed by the tool; you collect
responses through whatever chat interface or model you already use.

For *how to judge* responses, see [`annotation_guide.md`](annotation_guide.md).

## Contents

- [Data separation and integrity](#data-separation-and-integrity)
- [Benchmark layout](#benchmark-layout)
- [Step 1: Collect responses](#step-1-collect-responses)
- [Step 2: Evaluate responses](#step-2-evaluate-responses)
- [Step 3: Record pairwise preferences](#step-3-record-pairwise-preferences)
- [Step 4: Track progress and report](#step-4-track-progress-and-report)
- [Manual templates (alternative)](#manual-templates-alternative)
- [Drafts and interruptions](#drafts-and-interruptions)
- [Correcting a saved evaluation](#correcting-a-saved-evaluation)
- [Other mistakes](#other-mistakes)
- [What to commit](#what-to-commit)

---

## Data separation and integrity

| Directory | Contains | Provenance |
|---|---|---|
| `data/examples/` | Hand-written demonstration data | `synthetic_example` responses, `illustrative_example` annotations |
| `data/benchmark/` | The genuine benchmark | `model_output` responses, `human` annotations |

Rules enforced by the tools:

- Imported responses always have provenance `model_output` and must record the model
  name, provider, collection method, and generation date. The name `example-only` is
  rejected for real outputs, and future dates are rejected.
- Annotations created with `annotate` / `annotate-pair` are marked `human`, and only after
  you confirm that the judgments are your own.
- Records are **append-only**. No command edits or deletes an existing response,
  evaluation, or preference. Re-importing a filled slot is refused.
- `ai-eval status` reports progress counts only. Reports on a partly annotated benchmark
  carry an **Incomplete annotation** banner.

Rules you must follow:

- Never paste AI-generated scores, rationales, or error labels into an evaluation.
- Never edit a model's response before importing it; paste the complete first response.
- Never invent metadata. If something is unknown (e.g. temperature in a chat interface),
  leave it blank.

## Benchmark layout

```text
data/benchmark/
├── prompts.json        # 20 prompts (B001–B020), with reference notes and objectives
├── responses.json      # collected model responses (starts empty)
├── evaluations.json    # human evaluations (starts empty)
├── preferences.json    # human A/B/tie decisions (starts empty)
├── raw_responses/      # paste area for response text (git-ignored; created by `collect`)
└── .drafts/            # in-progress annotations (git-ignored; created by `annotate`)
```

Each prompt has two candidate slots: `<prompt_id>-A` and `<prompt_id>-B` (e.g. `B007-A`).
That makes 40 response slots, 40 evaluations (one per response per reviewer), and 20
pairwise decisions.

| ID | Pattern | Assigned by |
|---|---|---|
| Prompt | `B001`–`B020` | Fixed |
| Response | `B001-A`, `B001-B` | `collect` |
| Evaluation | `EV0001`, `EV0002`, ... | `annotate` (next free number) |
| Preference | `PF0001`, `PF0002`, ... | `annotate-pair` (next free number) |

## Step 1: Collect responses

### Choosing models

Choose two models you can access (free tiers are fine), e.g. ChatGPT, Claude, Gemini,
Microsoft Copilot, or a local model via Ollama or LM Studio.

Decide which model fills slot A and which fills slot B **before** you start, and alternate
the assignment between prompts. For example: model 1 is A for odd-numbered prompts and B
for even-numbered ones. This keeps "A" and "B" from always meaning the same model, which
reduces position and brand effects in the pairwise comparison. Write the assignment down;
the tool records the model for every response, so it can always be audited later.

### Collection protocol

For every slot:

1. Open a **new chat** (no earlier conversation in context).
2. Turn off custom instructions, memory, and personalization if the interface has them,
   or note in *generation settings* that they were on.
3. Do not enable web search or tools unless you do so consistently for every prompt, and
   record it in *generation settings*.
4. Paste the prompt **exactly** as `collect` displays it.
5. Take the **first** complete response. Don't regenerate, edit, or pick the best of
   several (cherry-picking biases the benchmark).
6. Copy the whole response (most interfaces have a copy button that preserves Markdown).

### Importing interactively (recommended)

```bash
ai-eval collect --data-dir data/benchmark
```

For each pending slot, the tool:

1. shows the prompt between `BEGIN PROMPT` / `END PROMPT` markers for you to copy;
2. creates an empty file `data/benchmark/raw_responses/<slot>.txt` and waits while you
   paste the response into it and save (type `skip` to leave the slot for later);
3. asks for metadata:

   | Field | What to enter |
   |---|---|
   | Model name | Exactly what the interface shows (e.g. the model picker label). If no version is shown, write the product name and "(version not shown)". |
   | Provider / product | e.g. `OpenAI ChatGPT`, `Anthropic Claude.ai`, `Google Gemini`, `Ollama (local)` |
   | Collection method | `web_chat`, `api`, `local_model`, or `other` |
   | Date generated | Defaults to today; future dates are rejected |
   | Generation settings | Only what you know, e.g. `new chat; memory off; web search off`. Leave blank if unknown. |

4. shows a preview and imports the response only after you confirm.

Model metadata is **never** carried over between slots, so you cannot accidentally label
model 2's answer with model 1's name.

To work on one prompt or slot only:

```bash
ai-eval collect --data-dir data/benchmark --prompt-id B005
ai-eval collect --data-dir data/benchmark --prompt-id B005 --label B
```

### Importing a single file non-interactively

```bash
ai-eval collect --data-dir data/benchmark --prompt-id B001 --label A \
  --model-name "<model name as shown>" --provider "<provider>" --method web_chat \
  --generated-at 2026-10-12 --text-file path/to/response.txt
```

All metadata flags are required in this mode. `--settings "..."` is optional. (In
PowerShell, replace the trailing `\` line continuations with backticks, or put the command
on one line.)

### Checks performed on import

- The prompt exists, and the slot (`A`/`B`) is still empty.
- The text is non-empty. Line endings are normalized and surrounding whitespace is
  trimmed; the body is otherwise stored verbatim.
- The generation date is not in the future.
- The text does not contain likely secrets or personal email addresses (heuristic scan).
  If it does, remove them from the text file and retry.
- The record validates against schema 1.1 before being appended.

## Step 2: Evaluate responses

```bash
ai-eval annotate --data-dir data/benchmark --reviewer-id reviewer_01
```

Use the same reviewer ID every time. Each session:

1. asks you to confirm that your judgments are your own (records are marked `human`);
2. takes responses in order, putting any with an unfinished draft first;
3. shows the prompt, its constraints and evaluation objectives, then waits for Enter
   before revealing the response. **Model and provider names are hidden.**
4. shows the reference notes as a starting point for verification;
5. for each of the seven dimensions, asks for a score (`1`–`5`, `n` for not assessed, `?`
   for a rubric reminder) and a rationale (required, including for `n`). Rationales are
   checked as you type (see [Rationale checks](#rationale-checks));
6. lets you add error labels, each with an evidence status, a note, and a source (the
   source is required when the status is `verified`); type `?` to list the taxonomy;
7. asks for an overall rationale and an optional improved response (multi-line, finish
   with a line containing only `.`);
8. shows a summary with consistency checks (e.g. "accuracy is 1 but no factual error is
   labelled"), then lets you **s**ave, **e**dit an item, or **q**uit and keep the draft.

Useful options:

```bash
# Evaluate one specific response
ai-eval annotate --data-dir data/benchmark --reviewer-id reviewer_01 --response-id B003-B

# Correct one of your saved evaluations (see "Correcting a saved evaluation")
ai-eval annotate --data-dir data/benchmark --reviewer-id reviewer_01 --revise EV0001

# Deliberate consistency re-review of a response you already evaluated
ai-eval annotate --data-dir data/benchmark --reviewer-id reviewer_01 --response-id B003-B --repeat
```

Without `--revise` or `--repeat`, a second evaluation of the same response by the same reviewer
is refused, and the error message names the existing evaluation.

A **consistency re-review** (`--repeat`) is a blind second review: your earlier evaluation is
not shown. It is saved with `consistency_check_of` pointing at your current evaluation, and kept
for measuring your own consistency. It is **not** scored or counted, so it cannot double-count.
Use `--revise`, not `--repeat`, to fix a mistake.

### Rationale checks

The checks look at *content*, not length. A short rationale such as "Omits the 2100
exception." is fine; a long one such as "Overall the response is pretty good and quite clear"
is not.

| Problem | Example | What happens |
|---|---|---|
| Only a number or rating | `4`, `4/5`, `score: 4` | Refused; you are asked again |
| Placeholder | `n/a`, `ok`, `fine`, `same as above`, `tbd` | Refused; you are asked again |
| No specific content | "The model output is okay", "Correct." | Warning; keep it only by confirming |
| Same text for three or more dimensions | "4" pasted everywhere | Shown as a CHECK in the summary |

"No specific content" means that, after ignoring common words ("the", "is") and generic
judgment words ("good", "okay", "clear", "response", "accuracy"), fewer than two meaningful
words remain. Passing the checks does not prove a rationale is good. It only rules out obvious
non-explanations, so the [annotation guide](annotation_guide.md#13-writing-defensible-rationales)
still applies.

`ai-eval validate` runs the same checks on saved records and reports them as **warnings**.
Existing records are never rejected or changed because of them. `validate --strict` treats
them as failures, and the report's summary counts evaluations with rationale warnings.

## Step 3: Record pairwise preferences

After both candidates for a prompt have been evaluated individually:

```bash
ai-eval annotate-pair --data-dir data/benchmark --reviewer-id reviewer_01
ai-eval annotate-pair --data-dir data/benchmark --reviewer-id reviewer_01 --prompt-id B007
```

The tool shows the prompt and both responses (model names hidden), then asks for `a`, `b`,
or `t` (tie) and a reason naming the decisive difference. It reminds you if you have not yet
evaluated the two responses individually.

## Step 4: Track progress and report

```bash
ai-eval status   --data-dir data/benchmark
ai-eval validate --data-dir data/benchmark
ai-eval score    --data-dir data/benchmark
ai-eval compare  --data-dir data/benchmark
ai-eval report   --data-dir data/benchmark --output-dir reports/benchmark
```

`status` shows collected responses (of 40), responses with a human evaluation, pairs with a
human preference, pending IDs, and drafts in progress. It ends with `INCOMPLETE` or
`COMPLETE`.

`validate` warns about prompts with no responses yet. These warnings are expected during
collection.

Treat any report produced before `status` says `COMPLETE` as a progress check, not a
result. The report says so itself with an **Incomplete annotation** banner.

## Manual templates (alternative)

If you prefer editing JSON directly, [`templates/`](../templates/) contains:

| Template | Append to |
|---|---|
| `response_template.json` | `data/benchmark/responses.json` |
| `evaluation_template.json` | `data/benchmark/evaluations.json` |
| `preference_template.json` | `data/benchmark/preferences.json` |

Copy a template into the JSON array of the target file and replace every `<...>`
placeholder and empty string. Then run `ai-eval validate --data-dir data/benchmark`.

An unfilled template fails validation (placeholder IDs, empty rationales, and an invalid
date are all rejected), so an incomplete record cannot pass as finished. The interactive
tools are safer because they validate as you go and never rewrite earlier records.

## Drafts and interruptions

- **Interruptions.** Ctrl+C, closing the terminal, or `q` at the save prompt keeps a draft
  in `data/benchmark/.drafts/`. Run the same command again to resume where you stopped.
  This also applies to revisions. Drafts are working files: validation and reports ignore
  them.
- **Abandoning a draft.** Delete its file from `.drafts/`. `status` lists drafts in progress.

## Correcting a saved evaluation

Saved evaluations are never edited or deleted. A correction is a **new record that supersedes
the old one**, and the old record stays in `evaluations.json` as revision history.

```bash
ai-eval annotate --data-dir data/benchmark --reviewer-id reviewer_01 --revise EV0001
```

The tool:

1. shows the revision history (e.g. `EV0001`) and lists any problems found in the original,
   such as score-only rationales;
2. asks for a **revision reason**: what was wrong with the original;
3. shows the prompt and response again, then goes through every dimension, showing the
   original score and rationale:
   - **Enter keeps the original score.** Nothing changes unless you change it, and you
     confirm every dimension.
   - The original rationale is offered as the default **only if it passes the rationale
     checks**. Flagged rationales (like `"4"`) must be rewritten.
4. offers to keep the original error labels, lets you add more, then asks for the overall
   rationale (same rules as above);
5. shows a summary with every changed score marked `(was N)`, then saves the new record, e.g.
   `EV0002` with `"supersedes": "EV0001"` and your `revision_reason`.

### Revision chains

You can correct a correction: `--revise EV0002` creates `EV0003`, which supersedes `EV0002`.
The history is always a single line, `EV0001 -> EV0002 -> EV0003`. To keep it that way:

- only the **latest** version can be revised (`--revise EV0001` after `EV0002` exists is
  refused);
- only the **original reviewer** can revise an evaluation;
- `validate` rejects branching (two records superseding the same one), cycles, references to
  unknown evaluations or to a different response or reviewer, a correction dated before the
  record it replaces, and more than one *active* evaluation per reviewer and response.

### What counts after a correction

Only the **active** version (the latest in each chain) is used by `score`, `compare`, `report`,
and `status`. Superseded versions and consistency re-reviews remain in the data, are excluded
from every count and aggregate, and are summarized in the report's **Revision history** banner
and in the JSON metadata (`revision_history`). The CSV's `supersedes` column links each active
evaluation to the record it replaced.

### Procedure

1. `ai-eval validate --data-dir data/benchmark` lists the rationale warnings to fix.
2. Run `annotate --revise <ID>` for each affected evaluation, and give a specific revision
   reason.
3. `ai-eval validate` again: the warnings for superseded records disappear.
4. Commit `evaluations.json` with a message naming the corrected IDs, e.g.
   `data: revise EV0001 (score-only rationales)`.

Do not hand-edit saved evaluations. A hand edit erases the original from the data and can
only be traced through git history.

## Other mistakes

- **A mistake in a prompt's reference notes.** Correct the note in `prompts.json` and
  mention it in the commit message. If the change could have affected evaluations already
  saved, re-check those evaluations.

## What to commit

Commit `prompts.json`, `responses.json`, `evaluations.json`, and `preferences.json` as you
go. Small, frequent commits (e.g. one per session) give a clear audit trail.
`raw_responses/` and `.drafts/` are git-ignored.

Check the provider's terms of use before publishing model outputs in a public repository;
most permit it, but it is your responsibility to confirm.
