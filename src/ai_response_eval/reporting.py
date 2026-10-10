"""Generate CSV, JSON and Markdown reports computed from validated input records.

Reports are built in memory first (``build_reports``) and written separately
(``write_reports``). That split keeps report content a pure function of its
inputs -- easy to test and byte-for-byte reproducible for a fixed
``generated_at`` -- and keeps file-system safety rules in one place.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean, median
from typing import Any

from ai_response_eval import __version__
from ai_response_eval.comparisons import PairwiseRow, summarize_pairwise
from ai_response_eval.rubric import (
    DIMENSIONS,
    LABEL_TO_CATEGORY,
    RUBRIC_VERSION,
    SCHEMA_VERSION,
    SCORE_MAX,
    SCORE_MIN,
)
from ai_response_eval.scoring import ScoredEvaluation, ScoringConfig, format_score
from ai_response_eval.validation import Dataset

REPORT_FILES = (
    "evaluation_results.csv",
    "evaluation_results.json",
    "pairwise_results.csv",
    "summary.md",
)
SMALL_SAMPLE_THRESHOLD = 30


@dataclass(frozen=True)
class ReportInputs:
    dataset: Dataset
    scored: list[ScoredEvaluation]
    pairwise: list[PairwiseRow]
    config: ScoringConfig
    input_files: dict[str, Path]
    config_path: Path
    rubric_path: Path | None
    generated_at: datetime


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pct(numerator: int, denominator: int) -> str:
    return "n/a" if denominator == 0 else f"{100 * numerator / denominator:.1f}%"


def _counts(inputs: ReportInputs) -> dict[str, int]:
    d = inputs.dataset
    return {
        "prompts": len(d.prompts),
        "candidate_responses": len(d.responses),
        "evaluation_records": len(d.evaluations),
        "scored_evaluations": sum(s.overall is not None for s in inputs.scored),
        "reviewers": len(
            {e.reviewer_id for e in d.evaluations} | {p.reviewer_id for p in d.preferences}
        ),
        "pairwise_decisions": len(d.preferences),
    }


def _completeness(dataset: Dataset) -> dict[str, int]:
    evaluated = {e.response_id for e in dataset.evaluations}
    answered = {r.prompt_id for r in dataset.responses}
    return {
        "responses_without_evaluation": sum(
            r.response_id not in evaluated for r in dataset.responses
        ),
        "prompts_without_responses": sum(p.prompt_id not in answered for p in dataset.prompts),
    }


def _provenance(dataset: Dataset) -> dict[str, dict[str, int]]:
    return {
        "responses_by_provenance": dict(
            sorted(Counter(r.provenance for r in dataset.responses).items())
        ),
        "evaluations_by_annotation_source": dict(
            sorted(Counter(e.annotation_source for e in dataset.evaluations).items())
        ),
        "preferences_by_annotation_source": dict(
            sorted(Counter(p.annotation_source for p in dataset.preferences).items())
        ),
    }


def _genuine_human_counts(dataset: Dataset) -> tuple[int, int]:
    return (
        sum(e.annotation_source == "human" for e in dataset.evaluations),
        sum(p.annotation_source == "human" for p in dataset.preferences),
    )


def _csv_text(header: list[str], rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    # Explicit "\n" so the bytes are identical on Windows and Linux.
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def _evaluation_record(s: ScoredEvaluation) -> dict[str, Any]:
    e = s.evaluation
    return {
        "evaluation_id": e.evaluation_id,
        "prompt_id": e.prompt_id,
        "response_id": e.response_id,
        "domain": s.domain,
        "reviewer_id": e.reviewer_id,
        "annotation_source": e.annotation_source,
        "response_provenance": s.response_provenance,
        "rubric_version": e.rubric_version,
        "scores": {d: e.scores[d] for d in DIMENSIONS},
        "n_scored_dimensions": s.n_scored,
        "overall": s.overall,
        "error_labels": list(e.error_labels),
        "review_flags": [{"code": f.code, "detail": f.detail} for f in s.flags],
        "needs_review": s.needs_review,
    }


def evaluation_results_csv(inputs: ReportInputs) -> str:
    header = [
        "evaluation_id", "prompt_id", "response_id", "domain", "reviewer_id",
        "annotation_source", "response_provenance", *DIMENSIONS,
        "n_scored_dimensions", "overall", "error_labels", "review_flags", "needs_review",
    ]  # fmt: skip
    rows = []
    for s in inputs.scored:
        e = s.evaluation
        rows.append(
            [
                e.evaluation_id, e.prompt_id, e.response_id, s.domain, e.reviewer_id,
                e.annotation_source, s.response_provenance,
                # Null (not assessed) is written as an empty cell, never as 0.
                *("" if e.scores[d] is None else e.scores[d] for d in DIMENSIONS),
                s.n_scored,
                "" if s.overall is None else repr(s.overall),  # full precision for machines
                ";".join(e.error_labels),
                ";".join(str(f) for f in s.flags),
                str(s.needs_review).lower(),
            ]
        )  # fmt: skip
    return _csv_text(header, rows)


def pairwise_results_csv(inputs: ReportInputs) -> str:
    header = [
        "preference_id", "prompt_id", "domain", "response_a_id", "response_b_id",
        "reviewer_id", "annotation_source", "human_winner", "human_reason",
        "a_mean_overall", "b_mean_overall", "score_based_suggestion", "agreement",
    ]  # fmt: skip
    rows = []
    for r in inputs.pairwise:
        p = r.preference
        rows.append(
            [
                p.preference_id, p.prompt_id, r.domain, p.response_a_id, p.response_b_id,
                p.reviewer_id, p.annotation_source, p.winner, p.reason,
                "" if r.a_overall is None else repr(r.a_overall),
                "" if r.b_overall is None else repr(r.b_overall),
                r.score_suggestion or "", r.agreement,
            ]
        )  # fmt: skip
    return _csv_text(header, rows)


def metadata(inputs: ReportInputs) -> dict[str, Any]:
    human_evals, human_prefs = _genuine_human_counts(inputs.dataset)
    return {
        "package_version": __version__,
        "generated_at_utc": inputs.generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": SCHEMA_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "rubric_sha256": sha256_file(inputs.rubric_path),
        "scoring_config": inputs.config.model_dump(mode="json"),
        "scoring_config_sha256": sha256_file(inputs.config_path),
        "input_files_sha256": {
            path.name: sha256_file(path) for _, path in sorted(inputs.input_files.items())
        },
        "counts": _counts(inputs),
        "provenance": _provenance(inputs.dataset),
        "completeness": _completeness(inputs.dataset),
        "genuine_human_evaluations": human_evals,
        "genuine_human_preferences": human_prefs,
    }


def evaluation_results_json(inputs: ReportInputs) -> str:
    summary = summarize_pairwise(inputs.pairwise)
    document = {
        "metadata": metadata(inputs),
        "evaluations": [_evaluation_record(s) for s in inputs.scored],
        "pairwise_summary": {
            "decisions": summary.decisions,
            "a_wins": summary.a_wins,
            "b_wins": summary.b_wins,
            "ties": summary.ties,
            "decisions_with_score_suggestion": summary.with_suggestion,
            "agreements_with_score_suggestion": summary.agreements,
        },
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _md_table(header: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |" for row in rows]
    return lines


def summary_markdown(inputs: ReportInputs) -> str:
    d = inputs.dataset
    dec = inputs.config.display_decimals
    counts = _counts(inputs)
    meta = metadata(inputs)
    human_evals, human_prefs = _genuine_human_counts(d)
    synthetic_responses = sum(r.provenance == "synthetic_example" for r in d.responses)
    out: list[str] = ["# Evaluation Summary", ""]

    # --- data status banner: what this report is (and is not) evidence of --------------
    completeness = _completeness(d)
    if not d.evaluations and not d.preferences:
        out.append(
            "> **No annotations yet.** This dataset has no evaluations or pairwise decisions, "
            "so there are no results to report."
        )
    elif human_evals == 0 and human_prefs == 0:
        out.append(
            "> **Demonstration data only.** None of the evaluations or preferences in this report "
            "are genuine human benchmark annotations (all are `illustrative_example`). The numbers "
            "below show how the pipeline works; they are not findings about any AI model."
        )
    else:
        out.append(
            f"> Genuine human annotations: {human_evals} of {counts['evaluation_records']} "
            f"evaluation records and {human_prefs} of {counts['pairwise_decisions']} pairwise "
            "decisions. Other records are illustrative examples."
        )
    if synthetic_responses:
        out += [
            ">",
            f"> {synthetic_responses} of {counts['candidate_responses']} candidate responses are "
            "`synthetic_example` texts written to illustrate the framework, not real model "
            "outputs.",
        ]
    if completeness["responses_without_evaluation"] or completeness["prompts_without_responses"]:
        out += [
            ">",
            f"> **Incomplete annotation:** {completeness['responses_without_evaluation']} of "
            f"{counts['candidate_responses']} candidate responses have no evaluation and "
            f"{completeness['prompts_without_responses']} of {counts['prompts']} prompts have no "
            "responses. Aggregates describe only the annotated subset; they are not benchmark "
            "results.",
        ]
    if counts["scored_evaluations"] < SMALL_SAMPLE_THRESHOLD:
        out += [
            ">",
            f"> **Small sample:** {counts['scored_evaluations']} scored evaluations "
            f"(< {SMALL_SAMPLE_THRESHOLD}). Treat every aggregate as descriptive only.",
        ]
    out.append("")

    # --- reproducibility -------------------------------------------------------------------
    out += ["## Reproducibility", ""]
    out += _md_table(
        ["Item", "Value"],
        [
            ["Generated (UTC)", meta["generated_at_utc"]],
            ["Package version", meta["package_version"]],
            ["Rubric version", meta["rubric_version"]],
            ["Scoring config version", inputs.config.config_version],
            [
                "Rubric file SHA-256",
                f"`{meta['rubric_sha256']}`" if meta["rubric_sha256"] else "not found",
            ],
            ["Scoring config SHA-256", f"`{meta['scoring_config_sha256']}`"],
            *[
                [f"`{name}` SHA-256", f"`{digest}`"]
                for name, digest in meta["input_files_sha256"].items()
            ],
        ],
    )
    out.append("")

    # --- counts ------------------------------------------------------------------------------
    out += [
        "## Dataset counts",
        "",
        "These counts measure different things and are not interchangeable.",
        "",
    ]
    definitions = {
        "prompts": ("Prompts", "Distinct user prompts"),
        "candidate_responses": ("Candidate responses", "AI or example answers to those prompts"),
        "evaluation_records": ("Evaluation records", "Single-response rubric reviews"),
        "scored_evaluations": (
            "Scored evaluations",
            "Evaluation records with at least one non-null score",
        ),
        "reviewers": ("Reviewers", "Distinct reviewer IDs across evaluations and preferences"),
        "pairwise_decisions": ("Pairwise decisions", "A/B/tie preference records"),
    }
    out += _md_table(
        ["Measure", "Count", "Definition"],
        [[name, counts[key], definition] for key, (name, definition) in definitions.items()],
    )
    out.append("")

    # --- overall --------------------------------------------------------------------------
    overalls = [s.overall for s in inputs.scored if s.overall is not None]
    out += ["## Overall scores", ""]
    out.append(
        "Overall = weighted mean of the scored (non-null) dimensions of one evaluation, using the "
        "weights in the scoring config. Means of 1-5 ordinal ratings are convenient summaries, "
        "not interval measurements."
    )
    out.append("")
    if overalls:
        out += _md_table(
            ["n", "Mean", "Median", "Min", "Max"],
            [
                [len(overalls)]
                + [
                    format_score(v, dec)
                    for v in (fmean(overalls), median(overalls), min(overalls), max(overalls))
                ]
            ],
        )
    else:
        out.append("No scored evaluations.")
    out.append("")

    # --- per dimension ------------------------------------------------------------------
    out += ["## Scores by dimension", ""]
    out.append(
        "`n scored` is the denominator for the mean; `not assessed` (null) scores are excluded, "
        "not counted as zero."
    )
    out.append("")
    rows = []
    for dim in DIMENSIONS:
        values = [
            s.evaluation.scores[dim] for s in inputs.scored if s.evaluation.scores[dim] is not None
        ]
        dist = Counter(values)
        rows.append(
            [
                dim,
                len(values),
                len(inputs.scored) - len(values),
                format_score(fmean(values) if values else None, dec),
                " / ".join(str(dist.get(k, 0)) for k in range(SCORE_MIN, SCORE_MAX + 1)),
            ]
        )
    out += _md_table(
        ["Dimension", "n scored", "Not assessed", "Mean", "Count of 1 / 2 / 3 / 4 / 5"], rows
    )
    out.append("")

    # --- domains --------------------------------------------------------------------------
    out += ["## Domain breakdown", ""]
    by_domain: dict[str, list[ScoredEvaluation]] = defaultdict(list)
    for s in inputs.scored:
        by_domain[s.domain].append(s)
    prompts_per_domain = Counter(p.domain for p in d.prompts)
    domain_rows = []
    for domain in sorted(set(prompts_per_domain) | set(by_domain)):
        items = by_domain.get(domain, [])
        vals = [s.overall for s in items if s.overall is not None]
        domain_rows.append(
            [
                domain,
                prompts_per_domain.get(domain, 0),
                len(items),
                format_score(fmean(vals) if vals else None, dec),
                f"{sum(s.needs_review for s in items)} of {len(items)}",
            ]
        )
    if domain_rows:
        out += _md_table(
            ["Domain", "Prompts", "Evaluations", "Mean overall", "Flagged for review"], domain_rows
        )
    else:
        out.append("No prompts.")
    out.append("")

    # --- flagged items --------------------------------------------------------------------
    out += ["## Items flagged for review", ""]
    out.append(
        "Flags come from the review policy in the scoring config (low accuracy/safety scores, "
        "critical error labels, unverified claims). They are listed regardless of the overall "
        "score so that a high average cannot hide a critical failure."
    )
    out.append("")
    flagged = [s for s in inputs.scored if s.needs_review]
    if flagged:
        out += _md_table(
            ["Evaluation", "Response", "Domain", "Overall", "Flags"],
            [
                [s.evaluation.evaluation_id, s.evaluation.response_id, s.domain,
                 format_score(s.overall, dec), ", ".join(str(f) for f in s.flags)]
                for s in flagged
            ],
        )  # fmt: skip
    else:
        out.append("No evaluations were flagged.")
    out.append("")

    # --- error labels ----------------------------------------------------------------------
    out += ["## Error labels", ""]
    n_eval = counts["evaluation_records"]
    out.append(
        f"Percentages use the number of evaluation records ({n_eval}) as the denominator; a label "
        "is counted at most once per evaluation. Labels flag suspected or substantiated issues and "
        "are not proof on their own."
    )
    out.append("")
    label_counts = Counter(label for s in inputs.scored for label in s.evaluation.error_labels)
    if label_counts:
        out += _md_table(
            ["Label", "Category", "Evaluations", "% of evaluation records"],
            [
                [label, LABEL_TO_CATEGORY[label], count, _pct(count, n_eval)]
                for label, count in sorted(label_counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        )
    else:
        out.append("No error labels recorded.")
    out.append("")

    # --- pairwise ---------------------------------------------------------------------------
    summary = summarize_pairwise(inputs.pairwise)
    out += ["## Pairwise preferences", ""]
    out.append(
        f"Denominator: {summary.decisions} pairwise decisions. `A` and `B` are presentation "
        "positions, not quality labels; a skew toward one position in a small sample says nothing "
        "about the responses themselves."
    )
    out.append("")
    out += _md_table(
        ["Human-recorded outcome", "Count", "Share"],
        [
            ["A preferred", summary.a_wins, _pct(summary.a_wins, summary.decisions)],
            ["B preferred", summary.b_wins, _pct(summary.b_wins, summary.decisions)],
            ["Tie", summary.ties, _pct(summary.ties, summary.decisions)],
        ],
    )
    out.append("")
    out.append(
        f"System-generated score suggestion (tie margin {inputs.config.pairwise_tie_margin}) "
        f"available for {summary.with_suggestion} of {summary.decisions} decisions; it matched the "
        f"human preference in {summary.agreements} of {summary.with_suggestion} "
        f"({_pct(summary.agreements, summary.with_suggestion)}). This is a consistency check "
        "between two views of the same reviewer data, not validation of either."
    )
    out.append("")

    # --- limitations --------------------------------------------------------------------------
    out += [
        "## Limitations",
        "",
        "- Human ratings are informed judgments, not infallible facts; this tool does not verify "
        "factual claims automatically.",
        "- Overall scores average ordinal ratings with configurable weights; they are not an "
        "objective measure of model quality.",
        "- Items whose evaluations have different sets of null dimensions are averaged over "
        "different dimensions; compare `n_scored_dimensions` before comparing overall scores.",
        "- A small or unrepresentative set of prompts cannot support claims about which model is "
        "better in general.",
        "",
    ]
    return "\n".join(out)


def build_reports(inputs: ReportInputs) -> dict[str, str]:
    """Return ``{file name: content}`` for every report file."""
    return {
        "evaluation_results.csv": evaluation_results_csv(inputs),
        "evaluation_results.json": evaluation_results_json(inputs),
        "pairwise_results.csv": pairwise_results_csv(inputs),
        "summary.md": summary_markdown(inputs),
    }


class ReportWriteError(RuntimeError):
    pass


def write_reports(
    reports: dict[str, str], output_dir: Path, data_dir: Path, *, overwrite: bool = False
) -> list[Path]:
    """Write reports, refusing to touch the source data or silently replace old reports."""
    out_resolved = output_dir.resolve()
    data_resolved = data_dir.resolve()
    if out_resolved == data_resolved or data_resolved in out_resolved.parents:
        raise ReportWriteError(
            f"output directory {output_dir} is inside the data directory {data_dir}; "
            "reports must never be written next to annotated source data"
        )
    targets = [output_dir / name for name in sorted(reports)]
    existing = [p for p in targets if p.exists()]
    if existing and not overwrite:
        names = ", ".join(p.name for p in existing)
        raise ReportWriteError(
            f"report files already exist in {output_dir} ({names}); "
            "pass --overwrite to replace them"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in targets:
        # newline="" disables newline translation, so files are LF on every OS.
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(reports[path.name])
    return targets
