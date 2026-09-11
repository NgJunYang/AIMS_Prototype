import pytest
from pydantic import ValidationError

from app.models import (
    Criterion,
    CriterionMark,
    MarkProposal,
    Question,
    Step,
    StepVerification,
    Submission,
    VerificationReport,
)


def test_old_submission_json_defaults_to_unreviewed():
    submission = Submission.model_validate_json('{"id":"old","question_id":"q1"}')
    assert submission.reviewed is False
    assert submission.review_invalidated is False


def test_step_defaults_to_unedited_and_high_confidence():
    step = Step(index=1, latex="x^2 - 5x + 6 = 0")
    assert step.confidence == "high"
    assert step.edited_by_human is False


def test_criterion_mark_cannot_exceed_max():
    with pytest.raises(ValidationError):
        CriterionMark(
            criterion_id="C1", proposed=5, max=2, justification="x", evidence_step=1
        )


def test_mark_proposal_total_is_computed_from_criteria():
    proposal = MarkProposal(
        criteria=[
            CriterionMark(
                criterion_id="C1", proposed=2, max=2, justification="ok", evidence_step=1
            ),
            CriterionMark(
                criterion_id="C2", proposed=1, max=3, justification="partial", evidence_step=3
            ),
        ],
        misconceptions=["divided_by_variable_lost_root"],
    )
    assert proposal.total_proposed == 3
    assert proposal.total_max == 5


def test_verification_report_finds_first_divergence():
    report = VerificationReport(
        steps=[
            StepVerification(index=1, parsed=True, equivalent_to_previous=None),
            StepVerification(index=2, parsed=True, equivalent_to_previous=True),
            StepVerification(
                index=3,
                parsed=True,
                equivalent_to_previous=False,
                divergence="lost_roots",
                lost_roots=["0"],
            ),
        ],
        final_answer_correct=False,
    )
    assert report.first_divergence_index == 3


def test_question_round_trips():
    question = Question(
        id="q2",
        prompt="Solve $x^2 = 5x$.",
        model_solution_steps=["x^2 = 5x", "x^2 - 5x = 0", "x(x - 5) = 0", "x = 0, x = 5"],
        variable="x",
        criteria=[Criterion(id="C1", max=2, description="Rearranged to standard form")],
    )
    assert Question.model_validate(question.model_dump()) == question
