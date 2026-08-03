from app import feedback as feedback_module
from app.models import CriterionMark, Feedback, MarkProposal, Step, VerificationReport
from app.store import get_question


def _proposal() -> MarkProposal:
    return MarkProposal(
        criteria=[
            CriterionMark(
                criterion_id="C1",
                proposed=0,
                max=2,
                justification="Divided by x at step 2.",
                evidence_step=2,
            )
        ],
        misconceptions=["divided_by_variable_lost_root"],
    )


def _report() -> VerificationReport:
    return VerificationReport(
        steps=[], final_answer_correct=False, model_solutions=["0", "5"]
    )


def test_prompt_addresses_the_student_directly_and_bans_new_claims():
    prompt = feedback_module.build_prompt(
        get_question("q2"), [Step(index=1, latex="x^2 = 5x")], _proposal(), _report()
    )
    lowered = prompt.lower()
    assert "second person" in lowered
    assert "do not" in lowered


def test_prompt_includes_the_marks_already_decided():
    prompt = feedback_module.build_prompt(
        get_question("q2"), [Step(index=1, latex="x^2 = 5x")], _proposal(), _report()
    )
    assert "C1" in prompt
    assert "Divided by x at step 2." in prompt


def test_write_returns_structured_feedback(monkeypatch):
    fake = {
        "what_went_well": "You rearranged correctly.",
        "what_went_wrong": "You divided by x and lost the solution x = 0.",
        "how_to_improve": "Move everything to one side and factorise.",
        "references": ["Notes §2 — the zero-product principle"],
    }
    monkeypatch.setattr(feedback_module, "complete_json", lambda **kwargs: fake)

    result = feedback_module.write(get_question("q2"), [], _proposal(), _report())

    assert isinstance(result, Feedback)
    assert "x = 0" in result.what_went_wrong
    assert result.references == ["Notes §2 — the zero-product principle"]
