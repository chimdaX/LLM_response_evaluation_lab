"""Deterministic score aggregation and review flags.

Scoring policy (rubric v1.0):

* ``overall = sum(s_i * w_i) / sum(w_i)`` over the dimensions that were actually
  scored. A ``null`` score means "not assessed", so it is dropped from both the
  numerator *and* the denominator -- it is never treated as zero.
* Nothing is rounded here. Rounding happens only when values are displayed.
* The overall number is a convenience summary of ordinal ratings, not a pass/fail
  verdict. Separately, review *flags* make critical problems visible no matter
  how high the average is (e.g. accuracy 1 with every other dimension at 5).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, ValidationError, model_validator

from ai_response_eval.rubric import DIMENSIONS, ERROR_LABELS, SCORE_MAX, SCORE_MIN
from ai_response_eval.schemas import Evaluation
from ai_response_eval.validation import Dataset


class ConfigError(ValueError):
    """Raised when the scoring configuration file is missing or invalid."""


class ReviewFlagPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    critical_dimensions: tuple[str, ...]
    critical_score_threshold: int = Field(ge=SCORE_MIN, le=SCORE_MAX)
    critical_error_labels: tuple[str, ...]
    flag_needs_verification: bool

    @model_validator(mode="after")
    def _known_names(self) -> ReviewFlagPolicy:
        unknown_dims = sorted(set(self.critical_dimensions) - set(DIMENSIONS))
        unknown_labels = sorted(set(self.critical_error_labels) - ERROR_LABELS)
        if unknown_dims:
            raise ValueError(f"unknown critical_dimensions: {', '.join(unknown_dims)}")
        if unknown_labels:
            raise ValueError(f"unknown critical_error_labels: {', '.join(unknown_labels)}")
        return self


class ScoringConfig(BaseModel):
    """Versioned scoring configuration (``config/scoring.json``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    config_version: str
    rubric_version: Literal["1.0"]
    weights: dict[str, PositiveFloat]
    display_decimals: int = Field(ge=0, le=6)
    review_flags: ReviewFlagPolicy
    pairwise_tie_margin: float = Field(ge=0)

    @model_validator(mode="after")
    def _weights_cover_rubric(self) -> ScoringConfig:
        if set(self.weights) != set(DIMENSIONS):
            missing = sorted(set(DIMENSIONS) - set(self.weights))
            unknown = sorted(set(self.weights) - set(DIMENSIONS))
            raise ValueError(
                f"weights must cover exactly the rubric dimensions (missing: {missing or 'none'}; "
                f"unknown: {unknown or 'none'})"
            )
        return self


def load_scoring_config(path: Path) -> ScoringConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ConfigError(f"scoring config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON at line {exc.lineno}: {exc.msg}") from exc
    try:
        return ScoringConfig.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors()
        )
        raise ConfigError(f"{path}: invalid scoring config: {details}") from exc


def weighted_overall(
    scores: Mapping[str, int | None], weights: Mapping[str, float]
) -> float | None:
    """Weighted mean of the non-null scores, or ``None`` if nothing was scored.

    ``math.fsum`` is correctly rounded, so the result does not depend on the
    iteration order of ``scores`` -- the same data always gives the same number.
    """
    numerator: list[float] = []
    denominator: list[float] = []
    for dimension, score in scores.items():
        if score is None:
            continue
        if (
            isinstance(score, bool)
            or not isinstance(score, int)
            or not (SCORE_MIN <= score <= SCORE_MAX)
        ):
            raise ValueError(f"{dimension}: score must be an integer {SCORE_MIN}-{SCORE_MAX}")
        if dimension not in weights:
            raise ValueError(f"no weight configured for dimension '{dimension}'")
        numerator.append(score * weights[dimension])
        denominator.append(weights[dimension])
    if not denominator:
        return None
    return math.fsum(numerator) / math.fsum(denominator)


@dataclass(frozen=True, order=True)
class ReviewFlag:
    """A reason an evaluation needs human attention. A flag is not a verdict."""

    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}({self.detail})"


def review_flags(evaluation: Evaluation, policy: ReviewFlagPolicy) -> tuple[ReviewFlag, ...]:
    flags: set[ReviewFlag] = set()
    for dimension in policy.critical_dimensions:
        score = evaluation.scores.get(dimension)
        if score is not None and score <= policy.critical_score_threshold:
            flags.add(ReviewFlag("low_critical_score", f"{dimension}={score}"))
    for error in evaluation.errors:
        if error.label in policy.critical_error_labels:
            flags.add(ReviewFlag("critical_error", error.label))
        if policy.flag_needs_verification and error.evidence_status == "needs_verification":
            flags.add(ReviewFlag("needs_verification", error.label))
    if all(score is None for score in evaluation.scores.values()):
        flags.add(ReviewFlag("no_scored_dimensions", "all dimensions null"))
    return tuple(sorted(flags))


@dataclass(frozen=True)
class ScoredEvaluation:
    evaluation: Evaluation
    domain: str
    response_provenance: str
    overall: float | None
    n_scored: int
    flags: tuple[ReviewFlag, ...]

    @property
    def needs_review(self) -> bool:
        return bool(self.flags)


def score_evaluations(dataset: Dataset, config: ScoringConfig) -> list[ScoredEvaluation]:
    """Score every evaluation of a *validated* dataset, sorted by evaluation_id."""
    results = []
    for evaluation in dataset.evaluations:
        response = dataset.responses_by_id[evaluation.response_id]
        prompt = dataset.prompts_by_id[response.prompt_id]
        results.append(
            ScoredEvaluation(
                evaluation=evaluation,
                domain=prompt.domain,
                response_provenance=response.provenance,
                overall=weighted_overall(evaluation.scores, config.weights),
                n_scored=sum(s is not None for s in evaluation.scores.values()),
                flags=review_flags(evaluation, config.review_flags),
            )
        )
    return sorted(results, key=lambda s: s.evaluation.evaluation_id)


def format_score(value: float | None, decimals: int) -> str:
    """Display helper: the only place scores are rounded."""
    return "n/a" if value is None else f"{value:.{decimals}f}"
