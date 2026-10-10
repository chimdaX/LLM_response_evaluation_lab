"""Benchmark progress: what has been collected and annotated, and what is still pending.

These are *progress counts*, not results. They never include scores, so an
incomplete benchmark cannot be mistaken for a finished evaluation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ai_response_eval.annotation import candidate_pairs
from ai_response_eval.collection import CANDIDATE_LABELS, pending_slots
from ai_response_eval.storage import DraftStore
from ai_response_eval.validation import Dataset


@dataclass(frozen=True)
class BenchmarkProgress:
    prompts: int
    expected_responses: int
    collected_responses: int
    responses_by_provenance: dict[str, int]
    pending_response_ids: list[str]
    human_evaluations: int
    responses_with_human_evaluation: int
    non_human_evaluations: int
    unevaluated_response_ids: list[str]
    complete_pairs: int
    human_preferences: int
    pairs_with_human_preference: int
    non_human_preferences: int
    superseded_evaluations: int = 0
    consistency_rereviews: int = 0
    drafts: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """Every slot collected, every response human-evaluated, every pair compared."""
        return (
            self.prompts > 0
            and not self.pending_response_ids
            and not self.unevaluated_response_ids
            and self.pairs_with_human_preference == self.complete_pairs == self.prompts
        )


def compute_progress(dataset: Dataset, drafts: DraftStore | None = None) -> BenchmarkProgress:
    active = dataset.active_evaluations
    human_evals = [e for e in active if e.annotation_source == "human"]
    evaluated = {e.response_id for e in human_evals}
    human_prefs = [p for p in dataset.preferences if p.annotation_source == "human"]
    compared = {(p.response_a_id, p.response_b_id) for p in human_prefs}
    pairs = candidate_pairs(dataset)
    return BenchmarkProgress(
        prompts=len(dataset.prompts),
        expected_responses=len(dataset.prompts) * len(CANDIDATE_LABELS),
        collected_responses=len(dataset.responses),
        responses_by_provenance=dict(
            sorted(Counter(r.provenance for r in dataset.responses).items())
        ),
        pending_response_ids=[s.response_id for s in pending_slots(dataset)],
        human_evaluations=len(human_evals),
        responses_with_human_evaluation=len(evaluated & set(dataset.responses_by_id)),
        non_human_evaluations=len(active) - len(human_evals),
        superseded_evaluations=len(dataset.superseded_ids),
        consistency_rereviews=len(dataset.consistency_checks),
        unevaluated_response_ids=sorted(set(dataset.responses_by_id) - evaluated),
        complete_pairs=len(pairs),
        human_preferences=len(human_prefs),
        pairs_with_human_preference=sum(
            (p.a.response_id, p.b.response_id) in compared for p in pairs
        ),
        non_human_preferences=len(dataset.preferences) - len(human_prefs),
        drafts=drafts.keys() if drafts else [],
    )


def _ids(ids: list[str], limit: int = 12) -> str:
    if not ids:
        return "none"
    shown = ", ".join(ids[:limit])
    return shown + (f", ... (+{len(ids) - limit} more)" if len(ids) > limit else "")


def format_progress(p: BenchmarkProgress) -> str:
    provenance = ", ".join(f"{k}: {v}" for k, v in p.responses_by_provenance.items()) or "none"
    lines = [
        "Benchmark progress (counts only -- no scores are reported until annotation is complete)",
        "",
        f"  Prompts:                           {p.prompts}",
        f"  Responses collected:               {p.collected_responses} of {p.expected_responses} "
        f"slots ({provenance})",
        f"  Responses with a human evaluation: {p.responses_with_human_evaluation} of "
        f"{p.collected_responses} collected ({p.human_evaluations} human evaluation records)",
        f"  Pairs with a human preference:     {p.pairs_with_human_preference} of "
        f"{p.complete_pairs} complete pairs ({p.human_preferences} human preference records)",
    ]
    if p.non_human_evaluations or p.non_human_preferences:
        lines.append(
            f"  Non-human records (not counted):   {p.non_human_evaluations} evaluations, "
            f"{p.non_human_preferences} preferences"
        )
    if p.superseded_evaluations or p.consistency_rereviews:
        lines.append(
            f"  Revision history (not counted):    {p.superseded_evaluations} superseded, "
            f"{p.consistency_rereviews} consistency re-reviews"
        )
    lines += [
        "",
        f"  Pending responses:    {_ids(p.pending_response_ids)}",
        f"  Awaiting evaluation:  {_ids(p.unevaluated_response_ids)}",
        f"  Drafts in progress:   {_ids(p.drafts)}",
        "",
        "  Status: " + ("COMPLETE" if p.is_complete else "INCOMPLETE -- do not report results yet"),
    ]
    return "\n".join(lines)
