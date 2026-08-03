import pytest

from app.models import Step
from app.verifier import solution_set, verify


def steps(*latex: str) -> list[Step]:
    return [Step(index=i, latex=text) for i, text in enumerate(latex, start=1)]


def test_solution_set_of_a_factorised_quadratic():
    assert solution_set("(x - 2)(x - 3) = 0", "x") == {"2", "3"}


def test_solution_set_of_standard_form():
    assert solution_set("x^2 - 5x + 6 = 0", "x") == {"2", "3"}


def test_solution_set_of_answer_line():
    assert solution_set("x = 2, x = 3", "x") == {"2", "3"}


def test_correct_chain_is_fully_equivalent():
    report = verify(
        steps("x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x = 2, x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.final_answer_correct is True
    assert report.first_divergence_index is None
    assert report.candidate_misconceptions == []


def test_dividing_by_the_variable_is_detected_as_a_lost_root():
    report = verify(
        steps("x^2 = 5x", "x = 5"),
        model_solution_steps=["x^2 = 5x", "x(x - 5) = 0", "x = 0, x = 5"],
        variable="x",
    )
    assert report.first_divergence_index == 2
    assert report.steps[1].divergence == "lost_roots"
    assert report.steps[1].lost_roots == ["0"]
    assert "divided_by_variable_lost_root" in report.candidate_misconceptions
    assert report.final_answer_correct is False


def test_sign_error_in_factorisation_is_detected_as_different_roots():
    report = verify(
        steps("x^2 - 5x + 6 = 0", "(x + 2)(x + 3) = 0", "x = -2, x = -3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.first_divergence_index == 2
    assert report.steps[1].divergence == "different_roots"
    assert "sign_error" in report.candidate_misconceptions


def test_dropping_plus_minus_is_a_lost_root():
    report = verify(
        steps("x^2 = 9", "x = 3"),
        model_solution_steps=["x^2 = 9", "x = 3, x = -3"],
        variable="x",
    )
    assert report.steps[1].divergence == "lost_roots"
    assert "dropped_plus_minus" in report.candidate_misconceptions


def test_unparseable_step_degrades_without_crashing():
    report = verify(
        steps("x^2 - 5x + 6 = 0", r"\text{then I factorised}", "x = 2, x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.steps[1].parsed is False
    assert report.steps[1].divergence == "unparseable"
    assert report.all_steps_parsed is False
    # The chain still reaches a correct final answer.
    assert report.final_answer_correct is True


def test_no_real_roots_case():
    report = verify(
        steps("x^2 + 2x + 5 = 0", r"x = -1 + 2i, x = -1 - 2i"),
        model_solution_steps=["x^2 + 2x + 5 = 0", r"x = -1 + 2i, x = -1 - 2i"],
        variable="x",
    )
    assert report.final_answer_correct is True


def test_empty_input_produces_an_empty_report():
    report = verify([], model_solution_steps=["x = 1"], variable="x")
    assert report.steps == []
    assert report.final_answer_correct is False


REALISTIC_LINES = [
    "x^2 - 5x + 6 = 0",
    r"x^{2} - 5x + 6 = 0",
    r"\left(x - 2\right)\left(x - 3\right) = 0",
    "x^2 = 5x",
    "x(x - 5) = 0",
    "x = 0, x = 5",
    r"x = \frac{5 \pm \sqrt{25 - 24}}{2}",
    r"2x^{2} + 3x - 5 = 0",
    r"\left(2x + 5\right)\left(x - 1\right) = 0",
]


@pytest.mark.parametrize("latex", REALISTIC_LINES)
def test_realistic_lines_all_parse(latex):
    assert solution_set(latex, "x") is not None, f"failed to parse: {latex}"
