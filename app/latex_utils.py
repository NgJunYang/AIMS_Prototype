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
    # Discourse connectives are punctuation, not mathematics: they assert a
    # relationship *between* lines, which this pipeline establishes itself by
    # comparing solution sets. Stripping them therefore loses nothing, whereas
    # leaving them in corrupts the equation - parse_latex maps an unrecognised
    # command to a Symbol, so '\therefore x = 2' becomes Eq(therefore*x, 2).
    # Note this is the opposite treatment to prose, which is dropped along with
    # the whole line it appears on: prose says something the verifier cannot
    # check, so a line containing it is not a verifiable step. A connective
    # says only 'and so', which is exactly what the comparison already tests.
    # '\to' is deliberately NOT in this list. Unlike the others it has a genuine
    # mathematical use between bare expressions (limit and mapping notation), so
    # stripping it turns 'x \to 2' into 'x 2' -> Eq(2*x, 0) -> {'0'}, which is
    # precisely the value classify() reads as the headline lost-root
    # misconception. It is rejected outright by _NON_EQUALITY_RELATION instead,
    # which is also what stops the same hazard arriving through parse_latex's
    # silent truncation - see that pattern's comment. The eight below are safe:
    # used relationally they sit between two equations, so the line carries two
    # '=' signs and the count("=") > 1 guard in _parse_single rejects it already.
    # The trailing lookahead stops a name matching a longer command's prefix.
    (
        r"\\(?:therefore|because|Longrightarrow|Leftrightarrow|Rightarrow"
        r"|Leftarrow|implies|iff)(?![A-Za-z])",
        " ",
    ),
    (r"\\left|\\right", ""),             # sizing commands SymPy dislikes
    (r"\\dfrac|\\tfrac", r"\\frac"),     # fraction variants
    (r"\\times|\\cdot", "*"),            # explicit multiplication
    (r"\\div", "/"),
    (r"\\,|\\;|\\:|\\!|\\quad|\\qquad", " "),  # spacing commands
    (r"\\mathrm|\\mathit|\\mathbf", ""),
    (r"\s+", " "),                       # collapse whitespace
]

# Guard A: a line whose relation is not equality is not a step in an
# equation-solving chain, so it must degrade to unparseable rather than be
# judged. This has to be a *pre-parse* check on the raw line, because
# parse_latex does not fail on these - it silently truncates at a token it does
# not know and hands back whatever it managed to read:
#
#     parse_latex(r'x \to 2')          -> x          free_symbols {x}
#     parse_latex(r'x \longrightarrow 2') -> x       free_symbols {x}
#
# 'x' then becomes Eq(x, 0) and yields {'0'} - the value classify() reads as the
# headline lost-root misconception. No stray symbol is left behind, so the
# free-symbol guard in _parse_single cannot see that anything was discarded, and
# after parsing there is no evidence left at all. Hence a token blocklist.
#
# Matched against the raw line, before the rewrites run: '\right' would
# otherwise have already eaten the '\right' of '\rightarrow', and the
# connectives would already be gone. Case matters, which is what keeps
# '\Rightarrow' (a connective, stripped) distinct from '\rightarrow' (a
# relation, rejected). Every name carries the trailing lookahead so it cannot
# match a longer command's prefix: '\le' must not match '\left' or '\leq',
# '\in' must not match '\infty', '\to' must not match '\top'.
_NON_EQUALITY_RELATION = re.compile(
    r"[<>]"
    r"|\\(?:"
    # Arrows and maps. SymPy truncates the line at all of these.
    r"longrightarrow|rightarrow|leftarrow|mapsto|to"
    # Orderings. These parse into Relational objects whose only free symbol is
    # the unknown, so they slip past the free-symbol guard. Longest first; the
    # 'qq'/'slant' spellings are in SymPy's own grammar (LaTeX.g4 lines 138-149).
    r"|leqslant|leqq|leq|le|geqslant|geqq|geq|ge|neq|ne|gg|ll"
    # Other relations. These leave a stray symbol and so are already rejected,
    # but naming them keeps the intent explicit rather than incidental.
    r"|approx|simeq|sim|propto|notin|in|equiv|subset|supset"
    r")(?![A-Za-z])"
)

# Separators that survive normalisation. '\text{ or }' is not listed because
# normalise_latex has already rewritten it to ' or ', which '\bor\b' catches.
_SPLIT_PATTERN = re.compile(r",|;|\bor\b")

# A wide gap is how two answers get separated when nothing else is written
# between them. It has to be split on *before* normalisation, which turns it
# into ordinary whitespace and then collapses it.
_WIDE_GAP_PATTERN = re.compile(r"\\qquad|\\quad")

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
    parts: list[str] = []
    for chunk in _WIDE_GAP_PATTERN.split(raw):
        parts.extend(_SPLIT_PATTERN.split(normalise_latex(chunk)))
    parts = [part.strip() for part in parts]
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
    factorised form. Returns [] if nothing could be parsed, which includes a
    line stating a relation other than equality: an inequality is not a step in
    an equation-solving chain, and reporting it as a solution set would be a
    confident claim about working this module cannot verify.
    """
    if _NON_EQUALITY_RELATION.search(raw):
        return []

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
            lhs = _evaluate(parse_latex(left.strip(), strict=True))
            rhs = _evaluate(parse_latex(right.strip(), strict=True))
        else:
            lhs = _evaluate(parse_latex(part.strip(), strict=True))
            rhs = sympy.Integer(0)
    except Exception:
        return None

    if lhs is None or rhs is None:
        return None

    # Guard B: defence in depth behind _NON_EQUALITY_RELATION, for a relation
    # spelling the blocklist misses. Either side arriving as a comparison rather
    # than a quantity ('x \geqslant 2' -> GreaterThan(x, 2)) means this line is
    # not an equation, and its only free symbol may well be the unknown, so the
    # free-symbol guard below would wave it through.
    #
    # Tested as 'is an ordinary expression' rather than 'is a Boolean', because
    # sympy.Symbol inherits from Boolean - symbols are usable in boolean
    # algebra - so rejecting Boolean operands would reject 'x = 2'. Everything
    # to reject here (Relational, BooleanTrue/False, And/Or) is not an Expr;
    # everything to keep (Symbol, Add, Mul, Integer, I) is. Note this runs on
    # the *operands*: the BooleanTrue that sympy.Eq legitimately evaluates to
    # for 'x = x' is constructed below and must survive, as must the
    # BooleanFalse for 'x + 1 = x + 2'.
    for operand in (lhs, rhs):
        if not isinstance(operand, sympy.Expr) or isinstance(
            operand, sympy.core.relational.Relational
        ):
            return None

    if variable != "i":
        # '2i' parses as '2*i' with 'i' a free symbol; students mean sqrt(-1).
        imaginary = sympy.Symbol("i")
        try:
            lhs = lhs.subs(imaginary, sympy.I)
            rhs = rhs.subs(imaginary, sympy.I)
        except Exception:
            return None

    if (lhs.free_symbols | rhs.free_symbols) != {symbol}:
        # The unknown must be the *only* free symbol. Anything else means this
        # is not a step in this variable's solution chain: prose (which
        # parse_latex reads as a product of single-letter symbols), a
        # connective such as '\therefore' or '\Rightarrow' (which parse_latex
        # maps to a symbol and multiplies into the equation), or an
        # un-substituted general formula. Also rejects a line with no unknown
        # at all, e.g. an arithmetic aside.
        # Placed after the 'i' -> sympy.I substitution, so complex answers
        # still pass: sympy.I contributes no free symbols.
        return None
    return sympy.Eq(lhs, rhs)
