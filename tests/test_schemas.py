"""Single-record schema rules: ranges, vocabularies, rationales, dates, provenance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_response_eval.rubric import DIMENSIONS
from ai_response_eval.schemas import CandidateResponse, Evaluation, Preference, Prompt
from tests.conftest import make_evaluation, make_preference, make_prompt, make_response


def _scores(**changes: object) -> dict[str, object]:
    return {d: 4 for d in DIMENSIONS} | changes


@pytest.mark.parametrize("score", [1, 3, 5, None])
def test_valid_scores_accepted(score: int | None) -> None:
    evaluation = Evaluation.model_validate(make_evaluation(scores=_scores(accuracy=score)))
    assert evaluation.scores["accuracy"] == score


@pytest.mark.parametrize("score", [0, 6, -1, 4.0, 4.5, "4", True])
def test_invalid_scores_rejected(score: object) -> None:
    # Floats, numeric strings and booleans are rejected: ratings must be literal integers 1-5.
    with pytest.raises(ValidationError, match=r"scores\.accuracy"):
        Evaluation.model_validate(make_evaluation(scores=_scores(accuracy=score)))


def test_missing_dimension_rejected() -> None:
    scores = _scores()
    del scores["safety"]
    with pytest.raises(ValidationError, match="missing dimensions: safety"):
        Evaluation.model_validate(make_evaluation(scores=scores))


def test_unknown_dimension_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown dimensions: helpfulness"):
        Evaluation.model_validate(make_evaluation(scores=_scores(helpfulness=3)))


def test_rationale_required_even_for_null_score() -> None:
    record = make_evaluation(scores=_scores(safety=None))
    record["score_rationales"]["safety"] = "   "
    with pytest.raises(ValidationError, match="empty: safety"):
        Evaluation.model_validate(record)


def test_missing_rationale_key_rejected() -> None:
    record = make_evaluation()
    del record["score_rationales"]["clarity"]
    with pytest.raises(ValidationError, match="missing dimensions: clarity"):
        Evaluation.model_validate(record)


def test_unknown_error_label_rejected_with_suggestion() -> None:
    record = make_evaluation(
        errors=[{"label": "incorect_fact", "evidence_status": "not_applicable", "note": "x"}]
    )
    with pytest.raises(ValidationError, match="did you mean 'incorrect_fact'"):
        Evaluation.model_validate(record)


def test_invalid_evidence_status_rejected() -> None:
    record = make_evaluation(
        errors=[{"label": "incorrect_fact", "evidence_status": "probably", "note": "x"}]
    )
    with pytest.raises(ValidationError, match="evidence_status"):
        Evaluation.model_validate(record)


def test_verified_error_requires_source() -> None:
    record = make_evaluation(
        errors=[{"label": "incorrect_fact", "evidence_status": "verified", "note": "x"}]
    )
    with pytest.raises(ValidationError, match="requires a source"):
        Evaluation.model_validate(record)


def test_needs_verification_error_may_omit_source() -> None:
    record = make_evaluation(
        errors=[
            {"label": "unsupported_claim", "evidence_status": "needs_verification", "note": "x"}
        ]
    )
    assert Evaluation.model_validate(record).errors[0].category == "hallucination"


@pytest.mark.parametrize(
    "value", ["10/09/2026", "2026-2-1", "2026-02-30", 20260101, "2026-01-01T00:00"]
)
def test_dates_must_be_valid_iso_strings(value: object) -> None:
    with pytest.raises(ValidationError, match="reviewed_at"):
        Evaluation.model_validate(make_evaluation(reviewed_at=value))


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="reviwer_id"):
        Evaluation.model_validate(make_evaluation(reviwer_id="typo"))


def test_wrong_schema_version_rejected() -> None:
    with pytest.raises(ValidationError, match="schema_version"):
        Prompt.model_validate(make_prompt(schema_version="2.0"))


def test_unknown_domain_rejected() -> None:
    with pytest.raises(ValidationError, match="domain"):
        Prompt.model_validate(make_prompt(domain="astrology"))


@pytest.mark.parametrize("text", ["", "   \n"])
def test_empty_response_text_rejected(text: str) -> None:
    with pytest.raises(ValidationError, match="response_text"):
        CandidateResponse.model_validate(make_response(response_text=text))


def test_synthetic_example_cannot_claim_real_model() -> None:
    with pytest.raises(ValidationError, match="synthetic_example responses must use"):
        CandidateResponse.model_validate(make_response(model_name="some-real-model"))


def test_model_output_requires_model_name_and_date() -> None:
    with pytest.raises(ValidationError, match="generated_at"):
        CandidateResponse.model_validate(
            make_response(provenance="model_output", model_name="vendor-model-x")
        )
    ok = CandidateResponse.model_validate(
        make_response(
            provenance="model_output", model_name="vendor-model-x", generated_at="2026-01-01"
        )
    )
    assert ok.provenance == "model_output"


@pytest.mark.parametrize("winner", ["A", "B", "tie"])
def test_valid_winners(winner: str) -> None:
    assert Preference.model_validate(make_preference(winner=winner)).winner == winner


@pytest.mark.parametrize("winner", ["a", "both", "", None])
def test_invalid_winner_rejected(winner: object) -> None:
    with pytest.raises(ValidationError, match="winner"):
        Preference.model_validate(make_preference(winner=winner))


def test_preference_rejects_same_response_twice() -> None:
    with pytest.raises(ValidationError, match="two different responses"):
        Preference.model_validate(make_preference(a="R1A", b="R1A"))


def test_preference_requires_reason() -> None:
    with pytest.raises(ValidationError, match="reason"):
        Preference.model_validate(make_preference(reason=" "))
