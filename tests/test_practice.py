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


def test_generated_questions_are_distinct_from_each_other():
    """A student handed the same drill twice loses confidence in the whole feature.

    Consecutive seeds can draw the same small parameters, so this is not
    hypothetical - it was observed in the browser before being fixed.
    """
    for seed in range(40):
        questions = generate_practice(
            ["divided_by_variable_lost_root"], count=3, seed=seed
        )
        prompts = [q.prompt_latex for q in questions]
        assert len(set(prompts)) == 3, f"seed={seed} produced duplicates: {prompts}"


def test_distinctness_holds_for_every_tag_and_the_fallback():
    for tags in (
        ["divided_by_variable_lost_root"],
        ["dropped_plus_minus"],
        ["sign_error"],
        ["not_a_real_tag"],
        [],
    ):
        questions = generate_practice(tags, count=3, seed=11)
        prompts = [q.prompt_latex for q in questions]
        assert len(set(prompts)) == 3, f"{tags} produced duplicates: {prompts}"
