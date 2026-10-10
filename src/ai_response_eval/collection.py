"""Import authentic model responses into a benchmark data directory.

Collection is deliberately manual and API-free: the evaluator pastes a prompt into a
chat interface (or any model they can run), copies the complete first response into a
plain-text file, and imports it with the metadata they can actually observe.

Each benchmark prompt has two candidate slots, ``A`` and ``B``, with response IDs
``<prompt_id>-A`` and ``<prompt_id>-B``. A slot is *pending* until a response for it
exists in ``responses.json``. Imported records always use provenance
``model_output``; this module never writes synthetic or placeholder responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ai_response_eval.interactive import (
    Console,
    ask_choice,
    ask_date,
    ask_text,
    ask_yes_no,
    wrap,
)
from ai_response_eval.rubric import COLLECTION_METHODS, SCHEMA_VERSION
from ai_response_eval.schemas import CandidateResponse, Prompt
from ai_response_eval.storage import StorageError, append_record
from ai_response_eval.validation import Dataset, scan_sensitive_content

CANDIDATE_LABELS: tuple[str, ...] = ("A", "B")
RAW_RESPONSES_DIRNAME = "raw_responses"


class CollectionError(ValueError):
    """Raised when a response cannot be imported; nothing is written."""


def response_id_for(prompt_id: str, label: str) -> str:
    return f"{prompt_id}-{label}"


@dataclass(frozen=True)
class CollectionSlot:
    prompt: Prompt
    label: str

    @property
    def response_id(self) -> str:
        return response_id_for(self.prompt.prompt_id, self.label)

    def raw_path(self, data_dir: Path) -> Path:
        return data_dir / RAW_RESPONSES_DIRNAME / f"{self.response_id}.txt"


def pending_slots(dataset: Dataset) -> list[CollectionSlot]:
    """Candidate slots (prompt x label) that have no response yet, in prompt-ID order."""
    filled = {(r.prompt_id, r.candidate_label) for r in dataset.responses}
    return [
        CollectionSlot(prompt, label)
        for prompt in sorted(dataset.prompts, key=lambda p: p.prompt_id)
        for label in CANDIDATE_LABELS
        if (prompt.prompt_id, label) not in filled
    ]


@dataclass(frozen=True)
class ResponseMetadata:
    """What the evaluator observed when the response was generated."""

    model_name: str
    provider: str
    collection_method: str
    generated_at: date
    generation_settings: str | None = None


def normalize_text(text: str) -> str:
    """Unify line endings and trim surrounding whitespace; the body is kept verbatim."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def build_response_record(
    prompt: Prompt, label: str, text: str, meta: ResponseMetadata
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "response_id": response_id_for(prompt.prompt_id, label),
        "prompt_id": prompt.prompt_id,
        "candidate_label": label,
        "response_text": normalize_text(text),
        "model_name": meta.model_name.strip(),
        "provider": meta.provider.strip(),
        "collection_method": meta.collection_method,
        "generation_settings": (meta.generation_settings or "").strip() or None,
        "provenance": "model_output",
        "generated_at": meta.generated_at.isoformat(),
    }
    try:
        CandidateResponse.model_validate(record)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'record'}: {e['msg']}" for e in exc.errors()
        )
        raise CollectionError(f"response record is invalid: {details}") from exc
    return record


def import_response(
    data_dir: Path,
    dataset: Dataset,
    prompt_id: str,
    label: str,
    text: str,
    meta: ResponseMetadata,
    *,
    today: date,
) -> dict[str, Any]:
    """Validate and append one authentic response. Never replaces an existing one."""
    prompt = dataset.prompts_by_id.get(prompt_id)
    if prompt is None:
        raise CollectionError(f"unknown prompt_id '{prompt_id}'")
    if label not in CANDIDATE_LABELS:
        raise CollectionError(f"candidate label must be one of {', '.join(CANDIDATE_LABELS)}")
    response_id = response_id_for(prompt_id, label)
    if response_id in dataset.responses_by_id or any(
        r.prompt_id == prompt_id and r.candidate_label == label for r in dataset.responses
    ):
        raise CollectionError(
            f"slot {response_id} already has a response; existing responses are never replaced"
        )
    if not normalize_text(text):
        raise CollectionError("the response text is empty")
    if meta.generated_at > today:
        raise CollectionError(f"generated_at {meta.generated_at} is in the future")

    record = build_response_record(prompt, label, text, meta)
    sensitive = scan_sensitive_content([record], "responses.json", "response_id")
    if sensitive:
        raise CollectionError(
            "possible sensitive content: "
            + "; ".join(i.message for i in sensitive)
            + ". Remove it from the text file (or replace it with a placeholder) and retry."
        )
    try:
        append_record(data_dir / "responses.json", record, "response_id")
    except StorageError as exc:
        raise CollectionError(str(exc)) from exc
    return record


# --- interactive session -------------------------------------------------------------


def _show_prompt(console: Console, slot: CollectionSlot) -> None:
    console.say("")
    console.say(
        f"=== Slot {slot.response_id}  (prompt {slot.prompt.prompt_id}, "
        f"domain {slot.prompt.domain}, candidate {slot.label}) ==="
    )
    console.say("Copy the prompt between the markers EXACTLY into a NEW chat:")
    console.say("-------- BEGIN PROMPT --------")
    console.say(slot.prompt.prompt)
    console.say("--------- END PROMPT ---------")


def _read_raw_text(console: Console, path: Path) -> str | None:
    """Wait for the evaluator to paste the response into ``path``; None means skip."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    console.say("")
    console.say("Paste the model's COMPLETE FIRST response (no edits, no regeneration) into:")
    console.say(f"    {path}")
    while True:
        answer = console.ask("Save the file, then press Enter (or type 'skip'): ").strip().lower()
        if answer == "skip":
            return None
        text = normalize_text(path.read_text(encoding="utf-8-sig"))
        if text:
            return text
        console.say("  The file is still empty.")


def collect_interactive(
    console: Console,
    data_dir: Path,
    dataset: Dataset,
    *,
    today: date,
    prompt_id: str | None = None,
    label: str | None = None,
    defaults: dict[str, str | None] | None = None,
) -> int:
    """Walk through pending slots, importing one response per slot. Returns the count."""
    defaults = defaults or {}
    slots = pending_slots(dataset)
    if prompt_id is not None:
        slots = [s for s in slots if s.prompt.prompt_id == prompt_id]
    if label is not None:
        slots = [s for s in slots if s.label == label]
    if not slots:
        console.say("No pending response slots match. Run 'ai-eval status' to see progress.")
        return 0

    console.say(
        f"{len(slots)} pending response slot(s). Ctrl+C stops at any time; "
        "nothing is saved until you confirm."
    )
    imported = 0
    for slot in slots:
        _show_prompt(console, slot)
        text = _read_raw_text(console, slot.raw_path(data_dir))
        if text is None:
            console.say("Skipped.")
            continue

        console.say("Record only what you actually observed; leave optional fields blank.")
        model_name = ask_text(
            console, "Model name as shown in the interface", default=defaults.get("model_name")
        )
        provider = ask_text(
            console, "Provider / product (e.g. OpenAI ChatGPT)", default=defaults.get("provider")
        )
        method = ask_choice(
            console,
            "Collection method",
            {m: m for m in COLLECTION_METHODS},
            default=defaults.get("collection_method") or "web_chat",
        )
        generated_at = ask_date(console, "Date generated (YYYY-MM-DD)", default=today, latest=today)
        settings = ask_text(
            console,
            "Generation settings, if known (optional)",
            required=False,
            default=defaults.get("generation_settings"),
        )
        meta = ResponseMetadata(model_name or "", provider or "", method, generated_at, settings)

        words = len(text.split())
        preview = text[:300] + ("..." if len(text) > 300 else "")
        console.say("")
        console.say(
            f"Response {slot.response_id}: {words} words, model '{meta.model_name}' "
            f"({meta.provider}, {meta.collection_method}, {meta.generated_at})."
        )
        console.say(wrap(preview))
        if not ask_yes_no(console, "Import this response?", default=True):
            console.say("Not imported.")
            continue
        try:
            import_response(
                data_dir, dataset, slot.prompt.prompt_id, slot.label, text, meta, today=today
            )
        except CollectionError as exc:
            console.say(f"NOT IMPORTED: {exc}")
            continue
        imported += 1
        console.say(f"Imported {slot.response_id}.")
        # Metadata is deliberately NOT carried over to the next slot: A and B usually come
        # from different models, and an accepted default would silently mislabel provenance.
        if slot is not slots[-1] and not ask_yes_no(
            console, "Collect the next slot?", default=True
        ):
            break
    return imported
