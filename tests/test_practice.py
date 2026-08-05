import pytest
import sympy

from app.practice import (
    BARE,
    SCENARIO,
    TEMPLATES,
    Framing,
    Rendered,
    compose,
    generate_practice,
)

# Every (template, framing) pair, for the invariants that must hold across all
# of them rather than only the ones a given template happens to reach.
PAIRS = [
    (template_id, framing.id)
    for template_id in sorted(TEMPLATES)
    for framing in TEMPLATES[template_id].framings
]


def _framing(template_id: str, framing_id: str) -> Framing:
    return next(f for f in TEMPLATES[template_id].framings if f.id == framing_id)


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


# ---------- the mathematics is correct ----------


@pytest.mark.parametrize("seed", range(50))
@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_every_generated_answer_actually_solves_its_own_question(template_id, seed):
    """Property test: the stated roots must satisfy the stated equation."""
    problem = TEMPLATES[template_id].make_problem(seed)

    x = sympy.Symbol("x")
    equation = sympy.sympify(problem.equation_sympy)
    claimed = {sympy.nsimplify(sympy.sympify(r)) for r in problem.roots_sympy}
    actual = {sympy.nsimplify(r) for r in sympy.solve(equation, x)}

    assert claimed == actual, (
        f"{template_id} seed={seed}: claims {claimed} but the equation has {actual}"
    )


# ---------- framing cannot change the mathematics ----------


@pytest.mark.parametrize("seed", range(30))
@pytest.mark.parametrize("template_id,framing_id", PAIRS)
def test_framing_is_presentation_only(template_id, framing_id, seed):
    """However a problem is phrased, the underlying maths must be identical.

    This is the invariant that makes scenario prose safe: compose() copies the
    equation and its roots off the Problem, so a framing has no way to describe
    different mathematics from the one that was verified.
    """
    problem = TEMPLATES[template_id].make_problem(seed)
    framing = _framing(template_id, framing_id)
    if not framing.applies(problem):
        pytest.skip(f"{framing_id} declines this problem")

    generated = compose(problem, framing)

    assert generated.equation_sympy == problem.equation_sympy
    assert generated.roots_sympy == problem.roots_sympy


@pytest.mark.parametrize("seed", range(30))
@pytest.mark.parametrize("template_id,framing_id", PAIRS)
def test_admissible_roots_are_a_non_empty_subset_of_the_real_roots(
    template_id, framing_id, seed
):
    """A framing may exclude a root for context, but never invent one, and
    never exclude them all - that would be a question with no answer."""
    problem = TEMPLATES[template_id].make_problem(seed)
    framing = _framing(template_id, framing_id)
    if not framing.applies(problem):
        pytest.skip(f"{framing_id} declines this problem")

    generated = compose(problem, framing)

    assert generated.admissible_roots
    assert set(generated.admissible_roots) <= set(problem.roots_sympy)


def test_compose_refuses_a_framing_that_admits_no_root():
    """The guard is real, not decorative."""
    problem = TEMPLATES["quad_plus_minus"].make_problem(1)
    broken = Framing(
        id="broken",
        question_type=SCENARIO,
        label="Broken",
        applies=lambda _p: True,
        render=lambda _p: Rendered(
            prompt_latex="?", answer_latex="?", admissible_roots=[]
        ),
    )
    with pytest.raises(ValueError, match="non-empty subset"):
        compose(problem, broken)


def test_compose_refuses_a_framing_that_invents_a_root():
    problem = TEMPLATES["quad_plus_minus"].make_problem(1)
    liar = Framing(
        id="liar",
        question_type=SCENARIO,
        label="Liar",
        applies=lambda _p: True,
        render=lambda _p: Rendered(
            prompt_latex="?", answer_latex="?", admissible_roots=["999"]
        ),
    )
    with pytest.raises(ValueError, match="non-empty subset"):
        compose(problem, liar)


# ---------- scenario behaviour ----------


@pytest.mark.parametrize("seed", range(50))
@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_requesting_a_scenario_never_produces_an_unanswerable_question(
    template_id, seed
):
    """quad_sign_check can draw two non-positive roots, which no
    positives-only scenario can honestly carry. It must fall back to bare
    rather than produce a question with no valid answer."""
    generated = TEMPLATES[template_id].generate(seed, SCENARIO)
    assert generated.admissible_roots
    assert set(generated.admissible_roots) <= set(generated.roots_sympy)


def test_question_type_reports_what_was_produced_not_what_was_asked_for():
    """A downgrade to bare must be visible, not silently mislabelled."""
    template = TEMPLATES["quad_sign_check"]
    downgraded = [
        template.generate(seed, SCENARIO)
        for seed in range(50)
        if not template.framings[1].applies(template.make_problem(seed))
    ]
    assert downgraded, "expected at least one seed the scenario framing declines"
    assert all(g.question_type == BARE for g in downgraded)


def test_the_garden_scenario_never_calls_a_square_a_rectangle():
    """With a = 1 the prose would read "x wide and x long" while calling the
    plot rectangular. Observed in the browser; the framing now declines."""
    template = TEMPLATES["quad_zero_root"]
    for seed in range(60):
        generated = template.generate(seed, SCENARIO)
        if generated.question_type != SCENARIO:
            continue
        assert "rectangular" not in generated.prompt_latex or (
            template.make_problem(seed).params["a"] >= 2
        )
        # The two dimensions must never be written identically.
        assert "$x$ metres wide and $x$ metres long" not in generated.prompt_latex


def test_a_scenario_that_rejects_a_root_explains_why():
    generated = TEMPLATES["quad_zero_root"].generate(1, SCENARIO)
    assert generated.question_type == SCENARIO
    assert generated.admissible_roots == [generated.roots_sympy[1]]
    assert "zero width" in generated.rejected_note


def test_scenario_prose_uses_the_same_numbers_as_the_equation():
    """The framing is handed pre-formatted strings, so it cannot fabricate a
    number - this pins that the ones it does show are the problem's own."""
    problem = TEMPLATES["quad_zero_root"].make_problem(4)
    generated = compose(problem, _framing("quad_zero_root", "garden_area"))
    assert f"{problem.params['b']} times its width" in generated.prompt_latex


def test_scenario_prompts_use_dollars_only_as_balanced_latex_delimiters():
    """renderMixed() in app.js splits on '$' and treats odd segments as maths,
    so an unbalanced '$' would silently render prose as an equation."""
    for template in TEMPLATES.values():
        for seed in range(20):
            generated = template.generate(seed, SCENARIO)
            assert generated.prompt_latex.count("$") % 2 == 0, generated.prompt_latex


# ---------- bare framing is unchanged ----------


def test_bare_framing_output_is_unchanged_from_before_framings_existed():
    """Guards against the refactor quietly altering the existing question set."""
    assert (
        TEMPLATES["quad_plus_minus"]
        .generate(3, BARE)
        .prompt_latex.startswith("Solve $x^2 = ")
    )
    zero_root = TEMPLATES["quad_zero_root"].generate(1, BARE)
    assert zero_root.answer_latex.startswith("x = 0, \\; x = ")
    assert zero_root.admissible_roots == zero_root.roots_sympy


# ---------- distinctness ----------


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


def test_scenario_questions_are_also_distinct():
    for tags in (["divided_by_variable_lost_root"], ["dropped_plus_minus"]):
        questions = generate_practice(tags, count=3, seed=5, question_type=SCENARIO)
        prompts = [q.prompt_latex for q in questions]
        assert len(set(prompts)) == 3, f"{tags} produced duplicates: {prompts}"
