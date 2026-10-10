"""Importing authentic responses: provenance, validation, no overwrites, interactive flow."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from ai_response_eval.collection import (
    CollectionError,
    ResponseMetadata,
    collect_interactive,
    import_response,
    pending_slots,
)
from ai_response_eval.interactive import ScriptedConsole
from ai_response_eval.validation import validate_data_dir
from tests.conftest import TODAY

META = ResponseMetadata("vendor-model-y", "Other Chat", "web_chat", date(2026, 10, 11), None)


def _import(
    bench_dir: Path, prompt_id: str = "P2", label: str = "A", text: str = "An answer.", meta=META
):
    dataset = validate_data_dir(bench_dir).dataset
    return import_response(bench_dir, dataset, prompt_id, label, text, meta, today=TODAY)


def _responses(bench_dir: Path) -> list[dict]:
    return json.loads((bench_dir / "responses.json").read_text(encoding="utf-8"))


def test_pending_slots(bench_dir: Path) -> None:
    dataset = validate_data_dir(bench_dir).dataset
    assert [s.response_id for s in pending_slots(dataset)] == ["P2-A", "P2-B"]


def test_import_records_provenance(bench_dir: Path) -> None:
    record = _import(bench_dir, text="\r\nLine one.\r\nLine two.\r\n\r\n")
    assert record == {
        "schema_version": "1.1",
        "response_id": "P2-A",
        "prompt_id": "P2",
        "candidate_label": "A",
        "response_text": "Line one.\nLine two.",
        "model_name": "vendor-model-y",
        "provider": "Other Chat",
        "collection_method": "web_chat",
        "generation_settings": None,
        "provenance": "model_output",
        "generated_at": "2026-10-11",
    }
    assert _responses(bench_dir)[-1] == record
    assert validate_data_dir(bench_dir).ok


def test_existing_slot_is_never_replaced(bench_dir: Path) -> None:
    before = _responses(bench_dir)
    with pytest.raises(CollectionError, match="already has a response"):
        _import(bench_dir, prompt_id="P1", label="A")
    assert _responses(bench_dir) == before


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"prompt_id": "P9"}, "unknown prompt_id"),
        ({"label": "C"}, "candidate label must be one of"),
        ({"text": "  \n "}, "empty"),
        ({"meta": ResponseMetadata("m", "p", "web_chat", date(2026, 10, 13))}, "in the future"),
        (
            {"meta": ResponseMetadata("example-only", "p", "web_chat", date(2026, 10, 1))},
            "real model name",
        ),
        ({"meta": ResponseMetadata(" ", "p", "web_chat", date(2026, 10, 1))}, "model_name"),
        ({"text": "Email me at someone@gmail.com"}, "sensitive content"),
    ],
)
def test_invalid_imports_write_nothing(bench_dir: Path, kwargs: dict, message: str) -> None:
    before = _responses(bench_dir)
    with pytest.raises(CollectionError, match=message):
        _import(bench_dir, **kwargs)
    assert _responses(bench_dir) == before


def _collect(bench_dir: Path, answers: list[str], **kwargs) -> tuple[int, ScriptedConsole]:
    dataset = validate_data_dir(bench_dir).dataset
    console = ScriptedConsole(answers)
    count = collect_interactive(console, bench_dir, dataset, today=TODAY, **kwargs)
    return count, console


def test_interactive_collection_from_raw_file(bench_dir: Path) -> None:
    raw = bench_dir / "raw_responses" / "P2-A.txt"
    raw.parent.mkdir()
    raw.write_text("The answer is 42.\n", encoding="utf-8")
    answers = ["", "vendor-model-y", "Other Chat", "", "2026-10-11", "", "y"]
    count, console = _collect(bench_dir, answers, prompt_id="P2", label="A")
    assert count == 1
    assert "BEGIN PROMPT" in console.text
    saved = _responses(bench_dir)[-1]
    assert saved["response_text"] == "The answer is 42."
    assert saved["collection_method"] == "web_chat"  # default accepted
    assert saved["generated_at"] == "2026-10-11"


def test_interactive_waits_for_nonempty_file_and_can_skip(bench_dir: Path) -> None:
    count, console = _collect(bench_dir, ["", "skip"], prompt_id="P2", label="A")
    assert count == 0
    assert "The file is still empty." in console.text
    assert (bench_dir / "raw_responses" / "P2-A.txt").exists()  # created for the user to paste into


def test_interactive_rejects_future_date(bench_dir: Path) -> None:
    raw = bench_dir / "raw_responses" / "P2-B.txt"
    raw.parent.mkdir()
    raw.write_text("Text.", encoding="utf-8")
    answers = [
        "",
        "m",
        "p",
        "api",
        "2026-12-01",
        "10/11/2026",
        "2026-10-12",
        "temperature 0.2",
        "y",
    ]
    count, console = _collect(bench_dir, answers, prompt_id="P2", label="B")
    assert count == 1
    assert "cannot be later than 2026-10-12" in console.text
    assert "Use the format YYYY-MM-DD." in console.text
    assert _responses(bench_dir)[-1]["generation_settings"] == "temperature 0.2"


def test_model_name_is_not_carried_over_between_slots(bench_dir: Path) -> None:
    raw_dir = bench_dir / "raw_responses"
    raw_dir.mkdir()
    for label in "AB":
        (raw_dir / f"P2-{label}.txt").write_text(f"Answer {label}.", encoding="utf-8")
    answers = [
        "",
        "model-one",
        "Prov",
        "",
        "",
        "",
        "y",
        "y",  # slot A, then continue
        "",
        "",
        "model-two",
        "Prov",
        "",
        "",
        "",
        "y",
    ]
    # For slot B the first empty model-name answer must be re-asked (no default carried over).
    count, _ = _collect(bench_dir, answers, prompt_id="P2")
    assert count == 2
    assert [r["model_name"] for r in _responses(bench_dir)[-2:]] == ["model-one", "model-two"]
