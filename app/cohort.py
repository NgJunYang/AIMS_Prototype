"""Cohort aggregation: many marked submissions into one class summary.

Pure and total. It takes the submissions it is handed and returns a
ClassSummary; it never reads the submissions directory itself, which keeps all
file I/O in store.py and makes this module trivially unit-testable.

No LLM is involved anywhere here. Every number is a count or a mean over marks
that SymPy-backed verification and the lecturer already settled, and the
recommendation sentence is a template over those same counts. Asking a model to
"summarise the class" would mean inventing a factual claim about numbers it
cannot verify - precisely what this project refuses to do everywhere else.
"""

import math
from collections import Counter

from app.models import (
    ClassMisconceptionCount,
    ClassStudentRow,
    ClassSummary,
    Submission,
)
from app.store import get_misconception

# Templated, never generated. Each is a factual statement about counts.
_NO_SUBMISSIONS = (
    "No submissions yet. This summary computes itself from real marking as "
    "soon as you mark a script."
)
_NONE_MARKED = (
    "{cohort} submission{s} started, none marked yet. Mark one and this view "
    "fills in."
)
_NO_MISCONCEPTIONS = (
    "No misconceptions were flagged across {marked} marked submission{s}. "
    "Mean mark {mean}%."
)
_TOP = "{count} of {marked} marked submission{s} {verb} {name}."
_TOP_WITH_REFERENCE = _TOP + " Revisit {reference} before the next assessment."


def humanise_tag(tag: str) -> str:
    """`divided_by_variable_lost_root` -> `Divided By Variable Lost Root`.

    Mirrors humanizeTag() in static/app.js so a tag missing from the seeded
    catalogue still reads as English rather than as a database key.
    """
    return " ".join(word.capitalize() for word in tag.split("_"))


def _display_name(tag: str) -> str:
    return get_misconception(tag).get("name") or humanise_tag(tag)


def _plural(count: int) -> str:
    return "" if count == 1 else "s"


def _tags_of(submission: Submission) -> set[str]:
    """The distinct misconceptions on one script.

    A set, so a tag the marker happened to list twice on a single script still
    counts as one student affected rather than two.
    """
    if submission.marks is None:
        return set()
    return set(submission.marks.misconceptions)


def misconception_counts(
    submissions: list[Submission],
) -> list[ClassMisconceptionCount]:
    """How many students showed each misconception, commonest first."""
    counter: Counter[str] = Counter()
    for submission in submissions:
        counter.update(_tags_of(submission))

    return [
        ClassMisconceptionCount(tag=tag, name=_display_name(tag), count=count)
        for tag, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _top_misconception(
    submission: Submission, cohort: Counter[str]
) -> str | None:
    """This script's own tag that is most common across the whole cohort.

    Showing the cohort-commonest of a student's tags is more useful to a
    lecturer scanning the table than an arbitrary first one: it surfaces the
    pattern worth reteaching. Ties fall back to the order the marker listed
    them, which is the order the verifier surfaced them - deterministic
    without being arbitrary.
    """
    tags = submission.marks.misconceptions if submission.marks else []
    if not tags:
        return None
    return max(tags, key=lambda tag: (cohort[tag], -tags.index(tag)))


def _recommendation(
    cohort_size: int,
    marked: int,
    mean_percentage: int,
    counts: list[ClassMisconceptionCount],
) -> str:
    if cohort_size == 0:
        return _NO_SUBMISSIONS
    if marked == 0:
        return _NONE_MARKED.format(cohort=cohort_size, s=_plural(cohort_size))
    if not counts:
        return _NO_MISCONCEPTIONS.format(
            marked=marked, s=_plural(marked), mean=mean_percentage
        )

    top = counts[0]
    name = top.name[0].lower() + top.name[1:] if top.name else top.tag
    fields = {
        "count": top.count,
        "marked": marked,
        "s": _plural(marked),
        "verb": "shows" if top.count == 1 else "show",
        "name": name,
    }
    reference = get_misconception(top.tag).get("remediation_reference")
    if reference:
        return _TOP_WITH_REFERENCE.format(reference=reference, **fields)
    return _TOP.format(**fields)


def summarise(submissions: list[Submission]) -> ClassSummary:
    """Aggregate real submissions into the cohort view."""
    marked_submissions = [s for s in submissions if s.marks is not None]

    # Only submissions with something to score contribute to the mean. An
    # unmarked script is absent from the average, not a zero in it.
    scored = [s for s in marked_submissions if s.marks.total_max > 0]
    if scored:
        mean = sum(
            100 * s.marks.total_proposed / s.marks.total_max for s in scored
        ) / len(scored)
        mean_percentage = math.floor(mean + 0.5)  # half-up, not banker's rounding
    else:
        mean_percentage = 0

    counts = misconception_counts(marked_submissions)
    cohort_counter: Counter[str] = Counter()
    for submission in marked_submissions:
        cohort_counter.update(_tags_of(submission))

    students = [
        ClassStudentRow(
            pseudonym=s.student_pseudonym,
            question_id=s.question_id,
            mark=s.marks.total_proposed,
            max=s.marks.total_max,
            top_misconception=_top_misconception(s, cohort_counter),
        )
        for s in sorted(
            marked_submissions,
            key=lambda s: (s.student_pseudonym.lower(), s.question_id, s.id),
        )
    ]

    cohort_size = len(submissions)
    marked = len(marked_submissions)
    return ClassSummary(
        source="computed",
        source_note=(
            f"Computed live from {marked} marked submission{_plural(marked)} "
            f"of {cohort_size} on this machine."
        ),
        submission_count=cohort_size,
        cohort_size=cohort_size,
        marked=marked,
        mean_percentage=mean_percentage,
        misconception_counts=counts,
        students=students,
        recommendation=_recommendation(cohort_size, marked, mean_percentage, counts),
    )
