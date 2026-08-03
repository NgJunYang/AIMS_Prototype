"""Deterministic symbolic verification of a chain of student working.

This module is the only component permitted to assert mathematical truth.
It contains no LLM calls, no network access and no file I/O, which is what
makes it exhaustively testable.

Model: each written line is an equation and therefore denotes a solution set.
A legitimate algebraic step preserves that set. Comparing the solution set of
line n with line n-1 classifies what went wrong:

    shrank  -> a root was discarded (dividing by the unknown, dropping the +/-)
    grew    -> a spurious root appeared (e.g. squaring both sides)
    changed -> an algebra or arithmetic error
"""

import sympy

from app.latex_utils import parse_equation_line
from app.models import Step, StepVerification, VerificationReport


# A line that is true for whatever the unknown is ('x(x - 5) = x^2 - 5x', which
# is how a student checks their own factorisation) carries no information about
# the solution set. sympy.solve returns [] for it, which is indistinguishable
# from "no solutions" - so it needs its own outcome, or an identity reads as
# "every root was lost".
TAUTOLOGY = object()


def solution_set(latex: str, variable: str = "x") -> set[str] | None | object:
    """Return the solution set of a written line as canonical strings.

    Four possible outcomes, and the differences between them are load-bearing:

        None           -> could not be read as mathematics; do not judge it
        TAUTOLOGY      -> true for all values of the unknown; carries no
                          information, so it must not be compared
        set()          -> parsed, and genuinely has no solutions ('x + 1 = x + 2')
        non-empty set  -> the solutions, as canonical strings
    """
    equations = parse_equation_line(latex, variable)
    if not equations:
        return None

    symbol = sympy.Symbol(variable)
    solutions: set[str] = set()
    for equation in equations:
        if _is_tautology(equation):
            return TAUTOLOGY
        try:
            roots = sympy.solve(equation, symbol, dict=False)
        except Exception:
            return None
        for root in roots:
            solutions.add(_canonical(root))

    return solutions


def _is_tautology(equation: sympy.Basic) -> bool:
    """True when this equation holds for every value of the unknown.

    ``sympy.Eq`` auto-evaluates, so ``parse_equation_line`` can hand back a
    bare ``BooleanTrue`` ('x = x'), which has no ``.lhs``. ``BooleanFalse``
    ('x + 1 = x + 2') has no ``.lhs`` either, so it correctly falls through to
    being solved and reported as a genuinely empty solution set.

    ``expand`` rather than ``simplify``: sufficient for polynomial work at this
    level and far cheaper.
    """
    if equation is sympy.true:
        return True
    if not hasattr(equation, "lhs"):
        return False
    try:
        return sympy.expand(equation.lhs - equation.rhs) == 0
    except Exception:
        return False


def _canonical(expression: sympy.Expr) -> str:
    """A stable, readable string form so that 6/2 and 3 compare equal.

    The same string is shown in the UI and handed to the marking model, so it
    has to be both canonical and human-readable: '0', '5', '-2 + sqrt(3)'.
    """
    try:
        simplified = sympy.simplify(expression)
    except Exception:
        return str(expression)
    try:
        simplified = sympy.nsimplify(simplified)
    except Exception:
        pass
    return str(simplified)


def verify(
    student_steps: list[Step],
    model_solution_steps: list[str],
    variable: str = "x",
) -> VerificationReport:
    """Verify a chain of student steps against the model solution."""
    expected = _model_solution_set(model_solution_steps, variable)

    outcomes = [solution_set(step.latex, variable) for step in student_steps]
    # A student may write one root per line. Those lines are one logical answer,
    # so they are read together rather than each being compared to the last.
    runs = _answer_runs(outcomes)

    verifications: list[StepVerification] = []
    previous: set[str] | None = None

    for position, step in enumerate(student_steps):
        current = outcomes[position]

        if current is None:
            verifications.append(
                StepVerification(
                    index=step.index,
                    parsed=False,
                    divergence="unparseable",
                    note="This line could not be interpreted as mathematics.",
                )
            )
            # Do not update `previous`: compare the next parseable line to the
            # last one we actually understood.
            continue

        if current is TAUTOLOGY:
            verifications.append(
                StepVerification(
                    index=step.index,
                    parsed=True,
                    equivalent_to_previous=True,
                    divergence=None,
                    solutions=[],
                    note="This line is an identity; it neither gains nor loses solutions.",
                )
            )
            # An identity is a valid step that says nothing about the solution
            # set, so `previous` must survive it untouched.
            continue

        run = runs.get(position)
        if run is not None and position != run[-1]:
            # An earlier line of a multi-line answer. Report it so the frontend
            # can still index by step number, but pass no verdict on it and
            # leave `previous` alone: the verdict lands on the last line of the
            # run, against the union of the whole run.
            verifications.append(
                StepVerification(
                    index=step.index,
                    parsed=True,
                    solutions=sorted(current),
                    equivalent_to_previous=None,
                    divergence=None,
                    note=(
                        "Part of a multi-line answer; read together with the "
                        "following line(s)."
                    ),
                )
            )
            continue

        if run is not None:
            current = set().union(*(outcomes[index] for index in run))

        verification = StepVerification(
            index=step.index,
            parsed=True,
            solutions=sorted(current),
        )

        if previous is not None:
            verification.equivalent_to_previous = current == previous
            if current != previous:
                lost = previous - current
                gained = current - previous
                verification.lost_roots = sorted(lost)
                verification.gained_roots = sorted(gained)
                if lost and not gained:
                    verification.divergence = "lost_roots"
                elif gained and not lost:
                    verification.divergence = "gained_roots"
                else:
                    verification.divergence = "different_roots"

        verifications.append(verification)
        previous = current

    # `previous` is the last line that *parsed*, so without this an unparseable
    # final line would silently award the answer mark on the strength of an
    # intermediate line. An identity as the last line says nothing either. And
    # if the model solution did not parse there is nothing to compare against.
    last_outcome = outcomes[-1] if outcomes else None
    answer_established = (
        previous is not None
        and expected is not None
        and last_outcome is not None
        and last_outcome is not TAUTOLOGY
    )
    final_correct = answer_established and previous == expected

    return VerificationReport(
        steps=verifications,
        final_answer_correct=final_correct,
        final_answer_verified=answer_established,
        model_solutions=sorted(expected) if expected is not None else [],
        candidate_misconceptions=classify(verifications, student_steps),
    )


def _states_a_single_root(outcome: set[str] | None | object) -> bool:
    """True when a line says exactly 'the unknown is this one constant'.

    Deliberately decided from the solution set rather than from the LaTeX: one
    solution, and that solution is a single value with no free symbols left in
    it. A line stating two roots at once ('x = 2, x = 3') is already a complete
    answer and is not part of a run.
    """
    if not isinstance(outcome, set) or len(outcome) != 1:
        return False
    try:
        return not sympy.sympify(next(iter(outcome))).free_symbols
    except Exception:
        return False


def _answer_runs(outcomes: list[set[str] | None | object]) -> dict[int, list[int]]:
    """Group consecutive single-root lines, so 'x = 2' then 'x = 3' is one answer.

    Maps each position in a run of two or more onto the whole run. A run of one
    is absent from the mapping and so behaves exactly as it always has: a
    single 'x = 5' after 'x^2 = 5x' is still a lost root, not half an answer.
    """
    runs: dict[int, list[int]] = {}
    start = 0
    while start < len(outcomes):
        if not _states_a_single_root(outcomes[start]):
            start += 1
            continue
        end = start
        while end + 1 < len(outcomes) and _states_a_single_root(outcomes[end + 1]):
            end += 1
        if end > start:
            positions = list(range(start, end + 1))
            for position in positions:
                runs[position] = positions
        start = end + 1
    return runs


def _model_solution_set(model_solution_steps: list[str], variable: str) -> set[str] | None:
    """The expected answer is the solution set of the last parseable model line."""
    for latex in reversed(model_solution_steps):
        solutions = solution_set(latex, variable)
        if solutions is not None:
            return solutions
    return None


def classify(
    verifications: list[StepVerification], student_steps: list[Step]
) -> list[str]:
    """Map divergence shapes onto named misconception tags.

    Deliberately conservative: these are *candidates* offered to the marking
    model, not conclusions. The marker may reject them.
    """
    by_index = {step.index: step for step in student_steps}
    tags: list[str] = []

    for verification in verifications:
        if verification.divergence is None:
            continue

        previous_step = by_index.get(verification.index - 1, None)
        previous_text = previous_step.latex if previous_step else ""

        if verification.divergence == "lost_roots":
            if "0" in verification.lost_roots:
                tags.append("divided_by_variable_lost_root")
            elif _is_plus_minus_pair(verification.lost_roots, verification.solutions):
                tags.append("dropped_plus_minus")
            else:
                tags.append("lost_solution")

        elif verification.divergence == "gained_roots":
            if "^2" in previous_text or "sqrt" in previous_text:
                tags.append("squaring_introduced_spurious_root")
            else:
                tags.append("gained_solution")

        elif verification.divergence == "different_roots":
            tags.append("sign_error")

    # Preserve order, remove duplicates.
    return list(dict.fromkeys(tags))


def _is_plus_minus_pair(lost: list[str], kept: list[str]) -> bool:
    """True when exactly the negative counterpart of a kept root was dropped."""
    if len(lost) != 1 or len(kept) != 1:
        return False
    try:
        return sympy.simplify(sympy.sympify(lost[0]) + sympy.sympify(kept[0])) == 0
    except Exception:
        return False
