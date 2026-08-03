import pytest
import sympy

from app.practice import TEMPLATES, generate_practice


def test_generate_returns_requested_count():
    questions = generate_practice(["divided_by_variable_lost_root"], count=3, seed=1)
    assert len(questions) == 3


def test_generated_questions_are_tagged_with_the_requested_misconception():
    questions = generate_practice(["dropped_plus_minus"], count=2, seed=7)
    assert all(q.misconception_tag == "dropped_plus_minus" for q in questions)


def test_unknown_tag_falls_back_to_general_practice():
    questions = generate_practice(["not_a_real_tag"], count=2, seed=3)
    assert len(questions) == 2


def test_no_tags_still_produces_practice():
    questions = generate_practice([], count=3, seed=3)
    assert len(questions) == 3


@pytest.mark.parametrize("seed", range(50))
@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_every_generated_answer_actually_solves_its_own_question(template_id, seed):
    """Property test: the stated answer must satisfy the stated equation."""
    template = TEMPLATES[template_id]
    generated = template.generate(seed)

    x = sympy.Symbol("x")
    equation = sympy.sympify(generated.equation_sympy)
    claimed = {sympy.nsimplify(sympy.sympify(r)) for r in generated.roots_sympy}
    actual = {sympy.nsimplify(r) for r in sympy.solve(equation, x)}

    assert claimed == actual, (
        f"{template_id} seed={seed}: claims {claimed} but the equation has {actual}"
    )
