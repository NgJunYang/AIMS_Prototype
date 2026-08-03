"""Turn student-written LaTeX into SymPy equations, defensively.

Every function here is pure and never raises: an unparseable line yields an
empty result so the pipeline can flag that one step and continue.
"""

import re

import sympy
from sympy.parsing.latex import parse_latex

# Applied in order. Each entry is (pattern, replacement).
_REWRITES: list[tuple[str, str]] = [
    (r"\\\[|\\\]|\$\$|\$", ""),          # display/inline math wrappers
    # Prose is not mathematics. 'or' inside prose is a separator between two
    # answers, so keep it; everything else in a \text{} block must go, because
    # parse_latex happily turns 'expand the brackets' into a product of
    # single-letter symbols that looks like a real (wrong) equation.
    (r"\\(?:text|textrm|mbox)\s*\{[^{}]*\bor\b[^{}]*\}", " or "),
    (r"\\(?:text|textrm|mbox)\s*\{[^{}]*\}", " "),
    (r"\\left|\\right", ""),             # sizing commands SymPy dislikes
    (r"\\dfrac|\\tfrac", r"\\frac"),     # fraction variants
    (r"\\times|\\cdot", "*"),            # explicit multiplication
    (r"\\div", "/"),
    (r"\\,|\\;|\\:|\\!|\\quad|\\qquad", " "),  # spacing commands
    (r"\\mathrm|\\mathit|\\mathbf", ""),
    (r"\s+", " "),                       # collapse whitespace
]

_SPLIT_PATTERN = re.compile(r",|;|\\text\{\s*or\s*\}|\\quad|\bor\b")

# A digit, letter, closing brace or closing bracket immediately followed by an
# opening bracket means implicit multiplication: '2(x+1)', 'x(x-5)', ')(' .
_IMPLICIT_MULTIPLICATION = re.compile(r"([A-Za-z0-9})])\s*\(")

# '\pm' has no meaning to SymPy; it parses as a free symbol called 'pm'.
_PLUS_MINUS = re.compile(r"\\pm|\\mp")


def normalise_latex(raw: str) -> str:
    """Rewrite equivalent LaTeX spellings into the subset SymPy parses well."""
    text = raw
    for pattern, replacement in _REWRITES:
        text = re.sub(pattern, replacement, text)
    return _insert_implicit_multiplication(text).strip()


def _insert_implicit_multiplication(text: str) -> str:
    """Make 'x(x - 5)' explicit, so SymPy reads a product not a function call.

    Without this, ``parse_latex('x(x - 5)')`` returns ``Function('x')(x - 5)``,
    which silently destroys a very common way of writing a factorised form.
    """

    def replace(match: re.Match[str]) -> str:
        index = match.start(1)
        # Walk back over a command name so '\sin(x)' is left alone.
        while index >= 0 and text[index].isalpha():
            index -= 1
        if index >= 0 and text[index] == "\\":
            return match.group(0)
        return f"{match.group(1)} * ("

    return _IMPLICIT_MULTIPLICATION.sub(replace, text)


def split_answer_line(raw: str) -> list[str]:
    """Split a final-answer line such as 'x = 2, x = 3' into separate equations.

    A line with no separator is returned unchanged as a single-element list.
    """
    normalised = normalise_latex(raw)
    parts = [part.strip() for part in _SPLIT_PATTERN.split(normalised)]
    parts = [part for part in parts if part]
    return parts if len(parts) > 1 else [normalised]


def expand_plus_minus(part: str) -> list[str]:
    """Turn one '\\pm' line into its two explicit branches.

    'x = \\frac{5 \\pm \\sqrt{1}}{2}' denotes two roots, so it becomes two
    equations. A line without '\\pm' is returned unchanged.
    """
    if not _PLUS_MINUS.search(part):
        return [part]
    plus = _PLUS_MINUS.sub(lambda m: "+" if m.group(0) == r"\pm" else "-", part)
    minus = _PLUS_MINUS.sub(lambda m: "-" if m.group(0) == r"\pm" else "+", part)
    return [plus, minus]


def parse_equation_line(raw: str, variable: str = "x") -> list[sympy.Eq]:
    """Parse one written line into a list of SymPy equations.

    A line may contain several equations ('x = 0, x = 5'). A bare expression
    is interpreted as 'expression = 0', which is how students often write a
    factorised form. Returns [] if nothing could be parsed.
    """
    equations: list[sympy.Eq] = []
    for part in split_answer_line(raw):
        for branch in expand_plus_minus(part):
            equation = _parse_single(branch, variable)
            if equation is None:
                return []
            equations.append(equation)
    return equations


def _evaluate(expression: sympy.Basic) -> sympy.Basic:
    """Rebuild a parse tree with SymPy's automatic evaluation switched on.

    ``parse_latex`` returns unevaluated nodes, so 'x^2 - 5x + 6' arrives as a
    nested ``Add(Add(...), ...)``. Rebuilding bottom-up gives the flat
    canonical form the rest of the pipeline compares against.
    """
    if expression.is_Atom or not expression.args:
        return expression
    return expression.func(*[_evaluate(argument) for argument in expression.args])


def _parse_single(part: str, variable: str) -> sympy.Eq | None:
    symbol = sympy.Symbol(variable)
    if part.count("=") > 1:
        # Two equations run together with no separator. Better to degrade this
        # line honestly than to report a confident, wrong solution set.
        return None
    try:
        if "=" in part:
            left, _, right = part.partition("=")
            lhs = _evaluate(parse_latex(left.strip()))
            rhs = _evaluate(parse_latex(right.strip()))
        else:
            lhs = _evaluate(parse_latex(part.strip()))
            rhs = sympy.Integer(0)
    except Exception:
        return None

    if lhs is None or rhs is None:
        return None

    if variable != "i":
        # '2i' parses as '2*i' with 'i' a free symbol; students mean sqrt(-1).
        imaginary = sympy.Symbol("i")
        try:
            lhs = lhs.subs(imaginary, sympy.I)
            rhs = rhs.subs(imaginary, sympy.I)
        except Exception:
            return None

    if symbol not in (lhs.free_symbols | rhs.free_symbols):
        # A line with no unknown in it (e.g. an arithmetic aside) is not a step
        # we can verify as part of the solution chain.
        return None
    return sympy.Eq(lhs, rhs)
