"""Schema 1.1 compatibility, storage safety, progress tracking, and the committed benchmark."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_response_eval.progress import compute_progress, format_progress
from ai_response_eval.schemas import CandidateResponse, Prompt
from ai_response_eval.storage import DraftStore, StorageError, append_record, next_id
from ai_response_eval.validation import validate_data_dir
from tests.conftest import (
    BENCHMARK_DIR,
    Records,
    benchmark_records,
    make_evaluation,
    make_model_response,
    make_preference,
    make_prompt,
    make_response,
    write_records,
)

# --- schema 1.1 ----------------------------------------------------------------------------


def test_v10_records_remain_valid() -> None:
    assert Prompt.model_validate(make_prompt()).schema_version == "1.0"
    assert CandidateResponse.model_validate(make_response()).provider is None


def test_v11_fields_accepted() -> None:
    prompt = Prompt.model_validate(
        make_prompt(schema_version="1.1", difficulty="challenging", evaluation_objectives=["x"])
    )
    assert prompt.difficulty == "challenging"
    response = CandidateResponse.model_validate(make_model_response())
    assert response.collection_method == "web_chat"


@pytest.mark.parametrize(
    ("factory", "field", "value"),
    [
        (make_prompt, "difficulty", "easy"),
        (make_prompt, "evaluation_objectives", ["x"]),
        (make_response, "provider", "Vendor"),
        (make_response, "collection_method", "api"),
    ],
)
def test_v11_fields_rejected_on_v10_records(factory, field: str, value: object) -> None:
    schema = Prompt if factory is make_prompt else CandidateResponse
    with pytest.raises(ValidationError, match=r"require schema_version '1\.1'"):
        schema.model_validate(factory(**{field: value}))


@pytest.mark.parametrize(
    ("record", "field"),
    [
        (make_prompt(schema_version="1.1", difficulty="impossible"), "difficulty"),
        (make_model_response(collection_method="scraped"), "collection_method"),
        (make_model_response(generated_at=None), "generated_at"),
        (make_model_response(model_name="example-only"), "real model name"),
    ],
)
def test_v11_invalid_values(record: dict, field: str) -> None:
    schema = Prompt if "prompt" in record and "response_text" not in record else CandidateResponse
    with pytest.raises(ValidationError, match=field):
        schema.model_validate(record)


# --- committed benchmark -----------------------------------------------------------------


def test_committed_benchmark_is_valid_and_unannotated() -> None:
    result = validate_data_dir(BENCHMARK_DIR)
    assert result.ok, [str(i) for i in result.errors]
    d = result.dataset
    assert len(d.prompts) == 20
    # Integrity: nothing may be pre-filled on behalf of the human evaluator.
    assert d.responses == [] and d.evaluations == [] and d.preferences == []


def test_benchmark_prompts_are_diverse_and_documented() -> None:
    prompts = validate_data_dir(BENCHMARK_DIR).dataset.prompts
    assert len({p.prompt_id for p in prompts}) == 20
    assert len(Counter(p.domain for p in prompts)) >= 8
    assert {p.difficulty for p in prompts} == {"easy", "moderate", "challenging"}
    for p in prompts:
        assert p.reference_notes and p.evaluation_objectives, p.prompt_id


# --- storage --------------------------------------------------------------------------------


def test_append_record_refuses_duplicates_and_preserves_existing(tmp_path: Path) -> None:
    path = tmp_path / "evaluations.json"
    append_record(path, {"evaluation_id": "EV0001", "x": 1}, "evaluation_id")
    with pytest.raises(StorageError, match="already contains"):
        append_record(path, {"evaluation_id": "EV0001", "x": 2}, "evaluation_id")
    append_record(path, {"evaluation_id": "EV0002"}, "evaluation_id")
    assert json.loads(path.read_text(encoding="utf-8")) == [
        {"evaluation_id": "EV0001", "x": 1},
        {"evaluation_id": "EV0002"},
    ]
    assert list(tmp_path.iterdir()) == [path]  # no temp files left behind


def test_append_record_refuses_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "evaluations.json"
    path.write_text("[{", encoding="utf-8")
    with pytest.raises(StorageError, match="not valid JSON"):
        append_record(path, {"evaluation_id": "EV0001"}, "evaluation_id")
    assert path.read_text(encoding="utf-8") == "[{"


def test_next_id_fills_first_gap(tmp_path: Path) -> None:
    path = tmp_path / "e.json"
    assert next_id(path, "evaluation_id", "EV") == "EV0001"
    path.write_text(json.dumps([{"evaluation_id": "EV0001"}, {"evaluation_id": "EV0003"}]), "utf-8")
    assert next_id(path, "evaluation_id", "EV") == "EV0002"


def test_draft_store_round_trip(tmp_path: Path) -> None:
    drafts = DraftStore(tmp_path)
    assert drafts.load("k") is None
    drafts.save("evaluation__r__X", {"scores": {"accuracy": 3}})
    assert drafts.load("evaluation__r__X") == {"scores": {"accuracy": 3}}
    assert drafts.keys("evaluation__") == ["evaluation__r__X"]
    drafts.delete("evaluation__r__X")
    assert drafts.keys() == []


# --- progress ---------------------------------------------------------------------------------


def _progress(tmp_path: Path, records: Records):
    data_dir = write_records(tmp_path / "d", records)
    return compute_progress(validate_data_dir(data_dir).dataset, DraftStore(data_dir))


def test_progress_of_partial_benchmark(tmp_path: Path) -> None:
    p = _progress(tmp_path, benchmark_records())
    assert (p.prompts, p.expected_responses, p.collected_responses) == (2, 4, 2)
    assert p.pending_response_ids == ["P2-A", "P2-B"]
    assert p.unevaluated_response_ids == ["P1-A", "P1-B"]
    assert (p.complete_pairs, p.pairs_with_human_preference) == (1, 0)
    assert not p.is_complete
    assert "INCOMPLETE" in format_progress(p)


def test_progress_ignores_non_human_annotations(tmp_path: Path) -> None:
    records = benchmark_records()
    records["evaluations"] = [make_evaluation("E1", "P1-A")]  # illustrative_example
    p = _progress(tmp_path, records)
    assert p.human_evaluations == 0
    assert p.non_human_evaluations == 1
    assert "P1-A" in p.unevaluated_response_ids


def test_progress_complete(tmp_path: Path) -> None:
    records = benchmark_records()
    records["prompts"] = records["prompts"][:1]
    records["evaluations"] = [
        make_evaluation("E1", "P1-A", annotation_source="human"),
        make_evaluation("E2", "P1-B", annotation_source="human"),
    ]
    records["preferences"] = [make_preference(a="P1-A", b="P1-B", annotation_source="human")]
    p = _progress(tmp_path, records)
    assert p.is_complete
    assert "COMPLETE" in format_progress(p)


def test_empty_benchmark_is_not_complete(tmp_path: Path) -> None:
    empty: Records = {"prompts": [], "responses": [], "evaluations": [], "preferences": []}
    assert not _progress(tmp_path, empty).is_complete
