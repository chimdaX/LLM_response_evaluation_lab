"""File loading and cross-file validation."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from ai_response_eval.validation import validate_data_dir
from tests.conftest import (
    EXAMPLES_DIR,
    Records,
    make_evaluation,
    make_preference,
    make_prompt,
    make_response,
)

WriteDataset = Callable[[Records], Path]


def _messages(result) -> list[str]:
    return [str(issue) for issue in result.issues]


def test_valid_dataset_has_no_issues(records: Records, write_dataset: WriteDataset) -> None:
    result = validate_data_dir(write_dataset(records))
    assert result.ok
    assert result.issues == []
    assert [r.response_id for r in result.dataset.responses] == ["R1A", "R1B"]


def test_committed_examples_are_valid() -> None:
    result = validate_data_dir(EXAMPLES_DIR)
    assert result.ok, _messages(result)
    assert result.warnings == []


def test_empty_collections_are_valid(write_dataset: WriteDataset) -> None:
    empty: Records = {"prompts": [], "responses": [], "evaluations": [], "preferences": []}
    result = validate_data_dir(write_dataset(empty))
    assert result.ok
    assert result.dataset.evaluations == []


def test_missing_directory(tmp_path: Path) -> None:
    result = validate_data_dir(tmp_path / "nope")
    assert not result.ok
    assert "does not exist" in result.errors[0].message


def test_missing_file(records: Records, write_dataset: WriteDataset) -> None:
    data_dir = write_dataset(records)
    (data_dir / "preferences.json").unlink()
    result = validate_data_dir(data_dir)
    assert not result.ok
    assert any(i.file == "preferences.json" and "not found" in i.message for i in result.errors)


def test_malformed_json_reports_position(records: Records, write_dataset: WriteDataset) -> None:
    data_dir = write_dataset(records)
    (data_dir / "prompts.json").write_text('[\n  {"prompt_id": "P1",}\n]', encoding="utf-8")
    result = validate_data_dir(data_dir)
    error = next(i for i in result.errors if i.file == "prompts.json")
    assert "invalid JSON" in error.message
    assert error.location.startswith("line 2")


def test_top_level_must_be_array(records: Records, write_dataset: WriteDataset) -> None:
    data_dir = write_dataset(records)
    (data_dir / "prompts.json").write_text(json.dumps(make_prompt()), encoding="utf-8")
    result = validate_data_dir(data_dir)
    assert any("must be a JSON array" in i.message for i in result.errors)


def test_duplicate_json_keys_rejected(records: Records, write_dataset: WriteDataset) -> None:
    data_dir = write_dataset(records)
    text = (data_dir / "evaluations.json").read_text(encoding="utf-8")
    # Inject a second, conflicting "accuracy" key into the first evaluation's scores.
    text = text.replace('"accuracy": 5,', '"accuracy": 5,\n      "accuracy": 1,', 1)
    (data_dir / "evaluations.json").write_text(text, encoding="utf-8")
    result = validate_data_dir(data_dir)
    assert any("duplicate JSON key 'accuracy'" in i.message for i in result.errors)


def test_utf8_bom_is_tolerated(records: Records, write_dataset: WriteDataset) -> None:
    data_dir = write_dataset(records)
    path = data_dir / "prompts.json"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert validate_data_dir(data_dir).ok


def test_duplicate_ids_rejected(records: Records, write_dataset: WriteDataset) -> None:
    records["evaluations"].append(make_evaluation("E1", "R1B"))
    records["preferences"].append(make_preference("PW1", winner="B"))
    result = validate_data_dir(write_dataset(records))
    messages = _messages(result)
    assert any("duplicate evaluation_id 'E1'" in m for m in messages)
    assert any("duplicate preference_id 'PW1'" in m for m in messages)


def test_response_with_unknown_prompt(records: Records, write_dataset: WriteDataset) -> None:
    records["responses"].append(make_response("R9", prompt_id="P9"))
    result = validate_data_dir(write_dataset(records))
    assert any("unknown prompt_id 'P9'" in m for m in _messages(result))


def test_duplicate_candidate_label_within_prompt(
    records: Records, write_dataset: WriteDataset
) -> None:
    records["responses"].append(make_response("R1C", label="A"))
    result = validate_data_dir(write_dataset(records))
    assert any("candidate_label 'A' is used by 2 responses" in m for m in _messages(result))


def test_evaluation_with_unknown_response(records: Records, write_dataset: WriteDataset) -> None:
    records["evaluations"].append(make_evaluation("E3", "R404"))
    result = validate_data_dir(write_dataset(records))
    assert any("unknown response_id 'R404'" in m for m in _messages(result))


def test_evaluation_prompt_must_match_response(
    records: Records, write_dataset: WriteDataset
) -> None:
    records["prompts"].append(make_prompt("P2"))
    records["responses"].append(make_response("R2A", prompt_id="P2"))
    records["evaluations"].append(make_evaluation("E3", "R2A", prompt_id="P1"))
    result = validate_data_dir(write_dataset(records))
    assert any("does not match response 'R2A'" in m for m in _messages(result))


def test_preference_responses_must_belong_to_prompt(
    records: Records, write_dataset: WriteDataset
) -> None:
    records["prompts"].append(make_prompt("P2"))
    records["responses"].append(make_response("R2A", prompt_id="P2"))
    records["preferences"].append(make_preference("PW2", prompt_id="P1", a="R1A", b="R2A"))
    result = validate_data_dir(write_dataset(records))
    assert any("answers prompt 'P2', not 'P1'" in m for m in _messages(result))


def test_preference_with_unknown_response(records: Records, write_dataset: WriteDataset) -> None:
    records["preferences"].append(make_preference("PW2", b="R404"))
    result = validate_data_dir(write_dataset(records))
    assert any("unknown response 'R404'" in m for m in _messages(result))


def test_all_issues_collected_in_one_pass(records: Records, write_dataset: WriteDataset) -> None:
    records["evaluations"][0]["scores"]["accuracy"] = 9  # schema error
    records["responses"].append(make_response("R9", prompt_id="P9"))  # reference error
    records["preferences"][0]["winner"] = "C"  # schema error
    result = validate_data_dir(write_dataset(records))
    files = {i.file for i in result.errors}
    assert files == {"evaluations.json", "responses.json", "preferences.json"}


def test_duplicate_active_evaluations_rejected(
    records: Records, write_dataset: WriteDataset
) -> None:
    # Two unrelated primary reviews by one reviewer would be double-counted in scores.
    records["evaluations"].append(make_evaluation("E3", "R1A"))
    result = validate_data_dir(write_dataset(records))
    assert any(
        "has 2 active evaluations of this response (E1, E3)" in i.message for i in result.errors
    )


def test_marked_consistency_rereview_is_allowed(
    records: Records, write_dataset: WriteDataset
) -> None:
    records["evaluations"].append(
        make_evaluation("E3", "R1A", schema_version="1.2", consistency_check_of="E1")
    )
    result = validate_data_dir(write_dataset(records))
    assert result.ok, [str(i) for i in result.issues]
    assert [e.evaluation_id for e in result.dataset.active_evaluations] == ["E1", "E2"]


def test_review_before_prompt_creation_warns(records: Records, write_dataset: WriteDataset) -> None:
    records["evaluations"][0]["reviewed_at"] = "2025-12-31"
    result = validate_data_dir(write_dataset(records))
    assert result.ok
    assert any("is before the prompt's created_at" in w.message for w in result.warnings)


def test_secret_like_strings_rejected(records: Records, write_dataset: WriteDataset) -> None:
    # Built at runtime so no credential-shaped literal is committed (avoids secret scanners).
    fake_key = "sk-" + "abcdefghij" * 2
    records["responses"][0]["response_text"] = f"Use key {fake_key} to call it."
    result = validate_data_dir(write_dataset(records))
    assert any("API key" in i.message and i.file == "responses.json" for i in result.errors)


def test_personal_email_rejected_but_reserved_domain_allowed(
    records: Records, write_dataset: WriteDataset
) -> None:
    records["prompts"][0]["reference_notes"] = "Contact jane.doe@gmail.com for details."
    records["responses"][0]["response_text"] = "Write to support@example.com instead."
    result = validate_data_dir(write_dataset(records))
    email_errors = [i for i in result.errors if "email address" in i.message]
    assert len(email_errors) == 1
    assert email_errors[0].file == "prompts.json"
