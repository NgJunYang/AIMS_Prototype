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


def solution_set(latex: str, variable: str = "x") -> set[str] | None:
    """Return the solution set of a written line as canonical strings.

    Returns None if the line could not be parsed.
    """
    equations = parse_equation_line(latex, variable)
    if not equations:
        return None

    symbol = sympy.Symbol(variable)
    solutions: set[str] = set()
    for equation in equations:
        try:
            roots = sympy.solve(equation, symbol, dict=False)
        except Exception:
            return None
        for root in roots:
            solutions.add(_canonical(root))

    return solutions


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

    verifications: list[StepVerification] = []
    previous: set[str] | None = None

    for step in student_steps:
        current = solution_set(step.latex, variable)

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

    final_correct = previous is not None and expected is not None and previous == expected

    return VerificationReport(
        steps=verifications,
        final_answer_correct=final_correct,
        model_solutions=sorted(expected) if expected else [],
        candidate_misconceptions=classify(verifications, student_steps),
    )


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
