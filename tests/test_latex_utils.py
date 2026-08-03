import sympy

from app.latex_utils import normalise_latex, parse_equation_line, split_answer_line


def test_normalise_strips_display_wrappers_and_spacing():
    assert normalise_latex(r"\[ x^{2} = 5x \]") == "x^{2} = 5x"
    assert normalise_latex(r"$$x^2=0$$") == "x^2=0"
    assert normalise_latex(r"x^2 \, = \, 0") == "x^2 = 0"


def test_normalise_rewrites_common_variants():
    assert r"\times" not in normalise_latex(r"2 \times x = 4")
    assert r"\left" not in normalise_latex(r"\left( x - 2 \right) = 0")
    assert r"\dfrac" not in normalise_latex(r"\dfrac{1}{2}x = 1")


def test_parse_simple_equation():
    equations = parse_equation_line("x^2 - 5x + 6 = 0", "x")
    assert len(equations) == 1
    assert equations[0].lhs - equations[0].rhs == sympy.sympify("x**2 - 5*x + 6")


def test_parse_bare_expression_is_treated_as_equal_to_zero():
    equations = parse_equation_line("x^2 - 4", "x")
    assert len(equations) == 1
    assert sympy.simplify(equations[0].lhs - equations[0].rhs) == sympy.sympify("x**2 - 4")


def test_split_answer_line_handles_comma_and_or():
    assert split_answer_line("x = 2, x = 3") == ["x = 2", "x = 3"]
    assert split_answer_line(r"x = 2 \text{ or } x = 3") == ["x = 2", "x = 3"]
    assert split_answer_line("x^2 = 4") == ["x^2 = 4"]


def test_parse_answer_line_yields_two_equations():
    equations = parse_equation_line("x = 0, x = 5", "x")
    assert len(equations) == 2


def test_unparseable_line_returns_empty_list():
    assert parse_equation_line(r"\text{no idea what this is}", "x") == []


def test_prose_containing_the_unknown_is_still_rejected():
    # 'expand' contains an x, and parse_latex will happily read the whole
    # phrase as a product of single-letter symbols. Prose must never be
    # mistaken for a verifiable step.
    assert parse_equation_line(r"\text{expand the brackets}", "x") == []
    assert parse_equation_line(r"\text{x is the answer}", "x") == []


def test_wide_gap_separates_two_answers():
    # '\quad' is the natural transcription of two answers separated by a wide
    # gap. normalise_latex rewrites it to a space before the split ran, so the
    # split has to happen first.
    assert split_answer_line(r"x = 2 \quad x = 3") == ["x = 2", "x = 3"]
    assert split_answer_line(r"x = 2 \qquad x = 3") == ["x = 2", "x = 3"]
    assert split_answer_line(r"\[x = 2 \quad x = 3\]") == ["x = 2", "x = 3"]
    assert parse_equation_line(r"x = 2 \quad x = 3", "x") != []


def test_bug1_stray_connective_does_not_multiply_into_the_equation():
    # parse_latex maps any unrecognised \command to a Symbol, so
    # '\therefore x = 2' used to parse as Eq(therefore*x, 2) and corrupt the
    # solution set. A line carrying a connective is not verifiable maths.
    assert parse_equation_line(r"\therefore x = 2", "x") == []
    assert parse_equation_line(r"\therefore x = 2, x = 3", "x") == []
    for connective in [r"\Rightarrow", r"\implies", r"\to"]:
        assert parse_equation_line(f"{connective} x = 2", "x") == [], connective


def test_bug2_unwrapped_and_unstripped_prose_is_rejected():
    # Whitespace is skipped by the grammar and every letter is an atom, so
    # prose that escapes the \text{} rewrites used to become a product of
    # single-letter symbols equal to zero.
    for prose in [
        "expand",                        # never wrapped at all
        "factorise the expression",
        r"\textbf{expand}",              # rewrite only covers text/textrm/mbox
        r"\text{expand \frac{1}{2}}",    # [^{}]* cannot cross inner braces
    ]:
        assert parse_equation_line(prose, "x") == [], prose


def test_bug1_general_formula_degrades_rather_than_inventing_roots():
    # The un-substituted quadratic formula has free symbols other than x, so
    # it is honestly reported as unparseable instead of yielding bogus roots.
    assert parse_equation_line(r"x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}", "x") == []


def test_complex_answers_still_parse_after_the_free_symbol_guard():
    # 'i' is substituted for sympy.I, which contributes no free symbols.
    assert len(parse_equation_line("x = -1 + 2i, x = -1 - 2i", "x")) == 2
