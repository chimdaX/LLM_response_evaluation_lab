"""Pairwise preferences: human-recorded decisions plus an explicitly labelled score suggestion.

The *human-recorded preference* is the judgment of record. The *score-based
suggestion* is computed by this program from the single-response evaluations
and exists only as a consistency check: a disagreement is a prompt to re-read
both responses, not evidence that the reviewer was wrong. The suggestion is
never written back into the preference data.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean
from typing import Literal

from ai_response_eval.schemas import Preference
from ai_response_eval.scoring import ScoredEvaluation, ScoringConfig
from ai_response_eval.validation import Dataset

Suggestion = Literal["A", "B", "tie"]
Agreement = Literal["agree", "disagree", "n/a"]


def mean_overall_by_response(scored: list[ScoredEvaluation]) -> dict[str, float]:
    """Mean overall score per response, across all evaluations that produced one."""
    values: dict[str, list[float]] = defaultdict(list)
    for s in scored:
        if s.overall is not None:
            values[s.evaluation.response_id].append(s.overall)
    return {response_id: fmean(v) for response_id, v in values.items()}


def score_based_suggestion(
    a_overall: float | None, b_overall: float | None, tie_margin: float
) -> Suggestion | None:
    """Suggest A, B or tie from overall scores; ``None`` when either side is unscored.

    Differences within ``tie_margin`` are treated as a tie because small gaps in
    averaged ordinal ratings are not meaningful.
    """
    if a_overall is None or b_overall is None:
        return None
    difference = a_overall - b_overall
    if abs(difference) <= tie_margin:
        return "tie"
    return "A" if difference > 0 else "B"


@dataclass(frozen=True)
class PairwiseRow:
    preference: Preference
    domain: str
    a_overall: float | None
    b_overall: float | None
    score_suggestion: Suggestion | None

    @property
    def human_winner(self) -> str:
        return self.preference.winner

    @property
    def winner_response_id(self) -> str | None:
        return {
            "A": self.preference.response_a_id,
            "B": self.preference.response_b_id,
        }.get(self.preference.winner)

    @property
    def agreement(self) -> Agreement:
        if self.score_suggestion is None:
            return "n/a"
        return "agree" if self.score_suggestion == self.preference.winner else "disagree"


def build_pairwise_rows(
    dataset: Dataset, scored: list[ScoredEvaluation], config: ScoringConfig
) -> list[PairwiseRow]:
    means = mean_overall_by_response(scored)
    rows = []
    for pref in dataset.preferences:
        a = means.get(pref.response_a_id)
        b = means.get(pref.response_b_id)
        rows.append(
            PairwiseRow(
                preference=pref,
                domain=dataset.prompts_by_id[pref.prompt_id].domain,
                a_overall=a,
                b_overall=b,
                score_suggestion=score_based_suggestion(a, b, config.pairwise_tie_margin),
            )
        )
    return sorted(rows, key=lambda r: r.preference.preference_id)


@dataclass(frozen=True)
class PairwiseSummary:
    decisions: int
    a_wins: int
    b_wins: int
    ties: int
    with_suggestion: int
    agreements: int


def summarize_pairwise(rows: list[PairwiseRow]) -> PairwiseSummary:
    return PairwiseSummary(
        decisions=len(rows),
        a_wins=sum(r.human_winner == "A" for r in rows),
        b_wins=sum(r.human_winner == "B" for r in rows),
        ties=sum(r.human_winner == "tie" for r in rows),
        with_suggestion=sum(r.score_suggestion is not None for r in rows),
        agreements=sum(r.agreement == "agree" for r in rows),
    )
