import pytest
from pydantic import ValidationError

from app.cohort import humanise_tag, summarise
from app.models import (
    ClassStudentRow,
    ClassSummary,
    CriterionMark,
    MarkProposal,
    Submission,
)


def _marked(
    submission_id: str,
    pseudonym: str,
    proposed: int,
    maximum: int,
    misconceptions: list[str],
    question_id: str = "q2",
) -> Submission:
    return Submission(
        id=submission_id,
        question_id=question_id,
        student_pseudonym=pseudonym,
        marks=MarkProposal(
            criteria=[
                CriterionMark(
                    criterion_id="C1",
                    proposed=proposed,
                    max=maximum,
                    justification="stub",
                )
            ],
            misconceptions=misconceptions,
        ),
    )


def _unmarked(submission_id: str, pseudonym: str = "Nobody") -> Submission:
    return Submission(id=submission_id, question_id="q2", student_pseudonym=pseudonym)


# ---------- degenerate inputs ----------


def test_no_submissions_at_all():
    summary = summarise([])
    assert summary.cohort_size == 0
    assert summary.marked == 0
    assert summary.students == []
    assert summary.misconception_counts == []
    assert summary.mean_percentage == 0
    assert "No submissions yet" in summary.recommendation


def test_submissions_that_were_never_marked_are_counted_but_not_scored():
    summary = summarise([_unmarked("a"), _unmarked("b")])
    assert summary.cohort_size == 2
    assert summary.marked == 0
    # An unmarked submission has no mark to average, so it must not drag the
    # mean toward zero - it is absent from the calculation, not a nil score.
    assert summary.mean_percentage == 0
    assert summary.students == []
    assert "none marked yet" in summary.recommendation


def test_a_marked_submission_worth_zero_marks_does_not_crash_the_mean():
    summary = summarise([_marked("a", "Ann", 0, 0, [])])
    assert summary.marked == 1
    assert summary.mean_percentage == 0


# ---------- the real thing ----------


def _cohort() -> list[Submission]:
    return [
        _marked("a", "Ann", 4, 8, ["divided_by_variable_lost_root"]),
        _marked("b", "Ben", 8, 8, []),
        _marked("c", "Cal", 3, 8, ["divided_by_variable_lost_root", "sign_error"]),
        _unmarked("d", "Dee"),
    ]


def test_counts_only_marked_submissions_as_students():
    summary = summarise(_cohort())
    assert summary.cohort_size == 4
    assert summary.marked == 3
    assert [row.pseudonym for row in summary.students] == ["Ann", "Ben", "Cal"]


def test_mean_percentage_is_the_mean_of_per_submission_percentages():
    # 50% + 100% + 37.5% = 187.5 / 3 = 62.5 -> 63 (half-up)
    assert summarise(_cohort()).mean_percentage == 63


def test_misconception_counts_are_ranked_and_named():
    counts = summarise(_cohort()).misconception_counts
    assert [(c.tag, c.count) for c in counts] == [
        ("divided_by_variable_lost_root", 2),
        ("sign_error", 1),
    ]
    # The human-readable name comes from the seeded misconception catalogue.
    assert counts[0].name == "Dividing both sides by the unknown"


def test_a_tag_repeated_on_one_script_still_counts_once():
    doubled = [_marked("a", "Ann", 4, 8, ["sign_error", "sign_error"])]
    counts = summarise(doubled).misconception_counts
    assert [(c.tag, c.count) for c in counts] == [("sign_error", 1)]


def test_an_unseeded_tag_still_gets_a_readable_name():
    summary = summarise([_marked("a", "Ann", 4, 8, ["some_new_tag"])])
    assert summary.misconception_counts[0].name == "Some New Tag"


def test_student_rows_reflect_lecturer_overrides():
    """mark/max read the computed totals, so an override shows up here."""
    submission = _marked("a", "Ann", 4, 8, [])
    submission.marks.criteria[0].proposed = 7
    assert summarise([submission]).students[0].mark == 7


def test_top_misconception_prefers_the_most_common_across_the_cohort():
    summary = summarise(_cohort())
    cal = next(row for row in summary.students if row.pseudonym == "Cal")
    # Cal has both tags; the cohort-wide commonest one is the more useful signal.
    assert cal.top_misconception == "divided_by_variable_lost_root"


def test_a_clean_script_has_no_top_misconception():
    summary = summarise(_cohort())
    ben = next(row for row in summary.students if row.pseudonym == "Ben")
    assert ben.top_misconception is None


def test_recommendation_names_the_top_misconception_with_real_counts():
    recommendation = summarise(_cohort()).recommendation
    assert "2 of 3" in recommendation
    assert "dividing both sides by the unknown" in recommendation.lower()


def test_recommendation_when_nothing_went_wrong():
    summary = summarise([_marked("a", "Ann", 8, 8, [])])
    assert "No misconceptions" in summary.recommendation


def test_source_is_computed_and_the_note_states_the_real_numbers():
    summary = summarise(_cohort())
    assert summary.source == "computed"
    assert "3" in summary.source_note and "4" in summary.source_note


# ---------- the consistency invariant ----------


def test_a_summary_claiming_more_students_than_rows_cannot_be_built():
    """This is the exact shape of the fixture this feature replaced."""
    with pytest.raises(ValidationError):
        ClassSummary(cohort_size=31, marked=31, students=[])


def test_marked_cannot_exceed_cohort_size():
    with pytest.raises(ValidationError):
        ClassSummary(cohort_size=1, marked=2, students=[])


def test_a_student_row_scoring_above_its_maximum_is_rejected():
    with pytest.raises(ValidationError):
        ClassSummary(
            cohort_size=1,
            marked=1,
            students=[
                ClassStudentRow(pseudonym="Ann", question_id="q2", mark=9, max=8)
            ],
        )


def test_every_computed_summary_satisfies_the_invariant():
    """summarise() must never be able to produce something the model rejects."""
    for submissions in ([], [_unmarked("a")], _cohort()):
        summary = summarise(submissions)
        assert len(summary.students) == summary.marked
        assert summary.marked <= summary.cohort_size


def test_humanise_tag_matches_the_frontend_helper():
    assert humanise_tag("divided_by_variable_lost_root") == (
        "Divided By Variable Lost Root"
    )
    assert humanise_tag("") == ""
