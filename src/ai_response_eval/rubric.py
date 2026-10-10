"""Machine-readable rubric v1.0: dimensions, error taxonomy and controlled vocabularies.

The human-readable scoring anchors live in ``rubrics/rubric_v1.md``. The two are
versioned together: changing a dimension, label or anchor means bumping
``RUBRIC_VERSION`` so that old evaluations are never silently reinterpreted.

Vocabularies are declared as ``Literal`` types (so Pydantic enforces them) and
exposed as tuples via ``get_args`` so there is exactly one source of truth.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Literal, get_args

RUBRIC_VERSION = "1.0"
SCHEMA_VERSION = "1.2"  # newest record schema; older records remain valid
SUPPORTED_SCHEMA_VERSIONS: tuple[str, ...] = ("1.0", "1.1", "1.2")

SCORE_MIN = 1
SCORE_MAX = 5

# Order matters only for presentation (tables, CSV columns); scoring is order-independent.
DIMENSIONS: tuple[str, ...] = (
    "accuracy",
    "instruction_following",
    "relevance",
    "completeness",
    "reasoning",
    "clarity",
    "safety",
)

# Category -> labels. A label flags a suspected or substantiated issue; it is not proof.
ERROR_TAXONOMY = MappingProxyType(
    {
        "factual": ("incorrect_fact", "incorrect_date", "incorrect_number", "false_attribution"),
        "hallucination": (
            "unsupported_claim",
            "fabricated_citation",
            "fabricated_source",
            "invented_entity",
        ),
        "instruction": ("missing_requirement", "wrong_format", "constraint_violation"),
        "reasoning": ("logic_error", "inconsistent_conclusion", "invalid_calculation"),
        "quality": ("off_topic", "incomplete", "unnecessarily_verbose", "unclear"),
        "calibration": ("overconfident", "fails_to_acknowledge_uncertainty"),
        "safety": ("unsafe_guidance", "missing_necessary_caution"),
    }
)

LABEL_TO_CATEGORY: dict[str, str] = {
    label: category for category, labels in ERROR_TAXONOMY.items() for label in labels
}
ERROR_LABELS: frozenset[str] = frozenset(LABEL_TO_CATEGORY)

EvidenceStatus = Literal["verified", "needs_verification", "not_applicable"]
EVIDENCE_STATUSES: tuple[str, ...] = get_args(EvidenceStatus)

Domain = Literal[
    "general_knowledge",
    "science",
    "history_geography",
    "mathematics",
    "coding",
    "writing",
    "summarization",
    "logical_reasoning",
    "instruction_following",
    "ambiguous",
    "uncertainty",
    "safety",
]
DOMAINS: tuple[str, ...] = get_args(Domain)

# Where a candidate response came from. "synthetic_example" responses were written by
# hand to illustrate the framework; they must not carry a real model name.
Provenance = Literal["synthetic_example", "model_output"]
PROVENANCES: tuple[str, ...] = get_args(Provenance)
EXAMPLE_MODEL_NAME = "example-only"

# Who produced an evaluation or preference. Only "human" records count as genuine
# benchmark annotations; "illustrative_example" records demonstrate the format.
AnnotationSource = Literal["human", "illustrative_example"]
ANNOTATION_SOURCES: tuple[str, ...] = get_args(AnnotationSource)

Winner = Literal["A", "B", "tie"]
WINNERS: tuple[str, ...] = get_args(Winner)

Difficulty = Literal["easy", "moderate", "challenging"]
DIFFICULTIES: tuple[str, ...] = get_args(Difficulty)

# How an authentic model response was obtained (schema 1.1).
CollectionMethod = Literal["web_chat", "api", "local_model", "other"]
COLLECTION_METHODS: tuple[str, ...] = get_args(CollectionMethod)
