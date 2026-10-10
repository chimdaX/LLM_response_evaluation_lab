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
- [Drafts, interruptions and mistakes](#drafts-interruptions-and-mistakes)
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
   for a rubric reminder) and a rationale (required, including for `n`);
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

# Deliberate consistency re-review of a response you already evaluated (creates a new record)
ai-eval annotate --data-dir data/benchmark --reviewer-id reviewer_01 --response-id B003-B --repeat
```

Without `--repeat`, a second evaluation of the same response by the same reviewer is refused.

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

## Drafts, interruptions and mistakes

- **Interruptions.** Ctrl+C, closing the terminal, or `q` at the save prompt keeps a draft
  in `data/benchmark/.drafts/`. Run the same command again to resume where you stopped.
  Drafts are working files: validation and reports ignore them.
- **Abandoning a draft.** Delete its file from `.drafts/`. `status` lists drafts in progress.
- **A mistake in a saved record.** The tools never edit saved records. Fix it by hand in
  the JSON file, keeping the IDs unchanged. Then run `ai-eval validate`, and describe the
  correction in your commit message so the change is traceable.
- **A mistake in a prompt's reference notes.** Correct the note in `prompts.json` and
  mention it in the commit message. If the change could have affected evaluations already
  saved, re-check those evaluations.

## What to commit

Commit `prompts.json`, `responses.json`, `evaluations.json`, and `preferences.json` as you
go. Small, frequent commits (e.g. one per session) give a clear audit trail.
`raw_responses/` and `.drafts/` are git-ignored.

Check the provider's terms of use before publishing model outputs in a public repository;
most permit it, but it is your responsibility to confirm.
