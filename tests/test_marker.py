from app import marker
from app.models import (
    CriterionMark,
    MarkProposal,
    Step,
    StepVerification,
    VerificationReport,
)
from app.store import get_question


def _report_with_lost_root() -> VerificationReport:
    return VerificationReport(
        steps=[
            StepVerification(index=1, parsed=True, solutions=["0", "5"]),
            StepVerification(
                index=2,
                parsed=True,
                solutions=["5"],
                equivalent_to_previous=False,
                divergence="lost_roots",
                lost_roots=["0"],
            ),
        ],
        final_answer_correct=False,
        model_solutions=["0", "5"],
        candidate_misconceptions=["divided_by_variable_lost_root"],
    )


def test_prompt_forbids_the_model_from_doing_mathematics():
    prompt = marker.build_prompt(
        get_question("q2"),
        [Step(index=1, latex="x^2 = 5x")],
        _report_with_lost_root(),
    )
    lowered = prompt.lower()
    assert "do not re-derive" in lowered
    assert "verified" in lowered


def test_prompt_contains_the_verification_findings():
    prompt = marker.build_prompt(
        get_question("q2"),
        [Step(index=1, latex="x^2 = 5x"), Step(index=2, latex="x = 5")],
        _report_with_lost_root(),
    )
    assert "lost_roots" in prompt
    assert "x = 5" in prompt


def test_prompt_permits_alternative_valid_methods():
    prompt = marker.build_prompt(
        get_question("q2"), [Step(index=1, latex="x^2 = 5x")], _report_with_lost_root()
    )
    assert "alternative" in prompt.lower() or "different valid method" in prompt.lower()


def test_mark_builds_a_proposal_from_the_model_response(monkeypatch):
    fake = {
        "criteria": [
            {
                "criterion_id": "C1",
                "proposed": 0,
                "justification": "divided through by x",
                "evidence_step": 2,
            },
            {
                "criterion_id": "C2",
                "proposed": 2,
                "justification": "method otherwise sound",
                "evidence_step": 2,
            },
            {"criterion_id": "C3", "proposed": 2, "justification": "arithmetic fine"},
            {"criterion_id": "C4", "proposed": 0, "justification": "only one solution given"},
        ],
        "misconceptions": ["divided_by_variable_lost_root"],
    }
    monkeypatch.setattr(marker, "complete_json", lambda **kwargs: fake)

    proposal = marker.mark(
        get_question("q2"),
        [Step(index=1, latex="x^2 = 5x"), Step(index=2, latex="x = 5")],
        _report_with_lost_root(),
    )

    assert isinstance(proposal, MarkProposal)
    assert proposal.total_proposed == 4
    assert proposal.total_max == 8
    # max values come from the rubric, never from the model
    assert {c.criterion_id: c.max for c in proposal.criteria}["C2"] == 3


def test_marks_above_the_rubric_max_are_clamped(monkeypatch):
    fake = {
        "criteria": [{"criterion_id": "C1", "proposed": 99, "justification": "x"}],
        "misconceptions": [],
    }
    monkeypatch.setattr(marker, "complete_json", lambda **kwargs: fake)

    proposal = marker.mark(get_question("q2"), [], _report_with_lost_root())

    assert proposal.criteria[0].proposed == 2  # C1 max for q2


def test_criteria_missing_from_the_response_default_to_zero_and_flag_for_review(monkeypatch):
    fake = {
        "criteria": [{"criterion_id": "C1", "proposed": 1, "justification": "ok"}],
        "misconceptions": [],
    }
    monkeypatch.setattr(marker, "complete_json", lambda **kwargs: fake)

    proposal = marker.mark(get_question("q2"), [], _report_with_lost_root())

    # q2 has C1..C4; the three absent ones must still appear
    assert [c.criterion_id for c in proposal.criteria] == ["C1", "C2", "C3", "C4"]
    absent = [c for c in proposal.criteria if c.criterion_id != "C1"]
    assert all(c.proposed == 0 for c in absent)
    assert all("review" in c.justification.lower() for c in absent)


def test_cross_check_warns_when_full_marks_given_on_a_diverged_step():
    proposal = MarkProposal(
        criteria=[
            CriterionMark(
                criterion_id="C2",
                proposed=3,
                max=3,
                justification="looks right",
                evidence_step=2,
            )
        ]
    )
    warnings = marker.cross_check(proposal, _report_with_lost_root())
    assert len(warnings) == 1
    assert "C2" in warnings[0]
    assert "step 2" in warnings[0]


def test_cross_check_is_silent_when_marks_and_verification_agree():
    proposal = MarkProposal(
        criteria=[
            CriterionMark(
                criterion_id="C2",
                proposed=1,
                max=3,
                justification="partial",
                evidence_step=2,
            )
        ]
    )
    assert marker.cross_check(proposal, _report_with_lost_root()) == []


def test_cross_check_ignores_zero_max_criteria():
    proposal = MarkProposal(
        criteria=[
            CriterionMark(
                criterion_id="C9",
                proposed=0,
                max=0,
                justification="n/a",
                evidence_step=2,
            )
        ]
    )
    assert marker.cross_check(proposal, _report_with_lost_root()) == []


def test_mark_attaches_cross_check_warnings_to_the_proposal(monkeypatch):
    fake = {
        "criteria": [
            {
                "criterion_id": "C2",
                "proposed": 3,
                "justification": "full marks despite divergence",
                "evidence_step": 2,
            }
        ],
        "misconceptions": [],
    }
    monkeypatch.setattr(marker, "complete_json", lambda **kwargs: fake)

    proposal = marker.mark(get_question("q2"), [], _report_with_lost_root())

    assert len(proposal.warnings) == 1
    assert "C2" in proposal.warnings[0]
