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
    # completely correct script. A connective is punctuation, so it is stripped
    # and the answer stays verifiable: the answer mark is genuinely earnable.
    assert solution_set(r"\therefore x = 2, x = 3", "x") == {"2", "3"}
    report = verify(
        steps("x^2 - 5x + 6 = 0", r"\therefore x = 2, x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.candidate_misconceptions == []
    assert report.first_divergence_index is None
    assert report.steps[1].lost_roots == []
    assert report.steps[1].gained_roots == []
    assert report.steps[1].parsed is True
    assert report.steps[1].equivalent_to_previous is True
    assert report.final_answer_correct is True
    assert report.final_answer_verified is True


def test_a_general_formula_line_still_degrades_to_unparseable():
    # Pins the boundary of the connective strip: symbols that carry actual
    # mathematics are still rejected, with or without a connective in front.
    assert solution_set(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}", "x") is None
    assert solution_set(r"\therefore x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}", "x") is None


NON_EQUALITY_RELATIONS = [
    r"\to", r"\rightarrow", r"\longrightarrow", r"\mapsto", r"\leftarrow",
    r"\geq", r"\ge", r"\geqq", r"\geqslant",
    r"\leq", r"\le", r"\leqq", r"\leqslant",
    r"\neq", r"\ne", r"\approx", r"\sim", r"\simeq", r"\propto",
    r"\in", r"\notin", r"\equiv", r"\gg", r"\ll", r"\subset", r"\supset",
    "<", ">",
]


@pytest.mark.parametrize("token", NON_EQUALITY_RELATIONS)
def test_a_line_whose_relation_is_not_equality_is_unparseable(token):
    # An inequality is not a step in an equation-solving chain. It used to give
    # set() - 'parsed, no solutions' - which reads downstream as 'every root was
    # lost', the same fabrication class as the other bugs. None is the honest
    # answer: this module cannot verify it, so it must not judge it.
    assert solution_set(f"x {token} 2", "x") is None, token


def test_silent_truncation_by_the_latex_parser_cannot_invent_a_root():
    # The non-obvious part: parse_latex does not fail on these. It truncates at
    # the token it does not know and returns what it read, so 'x \to 2' arrives
    # as the bare expression 'x', becomes Eq(x, 0) and yields {'0'} - the value
    # classify() reads as the headline lost-root misconception. Nothing survives
    # parsing to show that '\to 2' was discarded, and no stray free symbol is
    # left, so only a pre-parse check can catch it.
    assert solution_set(r"x \to 2", "x") is None
    assert solution_set(r"x \rightarrow 2", "x") is None
    assert solution_set(r"x \longrightarrow 2", "x") is None


def test_guard_b_rejects_a_relation_the_blocklist_would_have_missed(monkeypatch):
    # Guard B is reachable, not merely belt-and-braces: SymPy's grammar accepts
    # '\leqq' and '\leqslant' (LaTeX.g4), which parse to Relational objects
    # whose only free symbol is the unknown, so the free-symbol guard passes
    # them. Blinding the blocklist to those two names simulates any relation
    # spelling it does not know about; Guard B still stops them.
    import re

    from app import latex_utils

    narrowed = re.compile(
        latex_utils._NON_EQUALITY_RELATION.pattern.replace("leqslant|leqq|", "")
    )
    monkeypatch.setattr(latex_utils, "_NON_EQUALITY_RELATION", narrowed)

    assert narrowed.search(r"x \leqslant 2") is None  # the blocklist is now blind
    assert solution_set(r"x \leqslant 2", "x") is None  # and Guard B catches it
    assert solution_set(r"x \leqq 2", "x") is None


def test_an_inequality_step_degrades_and_accuses_the_student_of_nothing():
    report = verify(
        steps("x^2 - 5x + 6 = 0", r"x \geq 2", "x = 2, x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.steps[1].parsed is False
    assert report.steps[1].divergence == "unparseable"
    assert report.steps[1].solutions == []
    assert report.candidate_misconceptions == []
    assert report.first_divergence_index is None
    assert report.all_steps_parsed is False


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


def test_bug4_a_note_between_two_answer_lines_does_not_split_the_answer():
    # An unparseable line is transparent everywhere else in verify(), so it must
    # not break up a multi-line answer either. It used to, which resurrected the
    # fabricated 'lost_solution' and 'sign_error' from bug 4.
    report = verify(
        steps("(x - 2)(x - 3) = 0", "x = 2", r"\text{and also}", "x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.candidate_misconceptions == []
    assert report.first_divergence_index is None
    assert report.final_answer_correct is True
    assert report.steps[2].parsed is False
    assert report.steps[3].solutions == ["2", "3"]


def test_bug4_an_identity_between_two_answer_lines_does_not_split_the_answer():
    report = verify(
        steps("(x - 2)(x - 3) = 0", "x = 2", "x(x - 5) = x^2 - 5x", "x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.candidate_misconceptions == []
    assert report.first_divergence_index is None
    assert report.final_answer_correct is True


def test_restating_the_same_root_is_an_ordinary_step_not_a_multi_line_answer():
    # '2x = 4' then 'x = 2' state the same root, so they are a real algebraic
    # step and must keep their own verdict rather than being coalesced.
    report = verify(
        steps("2x = 4", "x = 2"),
        model_solution_steps=["2x = 4", "x = 2"],
        variable="x",
    )
    assert report.steps[1].equivalent_to_previous is True
    assert report.steps[0].note == ""
    assert report.steps[1].note == ""
    assert report.steps[0].solutions == ["2"]
    assert report.final_answer_correct is True
    assert report.candidate_misconceptions == []

    # Stating *different* roots on consecutive lines still coalesces.
    report = verify(
        steps("x^2 - 5x + 6 = 0", "x = 2", "x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.steps[1].note != ""
    assert report.steps[2].solutions == ["2", "3"]
    assert report.candidate_misconceptions == []
    assert report.first_divergence_index is None


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


def test_a_chain_equality_step_verifies_against_itself():
    # A lecturer photographed a model solution whose first step was written as
    # a chain equality: 'x^2 - 5x + 6 = (x-2)(x-3) = 0'. This used to be
    # rejected outright (more than one '=' with no separator), producing a
    # 400 on save even though the working is correct. It must now verify
    # cleanly, with no fabricated divergence against the very same roots
    # stated the ordinary way on the next line.
    report = verify(
        steps("x^2 - 5x + 6 = (x-2)(x-3) = 0", "x = 2 \\text{ or } x = 3"),
        model_solution_steps=[
            "x^2 - 5x + 6 = (x-2)(x-3) = 0",
            "x = 2 \\text{ or } x = 3",
        ],
        variable="x",
    )
    assert report.steps[0].parsed is True
    assert report.steps[0].divergence is None
    assert report.candidate_misconceptions == []
    assert report.first_divergence_index is None
    assert report.final_answer_correct is True
    assert report.final_answer_verified is True
