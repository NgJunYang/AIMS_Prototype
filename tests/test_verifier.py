import pytest

from app.models import Step
from app.verifier import TAUTOLOGY, solution_set, verify


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


def test_bug1_connective_before_the_answer_invents_no_misconception():
    # '\therefore x = 2, x = 3' used to parse as Eq(therefore*x, 2), giving
    # divergence='different_roots' and a fabricated 'sign_error' against a
    # completely correct script.
    assert solution_set(r"\therefore x = 2, x = 3", "x") is None
    report = verify(
        steps("x^2 - 5x + 6 = 0", r"\therefore x = 2, x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.candidate_misconceptions == []
    assert report.first_divergence_index is None
    assert report.steps[1].lost_roots == []
    assert report.steps[1].gained_roots == []
    # The line the answer was written on is now unparseable, so the answer is
    # not established rather than wrong: final_answer_verified says which.
    # (Bug 5's rule and this script pull in opposite directions - see the
    # accompanying report. Nothing is asserted as an error against the
    # student, which is the point of bug 1.)
    assert report.final_answer_correct is False
    assert report.final_answer_verified is False


def test_bug2_prose_never_produces_a_solution_set():
    # {'0'} was the worst possible wrong answer here: classify()'s flagship
    # check is `"0" in lost_roots`, so prose could fabricate the headline
    # 'divided_by_variable_lost_root' misconception.
    for prose in [
        "expand",
        "factorise the expression",
        r"\textbf{expand}",
        r"\text{expand \frac{1}{2}}",
    ]:
        assert solution_set(prose, "x") is None, prose


def test_bug2_genuinely_unsatisfiable_equation_is_still_an_empty_set():
    # The distinction that matters most: set() means 'parsed, no solutions',
    # None means 'could not be read as mathematics'.
    assert solution_set("x + 1 = x + 2", "x") == set()


def test_bug3_identity_line_is_not_read_as_losing_every_root():
    # A student checking their own factorisation writes a line that is true for
    # all x. sympy.solve returns [] for it, which used to read as a genuinely
    # empty solution set - i.e. 'every root was lost' and then 'every root came
    # back', producing two confident, mutually contradictory misconceptions.
    assert solution_set("x(x - 5) = x^2 - 5x", "x") is TAUTOLOGY
    report = verify(
        steps("x^2 = 5x", "x(x - 5) = x^2 - 5x", "x = 0, x = 5"),
        model_solution_steps=["x^2 = 5x", "x(x - 5) = 0", "x = 0, x = 5"],
        variable="x",
    )
    assert report.candidate_misconceptions == []
    assert report.first_divergence_index is None
    assert report.final_answer_correct is True
    # The identity is a valid step, and it does not disturb the comparison
    # between the lines either side of it.
    assert report.steps[1].parsed is True
    assert report.steps[1].divergence is None
    assert report.steps[1].solutions == []
    assert report.all_steps_parsed is True


def test_bug4_roots_written_on_consecutive_lines_are_one_answer():
    # Writing each root on its own line is a very common layout. Compared
    # line-by-line it looked like losing root 3 and then swapping 2 for 3,
    # giving 'lost_solution' and 'sign_error' against a correct script.
    report = verify(
        steps("(x - 2)(x - 3) = 0", "x = 2", "x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.candidate_misconceptions == []
    assert report.first_divergence_index is None
    assert report.final_answer_correct is True
    # Every step is still in the report, with its own index, so the UI can
    # highlight individual lines.
    assert [s.index for s in report.steps] == [1, 2, 3]
    assert report.steps[1].parsed is True
    assert report.steps[1].equivalent_to_previous is None
    assert report.steps[1].divergence is None
    assert report.steps[1].solutions == ["2"]
    assert report.steps[1].note != ""
    # The verdict for the whole run lands on its last line, against the union.
    assert report.steps[2].equivalent_to_previous is True
    assert report.steps[2].solutions == ["2", "3"]


def test_bug4_a_run_of_one_still_detects_a_lost_root():
    # The coalescing must not blunt the two lost-root cases: in both of these
    # the run has length 1, so behaviour is unchanged.
    report = verify(
        steps("x^2 = 5x", "x = 5"),
        model_solution_steps=["x^2 = 5x", "x(x - 5) = 0", "x = 0, x = 5"],
        variable="x",
    )
    assert report.steps[1].divergence == "lost_roots"
    assert report.steps[1].lost_roots == ["0"]
    assert report.candidate_misconceptions == ["divided_by_variable_lost_root"]
    assert report.final_answer_correct is False

    report = verify(
        steps("x^2 = 9", "x = 3"),
        model_solution_steps=["x^2 = 9", "x = 3, x = -3"],
        variable="x",
    )
    assert report.steps[1].divergence == "lost_roots"
    assert "dropped_plus_minus" in report.candidate_misconceptions


def test_bug4_both_square_roots_on_separate_lines_is_correct():
    report = verify(
        steps("x^2 = 9", "x = 3", "x = -3"),
        model_solution_steps=["x^2 = 9", "x = 3, x = -3"],
        variable="x",
    )
    assert report.candidate_misconceptions == []
    assert report.first_divergence_index is None
    assert report.final_answer_correct is True


def test_two_answers_separated_by_a_wide_gap_are_both_read():
    assert solution_set(r"x = 2 \quad x = 3", "x") == {"2", "3"}


def test_bug5_unparseable_final_line_does_not_award_the_answer_mark():
    # `previous` is the last line that *parsed*, so the answer mark used to be
    # decided from an intermediate line while the actual answer line was never
    # read at all.
    report = verify(
        steps("x^2 = 5x", "x(x - 5) = 0", r"\text{answer: five}"),
        model_solution_steps=["x^2 = 5x", "x(x - 5) = 0", "x = 0, x = 5"],
        variable="x",
    )
    assert report.final_answer_correct is False
    assert report.final_answer_verified is False


def test_bug5_a_verified_wrong_answer_is_distinguishable_from_an_unread_one():
    report = verify(
        steps("x^2 = 5x", "x = 5"),
        model_solution_steps=["x^2 = 5x", "x = 0, x = 5"],
        variable="x",
    )
    assert report.final_answer_correct is False
    assert report.final_answer_verified is True


def test_bug5_unparseable_model_solution_is_not_evidence_against_the_student():
    # 'if expected' was falsy for both None and set(), so a model solution that
    # failed to parse looked exactly like one with no solutions, and the marker
    # would be told as fact that the student was wrong because the *seed data*
    # did not parse.
    report = verify(
        steps("x^2 = 5x", "x = 0, x = 5"),
        model_solution_steps=[r"\text{see the worksheet}"],
        variable="x",
    )
    assert report.final_answer_correct is False
    assert report.final_answer_verified is False

    # A model solution that genuinely has no solutions is a real comparison.
    report = verify(
        steps("x + 1 = x + 2"),
        model_solution_steps=["x + 1 = x + 2"],
        variable="x",
    )
    assert report.final_answer_correct is True
    assert report.final_answer_verified is True
    assert report.model_solutions == []


def test_bug5_identity_as_the_last_line_leaves_the_answer_unverified():
    report = verify(
        steps("x^2 = 5x", "x = 0, x = 5", "x(x - 5) = x^2 - 5x"),
        model_solution_steps=["x^2 = 5x", "x = 0, x = 5"],
        variable="x",
    )
    assert report.final_answer_correct is False
    assert report.final_answer_verified is False


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
