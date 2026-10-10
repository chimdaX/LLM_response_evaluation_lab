"""Command-line interface for ``ai-eval``.

Analysis commands: ``validate``, ``score``, ``compare``, ``report``, ``status``.
Benchmark-building commands: ``collect``, ``annotate``, ``annotate-pair``.

Exit codes:
    0    success
    1    the input data failed validation
    2    usage, configuration or file-system error (argparse also uses 2)
    130  an interactive session was interrupted (drafts are kept)

No command makes network calls. Analysis commands never modify ``--data-dir``; the
benchmark-building commands only *append* new records to it (plus working drafts in
``--data-dir/.drafts``) and never change or delete existing records.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from ai_response_eval import __version__
from ai_response_eval.annotation import (
    AnnotationError,
    annotate_pair,
    annotate_response,
    confirm_attestation,
    evaluation_queue,
    preference_queue,
    revise_evaluation,
)
from ai_response_eval.collection import (
    CANDIDATE_LABELS,
    ResponseMetadata,
    collect_interactive,
    import_response,
)
from ai_response_eval.comparisons import build_pairwise_rows, summarize_pairwise
from ai_response_eval.interactive import Console, TerminalConsole, ask_yes_no
from ai_response_eval.progress import compute_progress, format_progress
from ai_response_eval.reporting import ReportInputs, ReportWriteError, build_reports, write_reports
from ai_response_eval.rubric import COLLECTION_METHODS, DIMENSIONS
from ai_response_eval.scoring import (
    ConfigError,
    ScoringConfig,
    format_score,
    load_scoring_config,
    score_evaluations,
)
from ai_response_eval.storage import DraftStore, StorageError
from ai_response_eval.validation import ValidationResult, validate_data_dir

EXIT_OK = 0
EXIT_INVALID_DATA = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130

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


def cmd_status(args: argparse.Namespace) -> int:
    result = _load_valid(args.data_dir)
    if result is None:
        return EXIT_INVALID_DATA
    print(format_progress(compute_progress(result.dataset, DraftStore(args.data_dir))))
    return EXIT_OK


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _check_reviewer(reviewer_id: str) -> bool:
    if _ID_PATTERN.match(reviewer_id) and len(reviewer_id) <= 64:
        return True
    print(
        "ERROR: --reviewer-id must start with a letter or digit and contain only letters, "
        "digits, '_', '.' or '-'",
        file=sys.stderr,
    )
    return False


def _interrupted() -> int:
    print(
        "\nInterrupted. Answers given so far are kept in a draft; run the same command to resume.",
        file=sys.stderr,
    )
    return EXIT_INTERRUPTED


def cmd_collect(args: argparse.Namespace) -> int:
    result = _load_valid(args.data_dir)
    if result is None:
        return EXIT_INVALID_DATA
    console: Console = args.console
    if args.text_file is not None:
        # Non-interactive import: every piece of provenance must be given explicitly.
        missing = [
            flag
            for flag, value in (
                ("--prompt-id", args.prompt_id),
                ("--label", args.label),
                ("--model-name", args.model_name),
                ("--provider", args.provider),
                ("--method", args.method),
                ("--generated-at", args.generated_at),
            )
            if value is None
        ]
        if missing:
            print(f"ERROR: --text-file also requires {', '.join(missing)}", file=sys.stderr)
            return EXIT_USAGE
        try:
            text = args.text_file.read_text(encoding="utf-8-sig")
            generated_at = date.fromisoformat(args.generated_at)
            meta = ResponseMetadata(
                args.model_name, args.provider, args.method, generated_at, args.settings
            )
            record = import_response(
                args.data_dir,
                result.dataset,
                args.prompt_id,
                args.label,
                text,
                meta,
                today=args.today,
            )
        except (OSError, ValueError) as exc:  # CollectionError is a ValueError
            print(f"ERROR: {exc}", file=sys.stderr)
            return EXIT_USAGE
        print(f"Imported {record['response_id']} into {args.data_dir / 'responses.json'}.")
        return EXIT_OK

    defaults = {
        "model_name": args.model_name,
        "provider": args.provider,
        "collection_method": args.method,
        "generation_settings": args.settings,
    }
    try:
        count = collect_interactive(
            console,
            args.data_dir,
            result.dataset,
            today=args.today,
            prompt_id=args.prompt_id,
            label=args.label,
            defaults=defaults,
        )
    except (KeyboardInterrupt, EOFError):
        print("\nInterrupted; responses imported before this point are saved.", file=sys.stderr)
        return EXIT_INTERRUPTED
    console.say(f"\n{count} response(s) imported this session.")
    return EXIT_OK


def cmd_annotate(args: argparse.Namespace) -> int:
    if not _check_reviewer(args.reviewer_id):
        return EXIT_USAGE
    result = _load_valid(args.data_dir)
    if result is None:
        return EXIT_INVALID_DATA
    console: Console = args.console
    dataset, drafts = result.dataset, DraftStore(args.data_dir)
    if args.revise is not None:
        if args.repeat:
            print("ERROR: --revise and --repeat cannot be combined", file=sys.stderr)
            return EXIT_USAGE
        return _run_revision(args, console, dataset, drafts)
    if args.response_id is not None:
        response = dataset.responses_by_id.get(args.response_id)
        if response is None:
            print(f"ERROR: unknown response_id '{args.response_id}'", file=sys.stderr)
            return EXIT_USAGE
        queue = [response]
    else:
        queue = evaluation_queue(dataset, args.reviewer_id, drafts)
    if not queue:
        console.say(
            f"Nothing to annotate: {args.reviewer_id} has evaluated every collected response."
        )
        return EXIT_OK
    try:
        if not confirm_attestation(console):
            console.say("Not confirmed; nothing was recorded.")
            return EXIT_USAGE
        saved = 0
        for i, response in enumerate(queue):
            console.say(f"\n===== {i + 1} of {len(queue)} remaining for {args.reviewer_id} =====")
            record = annotate_response(
                console,
                args.data_dir,
                dataset,
                response,
                args.reviewer_id,
                today=args.today,
                drafts=drafts,
                allow_repeat=args.repeat,
            )
            if record is None:
                break
            saved += 1
            if i + 1 < len(queue) and not ask_yes_no(
                console, "Continue with the next response?", default=True
            ):
                break
    except (KeyboardInterrupt, EOFError):
        return _interrupted()
    except (AnnotationError, StorageError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE
    console.say(
        f"\n{saved} evaluation(s) saved this session. Run 'ai-eval status --data-dir "
        f"{args.data_dir}' to see progress."
    )
    return EXIT_OK


def _run_revision(args: argparse.Namespace, console: Console, dataset, drafts: DraftStore) -> int:
    try:
        if not confirm_attestation(console):
            console.say("Not confirmed; nothing was recorded.")
            return EXIT_USAGE
        record = revise_evaluation(
            console,
            args.data_dir,
            dataset,
            args.revise,
            args.reviewer_id,
            today=args.today,
            drafts=drafts,
        )
    except (KeyboardInterrupt, EOFError):
        return _interrupted()
    except (AnnotationError, StorageError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if record is not None:
        console.say(
            f"Run 'ai-eval validate --data-dir {args.data_dir}' to confirm the revision history."
        )
    return EXIT_OK


def cmd_annotate_pair(args: argparse.Namespace) -> int:
    if not _check_reviewer(args.reviewer_id):
        return EXIT_USAGE
    result = _load_valid(args.data_dir)
    if result is None:
        return EXIT_INVALID_DATA
    console: Console = args.console
    dataset, drafts = result.dataset, DraftStore(args.data_dir)
    queue = preference_queue(dataset, args.reviewer_id, drafts)
    if args.prompt_id is not None:
        queue = [p for p in queue if p.prompt.prompt_id == args.prompt_id]
    if not queue:
        console.say(
            "No pairs to compare: either both candidates are not collected yet, or "
            f"{args.reviewer_id} has already recorded a preference."
        )
        return EXIT_OK
    try:
        if not confirm_attestation(console):
            console.say("Not confirmed; nothing was recorded.")
            return EXIT_USAGE
        saved = 0
        for i, pair in enumerate(queue):
            console.say(
                f"\n===== {i + 1} of {len(queue)} pairs remaining for {args.reviewer_id} ====="
            )
            record = annotate_pair(
                console,
                args.data_dir,
                dataset,
                pair,
                args.reviewer_id,
                today=args.today,
                drafts=drafts,
            )
            if record is None:
                break
            saved += 1
            if i + 1 < len(queue) and not ask_yes_no(
                console, "Continue with the next pair?", default=True
            ):
                break
    except (KeyboardInterrupt, EOFError):
        return _interrupted()
    except (AnnotationError, StorageError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE
    console.say(f"\n{saved} preference(s) saved this session.")
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

    p = sub.add_parser("status", help="show benchmark collection and annotation progress")
    add_data_dir(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser(
        "collect",
        help="import authentic model responses (interactive, or one file with --text-file)",
    )
    add_data_dir(p)
    p.add_argument("--prompt-id", help="only this prompt's pending slots")
    p.add_argument("--label", choices=CANDIDATE_LABELS, help="only this candidate slot")
    p.add_argument("--model-name", help="model name exactly as shown by the interface or API")
    p.add_argument("--provider", help="provider or product, e.g. 'OpenAI ChatGPT'")
    p.add_argument("--method", choices=COLLECTION_METHODS, help="how the response was obtained")
    p.add_argument("--generated-at", help="date the response was generated (YYYY-MM-DD)")
    p.add_argument("--settings", help="generation settings, only if actually known")
    p.add_argument(
        "--text-file",
        type=Path,
        help="import this file non-interactively (requires all metadata flags above)",
    )
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("annotate", help="evaluate collected responses against the rubric")
    add_data_dir(p)
    p.add_argument("--reviewer-id", required=True, help="your stable reviewer ID, e.g. reviewer_01")
    target = p.add_mutually_exclusive_group()
    target.add_argument(
        "--response-id", help="evaluate this response instead of the next in the queue"
    )
    target.add_argument(
        "--revise",
        metavar="EVALUATION_ID",
        help="correct one of your saved evaluations; saves a new record that supersedes it",
    )
    p.add_argument(
        "--repeat",
        action="store_true",
        help="deliberate consistency re-review of a response you already evaluated "
        "(stored separately, not scored)",
    )
    p.set_defaults(func=cmd_annotate)

    p = sub.add_parser("annotate-pair", help="record A/B/tie preferences for collected pairs")
    add_data_dir(p)
    p.add_argument("--reviewer-id", required=True, help="your stable reviewer ID, e.g. reviewer_01")
    p.add_argument(
        "--prompt-id", help="compare this prompt's pair instead of the next in the queue"
    )
    p.set_defaults(func=cmd_annotate_pair)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    console: Console | None = None,
    today: date | None = None,
) -> int:
    """Entry point. ``console`` and ``today`` are injectable so tests are deterministic."""
    # Avoid UnicodeEncodeError on legacy Windows consoles when data contains non-ASCII text.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    args.console = console or TerminalConsole()
    args.today = today or date.today()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
