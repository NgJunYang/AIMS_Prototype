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

Two kinds of line are not solution sets to be compared, and treating them as
such invents errors that the student did not make: a line that could not be
parsed, and a line that is an identity (true for every value of the unknown).
Both are skipped, leaving the comparison to run between the lines either side.
One answer written over several lines ('x = 2' then 'x = 3') is likewise read
as a single logical step.
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

    A written line is a list of branches (alternative answers, e.g.
    'x = 2, x = 3'), and each branch is a chain of one or more equations that
    must all hold at once ('a = b = c' is two links: Eq(a, b) and Eq(b, c)).
    So a branch's contribution is the *intersection* of its links' roots, and
    the line's solution set is the *union* of its branches' contributions.
    For every branch of length 1 - which is every line with at most one '='
    per branch, i.e. the entire pre-chain-equality test suite - this is
    exactly the old union-only logic: intersecting a single set with itself
    is a no-op.
    """
    branches = parse_equation_line(latex, variable)
    if not branches:
        return None

    symbol = sympy.Symbol(variable)
    solutions: set[str] = set()
    for branch in branches:
        if all(_is_tautology(link) for link in branch):
            # Matches the old short-circuit exactly for a length-1 branch: any
            # equation in the OR-list being an identity discards the whole
            # line, in order, the same as today. For a longer chain, this
            # means *every* link is an identity (true chain of substitutions
            # rather than a constraint), which carries the same "no
            # information" meaning.
            return TAUTOLOGY
        try:
            branch_solutions: set[str] | None = None
            for link in branch:
                if _is_tautology(link):
                    # A tautological link contributes no constraint of its
                    # own (e.g. the professor's "x^2-5x+6 = (x-2)(x-3)" half of
                    # a chain, which is an algebraic identity); it must not
                    # shrink the intersection to nothing.
                    continue
                roots = {_canonical(root) for root in sympy.solve(link, symbol, dict=False)}
                branch_solutions = roots if branch_solutions is None else branch_solutions & roots
        except Exception:
            return None
        solutions |= branch_solutions if branch_solutions is not None else set()

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


def _is_transparent(outcome: set[str] | None | object) -> bool:
    """True for a line that carries no solution set to compare.

    An unparseable line and an identity are both skipped by verify() without
    disturbing `previous`, so they must not break up an answer either: a
    student can write 'x = 2', a note in words, then 'x = 3'.
    """
    return outcome is None or outcome is TAUTOLOGY


def _answer_runs(outcomes: list[set[str] | None | object]) -> dict[int, list[int]]:
    """Group single-root lines that state *different* roots into one answer.

    Maps each position in a run of two or more onto the whole run. A run of one
    is absent from the mapping and so behaves exactly as it always has: a
    single 'x = 5' after 'x^2 = 5x' is still a lost root, not half an answer.

    Two adjacent lines stating the *same* root are not a two-part answer, they
    are an ordinary step ('2x = 4' then 'x = 2'), so they are left alone and
    compared to each other as usual. Listing *different* roots is what makes a
    multi-line answer.
    """
    runs: dict[int, list[int]] = {}

    def close(group: list[int]) -> None:
        if len(group) > 1:
            for position in group:
                runs[position] = list(group)

    members: list[int] = []
    for position, outcome in enumerate(outcomes):
        if _is_transparent(outcome):
            continue
        if not _states_a_single_root(outcome):
            close(members)
            members = []
            continue
        if members and outcomes[members[-1]] == outcome:
            # Restating the same root ends the run and begins a new one here.
            close(members)
            members = [position]
            continue
        members.append(position)
    close(members)
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
