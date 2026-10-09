"""Command-line interface: ``ai-eval validate | score | compare | report``.

Exit codes:
    0  success
    1  the input data failed validation
    2  usage, configuration or file-system error (argparse also uses 2)

No command makes network calls, and no command modifies files in ``--data-dir``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ai_response_eval import __version__
from ai_response_eval.comparisons import build_pairwise_rows, summarize_pairwise
from ai_response_eval.reporting import ReportInputs, ReportWriteError, build_reports, write_reports
from ai_response_eval.rubric import DIMENSIONS
from ai_response_eval.scoring import (
    ConfigError,
    ScoringConfig,
    format_score,
    load_scoring_config,
    score_evaluations,
)
from ai_response_eval.validation import ValidationResult, validate_data_dir

EXIT_OK = 0
EXIT_INVALID_DATA = 1
EXIT_USAGE = 2

DEFAULT_CONFIG = Path("config/scoring.json")
DEFAULT_RUBRIC = Path("rubrics/rubric_v1.md")


def _print_issues(result: ValidationResult, *, show_warnings: bool = True) -> None:
    for issue in result.errors:
        print(issue, file=sys.stderr)
    if show_warnings:
        for issue in result.warnings:
            print(issue, file=sys.stderr)


def _load_valid(data_dir: Path) -> ValidationResult | None:
    """Validate first; commands other than ``validate`` refuse to run on invalid data."""
    result = validate_data_dir(data_dir)
    if not result.ok:
        _print_issues(result, show_warnings=False)
        print(
            f"\n{len(result.errors)} validation error(s) in {data_dir}; "
            f"run 'ai-eval validate --data-dir {data_dir}' for details.",
            file=sys.stderr,
        )
        return None
    return result


def _load_config(path: Path) -> ScoringConfig | None:
    try:
        return load_scoring_config(path)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None


def cmd_validate(args: argparse.Namespace) -> int:
    result = validate_data_dir(args.data_dir)
    _print_issues(result)
    d = result.dataset
    counts = (
        f"{len(d.prompts)} prompts, {len(d.responses)} responses, "
        f"{len(d.evaluations)} evaluations, {len(d.preferences)} preferences"
    )
    if result.ok:
        print(f"OK: {args.data_dir} is valid ({counts}); {len(result.warnings)} warning(s).")
        if args.strict and result.warnings:
            print("FAILED: --strict treats warnings as errors.", file=sys.stderr)
            return EXIT_INVALID_DATA
        return EXIT_OK
    print(
        f"FAILED: {len(result.errors)} error(s), {len(result.warnings)} warning(s) in "
        f"{args.data_dir}. Valid records so far: {counts}.",
        file=sys.stderr,
    )
    return EXIT_INVALID_DATA


def cmd_score(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    if config is None:
        return EXIT_USAGE
    result = _load_valid(args.data_dir)
    if result is None:
        return EXIT_INVALID_DATA
    scored = score_evaluations(result.dataset, config)

    if args.json:
        payload = [
            {
                "evaluation_id": s.evaluation.evaluation_id,
                "response_id": s.evaluation.response_id,
                "domain": s.domain,
                "scores": {dim: s.evaluation.scores[dim] for dim in DIMENSIONS},
                "overall": s.overall,
                "n_scored_dimensions": s.n_scored,
                "review_flags": [str(f) for f in s.flags],
            }
            for s in scored
        ]
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    header = ("Evaluation", "Response", "Domain", "Overall", "Scored", "Review flags")
    rows = [
        (
            s.evaluation.evaluation_id,
            s.evaluation.response_id,
            s.domain,
            format_score(s.overall, config.display_decimals),
            f"{s.n_scored}/{len(DIMENSIONS)}",
            ", ".join(str(f) for f in s.flags) or "-",
        )
        for s in scored
    ]
    widths = [max(len(str(c)) for c in col) for col in zip(header, *rows, strict=True)]
    for row in (header, *rows):
        print("  ".join(str(c).ljust(w) for c, w in zip(row, widths, strict=True)).rstrip())
    flagged = sum(s.needs_review for s in scored)
    print(
        f"\n{len(scored)} evaluation(s); {flagged} flagged for review. Overall = weighted mean of "
        "non-null dimension scores (config weights); flags are shown regardless of the overall."
    )
    return EXIT_OK


def cmd_compare(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    if config is None:
        return EXIT_USAGE
    result = _load_valid(args.data_dir)
    if result is None:
        return EXIT_INVALID_DATA
    dataset = result.dataset
    rows = build_pairwise_rows(dataset, score_evaluations(dataset, config), config)
    dec = config.display_decimals

    if not rows:
        print("No pairwise preferences recorded.")
        return EXIT_OK
    for row in rows:
        p = row.preference
        winner = p.winner if p.winner == "tie" else f"{p.winner} ({row.winner_response_id})"
        print(f"{p.preference_id}  prompt {p.prompt_id} [{row.domain}]")
        print(f"  A = {p.response_a_id}   B = {p.response_b_id}")
        print(
            f"  Human-recorded preference: {winner}   "
            f"(reviewer {p.reviewer_id}, {p.annotation_source})"
        )
        print(f"  Reviewer reason: {p.reason}")
        suggestion = row.score_suggestion or "n/a (a response has no scored evaluation)"
        print(
            f"  System-generated score suggestion (not a human judgment): {suggestion}   "
            f"[mean overall A={format_score(row.a_overall, dec)}, "
            f"B={format_score(row.b_overall, dec)}; {row.agreement}]"
        )
        print()
    s = summarize_pairwise(rows)
    print(
        f"Human-recorded outcomes over {s.decisions} decision(s): A={s.a_wins}, B={s.b_wins}, "
        f"tie={s.ties}. Score suggestion matched the human preference in {s.agreements} of "
        f"{s.with_suggestion} decision(s) where it was available."
    )
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    if config is None:
        return EXIT_USAGE
    result = _load_valid(args.data_dir)
    if result is None:
        return EXIT_INVALID_DATA
    dataset = result.dataset
    scored = score_evaluations(dataset, config)
    inputs = ReportInputs(
        dataset=dataset,
        scored=scored,
        pairwise=build_pairwise_rows(dataset, scored, config),
        config=config,
        input_files=result.files,
        config_path=args.config,
        rubric_path=args.rubric,
        generated_at=datetime.now(UTC),
    )
    try:
        written = write_reports(
            build_reports(inputs), args.output_dir, args.data_dir, overwrite=args.overwrite
        )
    except (ReportWriteError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE
    for path in written:
        print(f"wrote {path}")
    if not args.rubric.is_file():
        print(
            f"WARNING: rubric file {args.rubric} not found; its hash is omitted.", file=sys.stderr
        )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-eval",
        description="Validate, score, compare and report human evaluations of AI responses.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def add_data_dir(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--data-dir",
            type=Path,
            required=True,
            help="directory with prompts.json, responses.json, evaluations.json, preferences.json",
        )

    def add_config(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--config",
            type=Path,
            default=DEFAULT_CONFIG,
            help=f"scoring configuration file (default: {DEFAULT_CONFIG})",
        )

    p = sub.add_parser("validate", help="check schemas and cross-file references")
    add_data_dir(p)
    p.add_argument("--strict", action="store_true", help="treat warnings as errors")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("score", help="show computed overall scores and review flags")
    add_data_dir(p)
    add_config(p)
    p.add_argument("--json", action="store_true", help="print machine-readable JSON")
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("compare", help="list human pairwise preferences with their reasons")
    add_data_dir(p)
    add_config(p)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("report", help="write CSV, JSON and Markdown reports")
    add_data_dir(p)
    add_config(p)
    p.add_argument("--output-dir", type=Path, required=True, help="where to write report files")
    p.add_argument(
        "--rubric",
        type=Path,
        default=DEFAULT_RUBRIC,
        help=f"rubric document to fingerprint in report metadata (default: {DEFAULT_RUBRIC})",
    )
    p.add_argument(
        "--overwrite", action="store_true", help="replace existing report files in --output-dir"
    )
    p.set_defaults(func=cmd_report)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # Avoid UnicodeEncodeError on legacy Windows consoles when data contains non-ASCII text.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
