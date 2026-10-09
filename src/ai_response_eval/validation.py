"""Load a data directory and validate it record-by-record and across files.

Validation never stops at the first problem: every file is parsed, every record
is checked against its schema, and cross-file checks run on the records that
were individually valid. The result lists *all* issues, so an annotator can fix
a batch of mistakes in one pass.

Severity:
    error   -- the data is wrong or unsafe to publish; commands refuse to run.
    warning -- legal but worth a look (e.g. the same reviewer scoring the same
               response twice, which is fine for a consistency re-check).
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from ai_response_eval.schemas import CandidateResponse, Evaluation, Preference, Prompt

DATA_FILES: dict[str, tuple[str, type[BaseModel], str]] = {
    # collection: (file name, schema, id field)
    "prompts": ("prompts.json", Prompt, "prompt_id"),
    "responses": ("responses.json", CandidateResponse, "response_id"),
    "evaluations": ("evaluations.json", Evaluation, "evaluation_id"),
    "preferences": ("preferences.json", Preference, "preference_id"),
}

Severity = Literal["error", "warning"]


@dataclass(frozen=True, order=True)
class Issue:
    severity: Severity
    file: str
    location: str
    message: str

    def __str__(self) -> str:
        where = f"{self.file} {self.location}".strip()
        return f"{self.severity.upper()}: {where}: {self.message}"


@dataclass
class Dataset:
    """The individually valid records of one data directory, in file order."""

    prompts: list[Prompt] = field(default_factory=list)
    responses: list[CandidateResponse] = field(default_factory=list)
    evaluations: list[Evaluation] = field(default_factory=list)
    preferences: list[Preference] = field(default_factory=list)

    @cached_property
    def prompts_by_id(self) -> dict[str, Prompt]:
        return {p.prompt_id: p for p in self.prompts}

    @cached_property
    def responses_by_id(self) -> dict[str, CandidateResponse]:
        return {r.response_id: r for r in self.responses}


@dataclass
class ValidationResult:
    dataset: Dataset
    issues: list[Issue]
    files: dict[str, Path]

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    # json.loads silently keeps the last duplicate key; in annotation files that
    # would hide a conflicting score such as two "accuracy" entries.
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateKeyError(f"duplicate JSON key '{key}'")
        seen[key] = value
    return seen


def _load_json_list(path: Path, issues: list[Issue]) -> list[Any] | None:
    name = path.name
    if not path.is_file():
        issues.append(Issue("error", name, "", f"required file not found at {path}"))
        return None
    try:
        # utf-8-sig tolerates the byte-order mark some Windows editors add.
        text = path.read_text(encoding="utf-8-sig")
        data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except UnicodeDecodeError as exc:
        issues.append(Issue("error", name, "", f"file is not valid UTF-8 ({exc.reason})"))
        return None
    except json.JSONDecodeError as exc:
        issues.append(
            Issue("error", name, f"line {exc.lineno} col {exc.colno}", f"invalid JSON: {exc.msg}")
        )
        return None
    except _DuplicateKeyError as exc:
        issues.append(Issue("error", name, "", str(exc)))
        return None
    if not isinstance(data, list):
        issues.append(
            Issue("error", name, "", f"top level must be a JSON array, got {type(data).__name__}")
        )
        return None
    return data


def _record_location(index: int, raw: Any, id_field: str) -> str:
    record_id = raw.get(id_field) if isinstance(raw, dict) else None
    return f"[{index}]" + (f" {record_id}" if isinstance(record_id, str) else "")


def _format_pydantic_error(err: dict[str, Any]) -> str:
    loc = ".".join(str(part) for part in err["loc"])
    msg = err["msg"].removeprefix("Value error, ")
    return f"{loc}: {msg}" if loc else msg


def _parse_records(
    raw_records: list[Any],
    file_name: str,
    schema: type[BaseModel],
    id_field: str,
    issues: list[Issue],
) -> list[Any]:
    """Validate each record against its schema; keep the first of any duplicate IDs."""
    valid: list[Any] = []
    seen_ids: dict[str, int] = {}
    for index, raw in enumerate(raw_records):
        location = _record_location(index, raw, id_field)
        try:
            record = schema.model_validate(raw)
        except ValidationError as exc:
            for err in exc.errors():
                issues.append(Issue("error", file_name, location, _format_pydantic_error(err)))
            continue
        record_id = getattr(record, id_field)
        if record_id in seen_ids:
            issues.append(
                Issue(
                    "error",
                    file_name,
                    location,
                    f"duplicate {id_field} '{record_id}' (first used at [{seen_ids[record_id]}])",
                )
            )
            continue
        seen_ids[record_id] = index
        valid.append(record)
    return valid


# --- sensitive-content scan -------------------------------------------------------------

# Heuristic patterns only: a clean scan does not prove a file is free of personal data.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("API key (sk- prefix)", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("AWS access key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("US SSN-like number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})\b")
# RFC 2606 / RFC 6761 reserved names are safe to use in examples.
_RESERVED_EMAIL_DOMAINS = re.compile(
    r"(^|\.)(example\.(com|org|net)|[a-z0-9-]+\.(example|test|invalid|localhost))$",
    re.IGNORECASE,
)


def _iter_strings(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _iter_strings(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _iter_strings(child, f"{path}[{i}]")


def scan_sensitive_content(raw_records: list[Any], file_name: str, id_field: str) -> list[Issue]:
    """Flag strings that look like credentials or personal contact details."""
    issues: list[Issue] = []
    for index, raw in enumerate(raw_records):
        location = _record_location(index, raw, id_field)
        for field_path, text in _iter_strings(raw):
            for description, pattern in _SECRET_PATTERNS:
                if pattern.search(text):
                    issues.append(
                        Issue(
                            "error",
                            file_name,
                            location,
                            f"{field_path}: looks like a {description}",
                        )
                    )
            for match in _EMAIL.finditer(text):
                if not _RESERVED_EMAIL_DOMAINS.search(match.group(1)):
                    issues.append(
                        Issue(
                            "error",
                            file_name,
                            location,
                            f"{field_path}: contains an email address; use an example.com "
                            "address or remove personal data",
                        )
                    )
    return issues


# --- cross-file checks -------------------------------------------------------------------


def check_references(dataset: Dataset) -> list[Issue]:
    """Checks that need more than one record: references, ownership and duplicates."""
    issues: list[Issue] = []
    prompts = dataset.prompts_by_id
    responses = dataset.responses_by_id

    labels_by_prompt: dict[str, Counter[str]] = defaultdict(Counter)
    for r in dataset.responses:
        if r.prompt_id not in prompts:
            issues.append(
                Issue(
                    "error", "responses.json", r.response_id, f"unknown prompt_id '{r.prompt_id}'"
                )
            )
        labels_by_prompt[r.prompt_id][r.candidate_label] += 1
    for prompt_id, labels in sorted(labels_by_prompt.items()):
        for label, count in sorted(labels.items()):
            if count > 1:
                issues.append(
                    Issue(
                        "error",
                        "responses.json",
                        prompt_id,
                        f"candidate_label '{label}' is used by {count} responses to this prompt",
                    )
                )
    for p in dataset.prompts:
        if p.prompt_id not in labels_by_prompt:
            issues.append(
                Issue("warning", "prompts.json", p.prompt_id, "prompt has no candidate responses")
            )

    review_counts: Counter[tuple[str, str]] = Counter()
    for e in dataset.evaluations:
        response = responses.get(e.response_id)
        if response is None:
            issues.append(
                Issue(
                    "error",
                    "evaluations.json",
                    e.evaluation_id,
                    f"unknown response_id '{e.response_id}'",
                )
            )
            continue
        if response.prompt_id != e.prompt_id:
            issues.append(
                Issue(
                    "error",
                    "evaluations.json",
                    e.evaluation_id,
                    f"prompt_id '{e.prompt_id}' does not match response '{e.response_id}', "
                    f"which belongs to prompt '{response.prompt_id}'",
                )
            )
        prompt = prompts.get(response.prompt_id)
        if prompt is not None and e.reviewed_at < prompt.created_at:
            issues.append(
                Issue(
                    "warning",
                    "evaluations.json",
                    e.evaluation_id,
                    f"reviewed_at {e.reviewed_at} is before the prompt's created_at "
                    f"{prompt.created_at}",
                )
            )
        review_counts[(e.reviewer_id, e.response_id)] += 1
    for (reviewer, response_id), count in sorted(review_counts.items()):
        if count > 1:
            issues.append(
                Issue(
                    "warning",
                    "evaluations.json",
                    response_id,
                    f"reviewer '{reviewer}' evaluated this response {count} times; keep only if "
                    "this is an intentional consistency re-review",
                )
            )

    for pref in dataset.preferences:
        if pref.prompt_id not in prompts:
            issues.append(
                Issue(
                    "error",
                    "preferences.json",
                    pref.preference_id,
                    f"unknown prompt_id '{pref.prompt_id}'",
                )
            )
        for side, response_id in (
            ("response_a_id", pref.response_a_id),
            ("response_b_id", pref.response_b_id),
        ):
            response = responses.get(response_id)
            if response is None:
                issues.append(
                    Issue(
                        "error",
                        "preferences.json",
                        pref.preference_id,
                        f"{side}: unknown response '{response_id}'",
                    )
                )
            elif response.prompt_id != pref.prompt_id:
                issues.append(
                    Issue(
                        "error",
                        "preferences.json",
                        pref.preference_id,
                        f"{side}: response '{response_id}' answers prompt '{response.prompt_id}', "
                        f"not '{pref.prompt_id}'",
                    )
                )
    return issues


def validate_data_dir(data_dir: Path) -> ValidationResult:
    """Run every check on ``data_dir`` and return the valid records plus all issues."""
    issues: list[Issue] = []
    dataset = Dataset()
    files: dict[str, Path] = {}
    if not data_dir.is_dir():
        issues.append(Issue("error", str(data_dir), "", "data directory does not exist"))
        return ValidationResult(dataset, issues, files)

    for collection, (file_name, schema, id_field) in DATA_FILES.items():
        path = data_dir / file_name
        files[collection] = path
        raw_records = _load_json_list(path, issues)
        if raw_records is None:
            continue
        issues.extend(scan_sensitive_content(raw_records, file_name, id_field))
        setattr(
            dataset, collection, _parse_records(raw_records, file_name, schema, id_field, issues)
        )

    issues.extend(check_references(dataset))
    # Stable order: by file in DATA_FILES order, then as discovered within the file.
    file_rank = {name: i for i, (name, _, _) in enumerate(DATA_FILES.values())}
    issues.sort(key=lambda i: file_rank.get(i.file, -1))
    return ValidationResult(dataset, issues, files)
