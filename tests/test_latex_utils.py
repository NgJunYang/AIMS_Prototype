import pytest
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


def test_bug1_connective_is_stripped_not_multiplied_into_the_equation():
    # parse_latex maps any unrecognised \command to a Symbol, so
    # '\therefore x = 2' used to parse as Eq(therefore*x, 2) and corrupt the
    # solution set. A connective is punctuation: it is removed, and the
    # equation it introduces is verified normally.
    assert normalise_latex(r"\therefore x = 2") == "x = 2"
    equations = parse_equation_line(r"\therefore x = 2", "x")
    assert len(equations) == 1
    assert equations[0] == sympy.Eq(sympy.Symbol("x"), 2)
    for connective in CONNECTIVES:
        assert len(parse_equation_line(f"{connective} x = 2, x = 3", "x")) == 2, connective


CONNECTIVES = [
    r"\therefore",
    r"\because",
    r"\Rightarrow",
    r"\Longrightarrow",
    r"\Leftrightarrow",
    r"\Leftarrow",
    r"\implies",
    r"\iff",
]


@pytest.mark.parametrize("connective", CONNECTIVES)
def test_each_connective_leaves_the_equation_intact(connective):
    assert normalise_latex(f"{connective} x = 2").strip() == "x = 2"
    assert parse_equation_line(f"{connective} x = 2", "x") == [
        sympy.Eq(sympy.Symbol("x"), 2)
    ]


def test_arrow_is_a_relation_not_a_connective_and_is_rejected():
    # '\to' is not stripped like the connectives above: between bare expressions
    # it is a real relation (limit, mapping). It is rejected outright, because
    # parse_latex does not fail on it - it silently truncates, handing back a
    # bare 'x' with no trace that '\to 2' was discarded.
    assert parse_equation_line(r"x \to 2", "x") == []
    assert parse_equation_line(r"\to x = 2", "x") == []


def test_a_connective_strip_does_not_eat_a_longer_command_name():
    # '\to' must not match the start of '\top', which is a real symbol and so
    # is still caught by the free-symbol guard.
    assert normalise_latex(r"\top x = 2") == r"\top x = 2"
    assert parse_equation_line(r"\top x = 2", "x") == []


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
    # Stripping discourse connectives is NOT a licence to loosen this guard:
    # a connective carries no mathematics, whereas b, a and c do.
    assert parse_equation_line(r"x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}", "x") == []
    assert parse_equation_line(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}", "x") == []
    assert parse_equation_line(r"\therefore x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}", "x") == []


def test_complex_answers_still_parse_after_the_free_symbol_guard():
    # 'i' is substituted for sympy.I, which contributes no free symbols.
    assert len(parse_equation_line("x = -1 + 2i, x = -1 - 2i", "x")) == 2


# Guard A's blocklist. A line whose relation is not equality is not a step in an
# equation-solving chain, so none of these may produce a solution set.
NON_EQUALITY_RELATIONS = [
    r"\to", r"\rightarrow", r"\longrightarrow", r"\mapsto", r"\leftarrow",
    r"\geq", r"\ge", r"\geqq", r"\geqslant",
    r"\leq", r"\le", r"\leqq", r"\leqslant",
    r"\neq", r"\ne", r"\approx", r"\sim", r"\simeq", r"\propto",
    r"\in", r"\notin", r"\equiv", r"\gg", r"\ll", r"\subset", r"\supset",
    "<", ">",
]


@pytest.mark.parametrize("token", NON_EQUALITY_RELATIONS)
def test_a_non_equality_relation_is_rejected(token):
    assert parse_equation_line(f"x {token} 2", "x") == [], token


# Commands whose names begin with a blocklisted token. The lookahead must not
# let the blocklist eat any of these, or ordinary lines start disappearing.
@pytest.mark.parametrize(
    "latex",
    [
        r"\left(x - 2\right)\left(x - 3\right) = 0",  # '\le' must not eat '\left'
        r"\top x = 2",                                # '\to' must not eat '\top'
        r"x \times 2 = 4",                            # '\to' must not eat '\times'
        r"\text{or} x = 2",                           # '\to' must not eat '\text'
        r"\therefore x = 2",                          # '\the...' is a connective
    ],
)
def test_the_relation_blocklist_does_not_eat_a_longer_command(latex):
    from app.latex_utils import _NON_EQUALITY_RELATION

    assert _NON_EQUALITY_RELATION.search(latex) is None, latex


def test_infinity_is_not_mistaken_for_the_set_membership_token():
    # '\in' must not match the start of '\infty'.
    from app.latex_utils import _NON_EQUALITY_RELATION

    assert _NON_EQUALITY_RELATION.search(r"x = \infty") is None
