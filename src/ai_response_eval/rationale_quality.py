"""Content-based checks that catch rationales which do not explain anything.

These are deliberately *not* length checks. A short rationale such as "Omits the
2100 exception." is specific and passes; a long one such as "Overall the response is
pretty good and quite clear" names nothing observable and is flagged.

The checks look for three things:

* **Score-like text** -- only a number or rating ("4", "4/5", "score: 4").
* **Placeholders** -- "n/a", "ok", "same", "as above", "tbd", ...
* **No specific content** -- after removing function words ("the", "is") and generic
  evaluative vocabulary ("good", "okay", "response", "accuracy"), fewer than two
  distinct content words remain.

Passing these checks does not make a rationale good; it only means it is not an
obvious non-explanation. Judging rationale quality remains a human responsibility.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from ai_response_eval.rubric import DIMENSIONS

Severity = Literal["blocking", "warning"]

_SCORE_LIKE = re.compile(
    r"^\s*(?:score|rating|rated|scored)?\s*[:=]?\s*\d+(?:\.\d+)?\s*"
    r"(?:/\s*\d+|out\s+of\s+\d+)?\s*[.!]?\s*$",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")

PLACEHOLDERS = frozenset(
    {
        "n/a", "na", "none", "nothing", "-", "--", "...", ".", "?", "x", "ok", "okay",
        "fine", "good", "bad", "yes", "no", "same", "same as above", "as above",
        "see above", "ditto", "tbd", "todo", "idk", "test", "asdf", "nil", "null",
    }
)  # fmt: skip


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


STOPWORDS = _words(
    """a an the is are was were be been being am of in on at to for with by from as and or
    but if then so than that this these those it its it's i we you he she they them my our
    your his her their me us do does did done has have had having not no nor yes can could
    should would will just also too there here which who what when where why how all any
    each both few more most other such only own same into over under again further once
    about above below up down out off very s t"""
)
# Words that describe a judgment without saying what was observed.
GENERIC = _words(
    """ok okay fine good great nice decent bad poor excellent perfect solid acceptable
    reasonable adequate satisfactory alright awesome amazing terrible weak strong correct
    incorrect accurate inaccurate right wrong clear unclear relevant irrelevant complete
    incomplete safe unsafe well better best worse worst overall generally mostly pretty
    quite really fairly somewhat bit little response responses answer answers output
    outputs model models text reply score scored rating rated dimension job everything
    seems seemed looks looked think thought feel felt stuff thing things something
    anything etc"""
) | {part for d in DIMENSIONS for part in d.split("_")}

MIN_CONTENT_WORDS = 2
DUPLICATE_THRESHOLD = 3


@dataclass(frozen=True)
class RationaleIssue:
    code: str
    severity: Severity
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def content_words(text: str) -> set[str]:
    """Distinct words that are neither function words nor generic evaluative vocabulary."""
    tokens = _TOKEN.findall(text.lower())
    return {t for t in tokens if t not in STOPWORDS and t not in GENERIC}


def check_rationale(text: str) -> list[RationaleIssue]:
    """Return problems with one rationale; an empty list means no obvious problem."""
    normalized = " ".join(text.strip().lower().split())
    if _SCORE_LIKE.match(normalized):
        return [
            RationaleIssue(
                "numeric_only",
                "blocking",
                "contains only a number or rating; explain what you observed, not the score",
            )
        ]
    if normalized.rstrip(".!") in PLACEHOLDERS or normalized in PLACEHOLDERS:
        return [
            RationaleIssue(
                "placeholder",
                "blocking",
                f"'{text.strip()}' is a placeholder, not an explanation",
            )
        ]
    if len(content_words(normalized)) < MIN_CONTENT_WORDS:
        return [
            RationaleIssue(
                "no_specific_content",
                "warning",
                "names no specific observation (which claim, requirement, step or passage?); "
                "generic words such as 'okay', 'good' or 'clear' do not explain a score",
            )
        ]
    return []


def repeated_rationales(rationales: Mapping[str, str]) -> list[tuple[str, list[str]]]:
    """Rationale texts reused verbatim for DUPLICATE_THRESHOLD or more dimensions."""
    groups: dict[str, list[str]] = defaultdict(list)
    for dimension, text in rationales.items():
        groups[" ".join(text.strip().lower().split())].append(dimension)
    return [(text, dims) for text, dims in groups.items() if len(dims) >= DUPLICATE_THRESHOLD]


def evaluation_issues(
    score_rationales: Mapping[str, str], overall_rationale: str
) -> list[tuple[str, RationaleIssue]]:
    """All rationale problems of one evaluation as (field path, issue) pairs."""
    found = [
        (f"score_rationales.{d}", issue)
        for d in DIMENSIONS
        if d in score_rationales
        for issue in check_rationale(score_rationales[d])
    ]
    found += [("overall_rationale", issue) for issue in check_rationale(overall_rationale)]
    for text, dims in repeated_rationales(score_rationales):
        found.append(
            (
                "score_rationales",
                RationaleIssue(
                    "repeated_rationale",
                    "warning",
                    f"the same rationale ('{text}') is used for {len(dims)} dimensions "
                    f"({', '.join(dims)}); each dimension needs its own explanation",
                ),
            )
        )
    return found
