from app.context import assemble
from app.store import get_question


def test_assemble_includes_the_rubric_and_model_solution():
    context = assemble(get_question("q2"), ["divided_by_variable_lost_root"])
    assert "C1" in context
    assert "x(x - 5) = 0" in context


def test_assemble_includes_only_the_relevant_misconception_entries():
    context = assemble(get_question("q2"), ["divided_by_variable_lost_root"])
    assert "Dividing both sides by the unknown" in context
    assert "Taking only the positive square root" not in context


def test_assemble_with_no_misconceptions_still_returns_rubric():
    context = assemble(get_question("q1"), [])
    assert "C1" in context


def test_assemble_includes_topic_notes():
    context = assemble(get_question("q1"), [])
    assert "zero-product principle" in context
