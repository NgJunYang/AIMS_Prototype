from app.authoring import DEFAULT_CRITERIA, compute_verification_tier, default_criteria, validate_question
from app.models import Criterion, Question


def _question(**overrides) -> Question:
    fields = {
        "id": "custom1",
        "prompt": "Solve $x^2 - 7x + 12 = 0$.",
        "model_solution_steps": [
            "x^2 - 7x + 12 = 0",
            "(x - 3)(x - 4) = 0",
            "x = 3, x = 4",
        ],
        "variable": "x",
        "criteria": [Criterion(id="C1", max=2, description="Solved it")],
    }
    fields.update(overrides)
    return Question(**fields)


# ---------- the invariant that matters ----------


def test_a_sound_question_has_no_problems():
    assert validate_question(_question()) == []


def test_a_sound_question_is_tiered_verified():
    assert compute_verification_tier(_question()) == ("verified", [])


def test_a_model_solution_that_loses_a_root_is_rejected():
    """The whole point. A lecturer who writes a model solution that drops a
    root would mark every student against it wrongly, so this must be caught
    when the question is saved, not discovered later.
    """
    problems = validate_question(
        _question(
            prompt="Solve $x^2 = 5x$.",
            model_solution_steps=["x^2 = 5x", "x = 5"],
        )
    )
    assert problems
    assert any("step 2" in p for p in problems)


def test_a_model_solution_with_a_sign_error_is_rejected():
    problems = validate_question(
        _question(
            model_solution_steps=[
                "x^2 - 7x + 12 = 0",
                "(x + 3)(x + 4) = 0",
                "x = -3, x = -4",
            ]
        )
    )
    assert problems
    assert any("step 2" in p for p in problems)


def test_an_unparseable_model_solution_line_is_ai_graded_not_rejected():
    """Non-algebraic content (a proof, a sum, prose) is not an authoring
    error: it falls outside what SymPy can check, so it is tiered instead of
    refused. The instructor still sees why, just as a non-blocking note.
    """
    question = _question(
        model_solution_steps=[
            "x^2 - 7x + 12 = 0",
            "then I factorised it somehow",
            "x = 3, x = 4",
        ]
    )
    assert validate_question(question) == []
    tier, notes = compute_verification_tier(question)
    assert tier == "ai_graded"
    assert any("step 2" in n.lower() for n in notes)


def test_a_single_step_solution_is_rejected():
    """One line is a statement, not a worked solution to mark against."""
    problems = validate_question(_question(model_solution_steps=["x = 3, x = 4"]))
    assert any("at least two" in p.lower() for p in problems)


def test_a_solution_with_no_steps_is_rejected():
    """Tiering can't excuse having nothing to mark against at all."""
    problems = validate_question(_question(model_solution_steps=[]))
    assert any("at least two" in p.lower() for p in problems)


def test_a_solution_of_only_blank_lines_is_rejected_regardless_of_tier():
    """A blank line never parses, so it would otherwise tier ai_graded and
    slip past the (tier-conditional) step-count check with nothing to mark
    against - this check is unconditional precisely to close that gap.
    """
    problems = validate_question(_question(model_solution_steps=["", "   "]))
    assert any("blank" in p.lower() for p in problems)


# ---------- ordinary field validation ----------


def test_an_empty_prompt_is_rejected():
    assert any("prompt" in p.lower() for p in validate_question(_question(prompt="  ")))


def test_a_question_with_no_criteria_is_rejected():
    problems = validate_question(_question(criteria=[]))
    assert any("criterion" in p.lower() for p in problems)


def test_duplicate_criterion_ids_are_rejected():
    problems = validate_question(
        _question(
            criteria=[
                Criterion(id="C1", max=2, description="a"),
                Criterion(id="C1", max=2, description="b"),
            ]
        )
    )
    assert any("duplicate" in p.lower() for p in problems)


def test_a_rubric_worth_no_marks_is_rejected():
    problems = validate_question(
        _question(criteria=[Criterion(id="C1", max=0, description="a")])
    )
    assert any("at least one mark" in p.lower() for p in problems)


def test_an_id_that_would_not_survive_a_url_is_rejected():
    assert any("id" in p.lower() for p in validate_question(_question(id="a b/c")))


def test_an_empty_id_is_rejected():
    assert any("id" in p.lower() for p in validate_question(_question(id="")))


def test_a_multi_character_variable_makes_otherwise_sound_algebra_ai_graded():
    """'xy' doesn't match any real free symbol in x-based content, so every
    step fails to parse under it - the same outcome, and the same tiering
    treatment, as declaring the wrong single-letter variable.
    """
    question = _question(variable="xy")
    assert validate_question(question) == []
    tier, notes = compute_verification_tier(question)
    assert tier == "ai_graded"
    assert notes


def test_a_single_step_proof_that_does_not_parse_is_ai_graded_not_rejected():
    """The same short-answer shape, but content SymPy can't read at all -
    a one-line proof - is tiered instead of blocked on step count.
    """
    question = _question(model_solution_steps=["By pigeonhole, two must share a remainder."])
    assert validate_question(question) == []
    tier, notes = compute_verification_tier(question)
    assert tier == "ai_graded"
    assert notes


def test_a_solution_in_a_different_variable_from_the_declared_one_is_ai_graded():
    """A model solution written in x but declared as y cannot be checked by
    SymPy either - the free-symbol guard in parse_equation_line treats a
    variable mismatch exactly like any other unparseable line (see
    app/latex_utils.py). It downgrades to ai_graded rather than being
    silently accepted as sound; the notes keep the mismatch visible to the
    instructor every time the question is viewed, not just at save time.
    """
    question = _question(variable="y")
    assert validate_question(question) == []
    tier, notes = compute_verification_tier(question)
    assert tier == "ai_graded"
    assert notes


# ---------- the default rubric ----------


def test_the_default_rubric_is_method_agnostic():
    """A factorisation-only rubric would unfairly penalise a student who
    completed the square, so the default deliberately does not name a method.
    """
    text = " ".join(c.description.lower() for c in default_criteria())
    for method in ("factoris", "quadratic formula", "completing the square"):
        assert method not in text
    assert any("valid solution method" in c.description.lower() for c in default_criteria())


def test_the_default_rubric_is_itself_a_valid_rubric():
    assert validate_question(_question(criteria=default_criteria())) == []


def test_default_criteria_returns_a_fresh_copy_each_time():
    """Callers edit these; a shared mutable default would leak between them."""
    first = default_criteria()
    first[0].description = "mutated"
    assert default_criteria()[0].description == DEFAULT_CRITERIA[0]["description"]
