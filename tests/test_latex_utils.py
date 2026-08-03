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
