from app.models import Step
from app.store import list_questions
from app.verifier import solution_set, verify


def test_every_model_solution_line_parses():
    for question in list_questions():
        for latex in question.model_solution_steps:
            assert solution_set(latex, question.variable) is not None, (
                f"{question.id}: unparseable model line {latex!r}"
            )


def test_every_model_solution_verifies_as_correct_against_itself():
    for question in list_questions():
        steps = [
            Step(index=i, latex=text)
            for i, text in enumerate(question.model_solution_steps, start=1)
        ]
        report = verify(steps, question.model_solution_steps, question.variable)
        assert report.final_answer_correct, f"{question.id} does not verify against itself"
        assert report.first_divergence_index is None, (
            f"{question.id} has a divergence in its own model solution "
            f"at step {report.first_divergence_index}"
        )
