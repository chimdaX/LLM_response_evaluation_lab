"""Typed record schemas for prompts, candidate responses, evaluations and preferences.

These models enforce everything that can be checked within a *single* record
(types, ranges, controlled vocabularies, rationale completeness). Checks that
need more than one record -- unique IDs, references between files -- live in
``validation.py``.

All models forbid unknown fields, so a typo such as ``"acuracy"`` or
``"reviwer_id"`` fails loudly instead of being silently ignored.
"""

from __future__ import annotations

import difflib
import re
from datetime import date
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ai_response_eval.rubric import (
    DIMENSIONS,
    EXAMPLE_MODEL_NAME,
    LABEL_TO_CATEGORY,
    SCORE_MAX,
    SCORE_MIN,
    AnnotationSource,
    CollectionMethod,
    Difficulty,
    Domain,
    EvidenceStatus,
    Provenance,
    Winner,
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_iso_date(value: object) -> date:
    """Accept only ``YYYY-MM-DD`` strings so every file uses one date format.

    Pydantic's default date parsing is lenient (it also accepts Unix
    timestamps, for example); annotation files should be stricter than that.
    """
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        raise ValueError("must be a date string in YYYY-MM-DD format")
    return date.fromisoformat(value)  # also rejects impossible dates such as 2026-02-30


def _require_text(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be empty or whitespace")
    return value


IsoDate = Annotated[date, BeforeValidator(_parse_iso_date)]
NonEmptyText = Annotated[str, AfterValidator(_require_text)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", max_length=64)]
# strict=True rejects 4.0, "4" and True: a rating must be a literal integer.
Score = Annotated[int, Field(ge=SCORE_MIN, le=SCORE_MAX, strict=True)]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Each version only ADDS optional fields; nothing is removed or redefined, so every
    # valid record of an older version is still valid.
    #   1.1: prompt metadata (difficulty, objectives) and response collection metadata
    #   1.2: evaluation corrections (supersedes, revision_reason) and consistency
    #        re-reviews (consistency_check_of)
    schema_version: Literal["1.0", "1.1", "1.2"]

    def _require_version(self, minimum: str, *fields: str) -> None:
        """Reject fields introduced in ``minimum`` on records declaring an older version."""
        if tuple(map(int, self.schema_version.split("."))) < tuple(map(int, minimum.split("."))):
            used = [f for f in fields if f in self.model_fields_set]
            if used:
                raise ValueError(
                    f"field(s) {', '.join(used)} require schema_version '{minimum}' or later"
                )


class Prompt(_Record):
    prompt_id: Identifier
    domain: Domain
    prompt: NonEmptyText
    constraints: list[NonEmptyText] = Field(default_factory=list)
    reference_notes: str | None = None
    created_at: IsoDate
    # Schema 1.1 (optional): intended difficulty and what the prompt is designed to test.
    difficulty: Difficulty | None = None
    evaluation_objectives: list[NonEmptyText] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_version_fields(self) -> Prompt:
        self._require_version("1.1", "difficulty", "evaluation_objectives")
        return self


class CandidateResponse(_Record):
    response_id: Identifier
    prompt_id: Identifier
    candidate_label: NonEmptyText
    response_text: NonEmptyText
    model_name: NonEmptyText
    provenance: Provenance
    generated_at: IsoDate | None = None
    # Schema 1.1 (optional): how an authentic response was collected. Record only what is
    # actually known; leave a field null rather than guessing (e.g. an unexposed temperature).
    provider: NonEmptyText | None = None
    collection_method: CollectionMethod | None = None
    generation_settings: NonEmptyText | None = None

    @model_validator(mode="after")
    def _check_provenance(self) -> CandidateResponse:
        self._require_version("1.1", "provider", "collection_method", "generation_settings")
        # Guard against attributing hand-written examples to a real model and vice versa.
        if self.provenance == "synthetic_example" and self.model_name != EXAMPLE_MODEL_NAME:
            raise ValueError(
                f"synthetic_example responses must use model_name '{EXAMPLE_MODEL_NAME}'; "
                "only name a real model when the text genuinely came from it"
            )
        if self.provenance == "model_output":
            if self.model_name == EXAMPLE_MODEL_NAME:
                raise ValueError("model_output responses must record the real model name")
            if self.generated_at is None:
                raise ValueError("model_output responses must record generated_at")
        return self


class ErrorAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    evidence_status: EvidenceStatus
    note: NonEmptyText
    source: str | None = None

    @field_validator("label")
    @classmethod
    def _known_label(cls, value: str) -> str:
        if value not in LABEL_TO_CATEGORY:
            hint = difflib.get_close_matches(value, LABEL_TO_CATEGORY, n=1)
            suggestion = f" (did you mean '{hint[0]}'?)" if hint else ""
            raise ValueError(f"'{value}' is not in the rubric error taxonomy{suggestion}")
        return value

    @model_validator(mode="after")
    def _verified_needs_source(self) -> ErrorAnnotation:
        if self.evidence_status == "verified" and not (self.source and self.source.strip()):
            raise ValueError("evidence_status 'verified' requires a source describing the check")
        return self

    @property
    def category(self) -> str:
        return LABEL_TO_CATEGORY[self.label]


class Evaluation(_Record):
    evaluation_id: Identifier
    prompt_id: Identifier
    response_id: Identifier
    reviewer_id: Identifier
    annotation_source: AnnotationSource
    rubric_version: Literal["1.0"]
    scores: dict[str, Score | None]
    score_rationales: dict[str, str]
    errors: list[ErrorAnnotation]
    overall_rationale: NonEmptyText
    improved_response: str | None = None
    reviewed_at: IsoDate
    # Schema 1.2 (optional). A correction is a NEW record that replaces an earlier one;
    # the earlier record is kept unchanged as revision history.
    supersedes: Identifier | None = None
    revision_reason: NonEmptyText | None = None
    # Schema 1.2 (optional). A deliberate re-review of the same response by the same
    # reviewer, kept for consistency analysis and excluded from scoring.
    consistency_check_of: Identifier | None = None

    @model_validator(mode="after")
    def _check_revision_fields(self) -> Evaluation:
        self._require_version("1.2", "supersedes", "revision_reason", "consistency_check_of")
        if (self.supersedes is None) != (self.revision_reason is None):
            raise ValueError("supersedes and revision_reason must be given together")
        if self.supersedes is not None and self.consistency_check_of is not None:
            raise ValueError("a record cannot be both a correction and a consistency re-review")
        if self.evaluation_id in (self.supersedes, self.consistency_check_of):
            raise ValueError("an evaluation cannot reference itself")
        return self

    @field_validator("scores")
    @classmethod
    def _all_dimensions_present(cls, scores: dict[str, int | None]) -> dict[str, int | None]:
        # Every dimension must be addressed explicitly: either a 1-5 rating or null.
        # A missing key would be ambiguous ("forgot" vs. "not applicable").
        _check_keys(scores, "scores")
        return scores

    @model_validator(mode="after")
    def _every_dimension_has_rationale(self) -> Evaluation:
        _check_keys(self.score_rationales, "score_rationales")
        empty = [d for d in DIMENSIONS if not self.score_rationales[d].strip()]
        if empty:
            raise ValueError(
                "score_rationales must be non-empty for every dimension, including null "
                f"scores (explain why it was not assessed); empty: {', '.join(empty)}"
            )
        return self

    @property
    def error_labels(self) -> tuple[str, ...]:
        return tuple(sorted({e.label for e in self.errors}))


def _check_keys(mapping: dict[str, object], field: str) -> None:
    missing = [d for d in DIMENSIONS if d not in mapping]
    unknown = sorted(set(mapping) - set(DIMENSIONS))
    problems = []
    if missing:
        problems.append(f"missing dimensions: {', '.join(missing)}")
    if unknown:
        problems.append(f"unknown dimensions: {', '.join(unknown)}")
    if problems:
        raise ValueError(
            f"{field} must contain exactly the rubric v1.0 dimensions ({'; '.join(problems)})"
        )


class Preference(_Record):
    preference_id: Identifier
    prompt_id: Identifier
    response_a_id: Identifier
    response_b_id: Identifier
    reviewer_id: Identifier
    annotation_source: AnnotationSource
    winner: Winner
    reason: NonEmptyText
    rubric_version: Literal["1.0"]
    reviewed_at: IsoDate

    @model_validator(mode="after")
    def _distinct_responses(self) -> Preference:
        if self.response_a_id == self.response_b_id:
            raise ValueError("a preference must compare two different responses")
        return self
