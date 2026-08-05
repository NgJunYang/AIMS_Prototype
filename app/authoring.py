"""Checking lecturer-authored questions before they can mark anybody.

`tests/test_seed_integrity.py` guarantees that every seeded model solution
parses and verifies against itself - the highest-value test in the project,
because a model solution that is wrong marks every student against it wrongly.

Once a lecturer can add questions at runtime, that guarantee has to move from
test time to write time. `validate_question` runs the same SymPy verification
the integrity test runs, so a question whose own model solution loses a root,
gains one, or cannot be read is refused at the point of saving. The tool holds
the lecturer to exactly the standard it holds the student to.

No LLM is involved. Every judgement here is SymPy's or a field check.
"""

import re

from app.models import Criterion, Question, Step
from app.verifier import solution_set, verify

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

# Deliberately method-agnostic: a rubric naming one method would penalise a
# student who solved it correctly by another. This mirrors the phrasing used
# by the seeded questions.
DEFAULT_CRITERIA: list[dict] = [
    {
        "id": "C1",
        "max": 1,
        "description": "Recognised the equation is in, or rearranged it to, a form suitable for solving",
    },
    {
        "id": "C2",
        "max": 3,
        "description": "Applied a valid solution method without losing or gaining solutions",
    },
    {
        "id": "C3",
        "max": 2,
        "description": "Carried out the algebra and arithmetic correctly",
    },
    {"id": "C4", "max": 1, "description": "Stated all solutions"},
    {"id": "C5", "max": 1, "description": "Working is clear and logically ordered"},
]


def default_criteria() -> list[Criterion]:
    """A fresh copy of the default rubric, safe for the caller to edit."""
    return [Criterion(**entry) for entry in DEFAULT_CRITERIA]


def validate_question(question: Question) -> list[str]:
    """Everything wrong with this question, in plain English. Empty means sound."""
    return _field_problems(question) + _mathematical_problems(question)


def _field_problems(question: Question) -> list[str]:
    problems: list[str] = []

    if not _ID_PATTERN.match(question.id or ""):
        problems.append(
            "The id must start with a letter or digit and contain only letters, "
            "digits, hyphens and underscores."
        )
    if not (question.prompt or "").strip():
        problems.append("The prompt cannot be empty.")
    if len(question.variable or "") != 1 or not question.variable.isalpha():
        problems.append("The variable must be a single letter, such as x.")

    if not question.criteria:
        problems.append("A rubric needs at least one criterion.")
    else:
        ids = [c.id for c in question.criteria]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            problems.append(
                f"Duplicate criterion ids: {', '.join(sorted(duplicates))}."
            )
        if sum(c.max for c in question.criteria) < 1:
            problems.append("The rubric must be worth at least one mark in total.")

    if len(question.model_solution_steps) < 2:
        problems.append(
            "A model solution needs at least two steps: one line is a statement, "
            "not working a student can be marked against."
        )

    return problems


def _mathematical_problems(question: Question) -> list[str]:
    """Run the lecturer's own model solution through the student verifier."""
    if len(question.model_solution_steps) < 2:
        return []  # already reported; verifying one line says nothing useful

    problems: list[str] = []
    for index, latex in enumerate(question.model_solution_steps, start=1):
        if solution_set(latex, question.variable) is None:
            problems.append(
                f"Step {index} could not be read as mathematics in "
                f"'{question.variable}': {latex!r}"
            )
    if problems:
        return problems

    steps = [
        Step(index=i, latex=latex)
        for i, latex in enumerate(question.model_solution_steps, start=1)
    ]
    report = verify(steps, question.model_solution_steps, question.variable)

    if report.first_divergence_index is not None:
        diverged = next(
            s for s in report.steps if s.index == report.first_divergence_index
        )
        detail = {
            "lost_roots": f"it loses {', '.join(diverged.lost_roots)}",
            "gained_roots": f"it introduces {', '.join(diverged.gained_roots)}",
            "different_roots": (
                f"it changes the solutions from {', '.join(diverged.lost_roots)} "
                f"to {', '.join(diverged.gained_roots)}"
            ),
        }.get(diverged.divergence or "", "it changes the solution set")
        problems.append(
            f"The model solution does not follow from itself at step "
            f"{report.first_divergence_index}: {detail}. A student marked "
            f"against this would be marked wrongly."
        )
    elif not report.final_answer_correct:
        problems.append(
            "The final line of the model solution does not match the equation "
            "it started from."
        )

    return problems
