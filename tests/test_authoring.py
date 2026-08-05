from app.authoring import DEFAULT_CRITERIA, default_criteria, validate_question
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


def test_an_unparseable_model_solution_line_is_rejected():
    problems = validate_question(
        _question(
            model_solution_steps=[
                "x^2 - 7x + 12 = 0",
                "then I factorised it somehow",
                "x = 3, x = 4",
            ]
        )
    )
    assert problems
    assert any("could not be read" in p.lower() for p in problems)


def test_a_single_step_solution_is_rejected():
    """One line is a statement, not a worked solution to mark against."""
    problems = validate_question(_question(model_solution_steps=["x = 3, x = 4"]))
    assert any("at least two" in p.lower() for p in problems)


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


def test_a_multi_character_variable_is_rejected():
    problems = validate_question(_question(variable="xy"))
    assert any("variable" in p.lower() for p in problems)


def test_a_solution_in_a_different_variable_from_the_declared_one_is_rejected():
    """Declaring `y` but writing the solution in `x` would make every step
    unverifiable, so it is caught here rather than at marking time."""
    problems = validate_question(_question(variable="y"))
    assert problems


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
