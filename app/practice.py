"""Parameterised practice generation, self-verified with SymPy.

No LLM is involved. A template declares both the equation it generated and the
roots it believes that equation has; the property test in tests/test_practice.py
checks those agree for many seeds, so a broken template cannot reach a student.

Two layers, deliberately separated:

  * A `Problem` is the mathematics - generated once, verified by SymPy, and
    framing-independent.
  * A `Framing` decides how to *phrase* that problem: as a bare "Solve ..."
    instruction, or as a word problem. A framing is handed pre-formatted
    display strings and does no arithmetic of its own, so the prose can never
    drift from the equation it is describing. `compose()` copies the
    mathematics straight off the Problem, which is what makes that structural
    rather than merely tested.

Scenario framings also declare which roots are admissible *in context* - a
plot of land cannot have zero width. That is the pedagogical point: it teaches
when discarding a root is legitimate, in contrast to the
`divided_by_variable_lost_root` misconception, where the same root disappears
unnoticed and it is not.
"""

import random
from dataclasses import dataclass
from typing import Callable

import sympy

from app.models import PracticeQuestion

BARE = "bare"
SCENARIO = "scenario"

QUESTION_TYPES = (BARE, SCENARIO)


@dataclass(frozen=True)
class Problem:
    """The verified mathematics, before anyone decides how to phrase it.

    `equation_sympy` is the ground truth. The `_latex` fields are display
    twins of the same numbers, produced by the same function that produced
    them, so a framing only ever concatenates strings it was handed.
    """

    equation_sympy: str        # "3*x**2 - 7*x", implicitly = 0
    roots_sympy: list[str]     # ["0", "7/3"]
    params: dict[str, int]     # {"a": 3, "b": 7}
    equation_latex: str        # "3x^2 = 7x"
    roots_latex: list[str]     # ["0", "\\frac{7}{3}"], index-aligned


@dataclass(frozen=True)
class Rendered:
    """Presentation only. A framing returns this and can touch nothing else."""

    prompt_latex: str
    answer_latex: str
    admissible_roots: list[str]   # non-empty subset of Problem.roots_sympy
    rejected_note: str = ""       # plain prose, no LaTeX delimiters


@dataclass(frozen=True)
class Framing:
    id: str
    question_type: str
    label: str                              # UI badge text
    applies: Callable[[Problem], bool]      # can this honestly render this problem?
    render: Callable[[Problem], Rendered]


@dataclass(frozen=True)
class Generated:
    prompt_latex: str
    answer_latex: str
    equation_sympy: str
    roots_sympy: list[str]
    question_type: str
    framing_id: str
    admissible_roots: list[str]
    rejected_note: str = ""


@dataclass(frozen=True)
class Template:
    id: str
    misconception_tags: tuple[str, ...]
    make_problem: Callable[[int], Problem]
    framings: tuple[Framing, ...]           # framings[0] must be the bare one

    def generate(self, seed: int, question_type: str = BARE) -> Generated:
        problem = self.make_problem(seed)
        return compose(problem, self.framing_for(problem, question_type))

    def framing_for(self, problem: Problem, question_type: str) -> Framing:
        """The requested type where a framing can honestly carry it, else bare.

        Downgrading is not hidden: Generated.question_type reports what was
        actually produced, never what was asked for.
        """
        if question_type != BARE:
            for framing in self.framings:
                if framing.question_type == question_type and framing.applies(problem):
                    return framing
        return self.framings[0]


def compose(problem: Problem, framing: Framing) -> Generated:
    """The only constructor of `Generated`.

    `equation_sympy` and `roots_sympy` are copied straight off the Problem, so
    a framing physically cannot alter the mathematics of the question it is
    phrasing. A framing that admits no root at all raises here rather than
    handing a student a question with no valid answer.
    """
    rendered = framing.render(problem)
    admissible = list(rendered.admissible_roots)
    if not admissible or not set(admissible) <= set(problem.roots_sympy):
        raise ValueError(
            f"{framing.id}: admissible roots {admissible} are not a non-empty "
            f"subset of {problem.roots_sympy}"
        )
    return Generated(
        prompt_latex=rendered.prompt_latex,
        answer_latex=rendered.answer_latex,
        equation_sympy=problem.equation_sympy,
        roots_sympy=list(problem.roots_sympy),
        question_type=framing.question_type,
        framing_id=framing.id,
        admissible_roots=admissible,
        rejected_note=rendered.rejected_note,
    )


# ---------- the mathematics ----------


def _zero_root_problem(seed: int) -> Problem:
    """a*x^2 = b*x  - the trap is dividing through by x and losing x = 0."""
    rng = random.Random(seed)
    a = rng.randint(1, 4)
    b = rng.randint(2, 12)
    root = sympy.Rational(b, a)
    return Problem(
        equation_sympy=f"{a}*x**2 - {b}*x",
        roots_sympy=["0", str(root)],
        params={"a": a, "b": b},
        equation_latex=f"{_coef(a)}x^2 = {b}x",
        roots_latex=["0", sympy.latex(root)],
    )


def _plus_minus_problem(seed: int) -> Problem:
    """x^2 = k  - the trap is writing only the positive root."""
    rng = random.Random(seed)
    root = rng.randint(2, 12)
    k = root * root
    return Problem(
        equation_sympy=f"x**2 - {k}",
        roots_sympy=[str(root), str(-root)],
        params={"root": root, "k": k},
        equation_latex=f"x^2 = {k}",
        roots_latex=[str(root), f"-{root}"],
    )


def _sign_check_problem(seed: int) -> Problem:
    """x^2 + bx + c = 0 with integer roots of mixed sign - tests sign handling."""
    rng = random.Random(seed)
    p = rng.randint(-9, 9)
    q = rng.randint(-9, 9)
    while p == q:
        q = rng.randint(-9, 9)
    b = -(p + q)
    c = p * q
    return Problem(
        equation_sympy=f"x**2 + ({b})*x + ({c})",
        roots_sympy=[str(p), str(q)],
        params={"p": p, "q": q, "b": b, "c": c},
        equation_latex=f"x^2 {_signed(b)}x {_signed(c)} = 0",
        roots_latex=[str(p), str(q)],
    )


def _coef(a: int) -> str:
    return "" if a == 1 else str(a)


def _signed(value: int) -> str:
    if value == 0:
        return "+ 0"
    return f"+ {value}" if value > 0 else f"- {abs(value)}"


# ---------- framings ----------


def _bare_render(problem: Problem) -> Rendered:
    return Rendered(
        prompt_latex=f"Solve ${problem.equation_latex}$.",
        answer_latex=", \\; ".join(f"x = {r}" for r in problem.roots_latex),
        admissible_roots=list(problem.roots_sympy),
    )


BARE_FRAMING = Framing(
    id="bare",
    question_type=BARE,
    label="Standard",
    applies=lambda _problem: True,
    render=_bare_render,
)


def _garden_render(problem: Problem) -> Rendered:
    """A plot x wide and ax long whose area is b times its width."""
    a = problem.params["a"]
    positive, positive_latex = problem.roots_sympy[1], problem.roots_latex[1]
    return Rendered(
        prompt_latex=(
            f"A rectangular plot of land is $x$ metres wide and "
            f"${_coef(a)}x$ metres long. Its area in square metres is "
            f"{problem.params['b']} times its width. Find the width."
        ),
        answer_latex=f"x = {positive_latex}",
        admissible_roots=[positive],
        rejected_note=(
            "x = 0 solves the equation but not the problem: a plot of land "
            "cannot have zero width. Discarding it here is legitimate - "
            "unlike dividing through by x, which discards it without noticing."
        ),
    )


def _garden_applies(problem: Problem) -> bool:
    """Only when the plot is genuinely rectangular.

    With a = 1 the prose would read "x metres wide and x metres long", which
    describes a square while calling it a rectangle. The mathematics would
    still be correct, but the sentence would not be, so the framing declines
    and the template falls back to a bare question.
    """
    return problem.params["a"] >= 2


GARDEN_AREA = Framing(
    id="garden_area",
    question_type=SCENARIO,
    label="Word problem",
    applies=_garden_applies,
    render=_garden_render,
)


def _courtyard_render(problem: Problem) -> Rendered:
    """A square courtyard of area k."""
    root, root_latex = problem.roots_sympy[0], problem.roots_latex[0]
    return Rendered(
        prompt_latex=(
            f"A square courtyard has an area of {problem.params['k']} square "
            f"metres and a side length of $x$ metres. Find the side length."
        ),
        answer_latex=f"x = {root_latex}",
        admissible_roots=[root],
        rejected_note=(
            f"x = -{problem.params['root']} also satisfies the equation, but a "
            "length cannot be negative, so it is not an answer to this "
            "question. Rejecting it for a stated reason is not the same as "
            "never finding it."
        ),
    )


SQUARE_COURTYARD = Framing(
    id="square_courtyard",
    question_type=SCENARIO,
    label="Word problem",
    applies=lambda _problem: True,
    render=_courtyard_render,
)


def _positive_roots(problem: Problem) -> list[str]:
    return [r for r in problem.roots_sympy if int(r) > 0]


def _profit_applies(problem: Problem) -> bool:
    """Only when at least one root is a positive number of weeks.

    Both roots are drawn from -9..9 and can both be non-positive. A scenario
    admitting no root at all is a question with no answer, so this framing
    declines and the template falls back to bare.
    """
    return bool(_positive_roots(problem))


def _profit_render(problem: Problem) -> Rendered:
    admissible = _positive_roots(problem)
    b, c = problem.params["b"], problem.params["c"]
    rejected = [r for r in problem.roots_sympy if r not in admissible]
    note = ""
    if rejected:
        note = (
            f"x = {rejected[0]} also satisfies the equation, but a number of "
            "weeks cannot be negative or zero here, so it is not an answer to "
            "this question."
        )
    return Rendered(
        prompt_latex=(
            f"A project's balance, in thousands of pounds, is modelled by "
            f"$x^2 {_signed(b)}x {_signed(c)}$ after $x$ weeks. Find when the "
            f"balance is zero."
        ),
        answer_latex=", \\; ".join(f"x = {r}" for r in admissible),
        admissible_roots=admissible,
        rejected_note=note,
    )


PROJECT_BALANCE = Framing(
    id="project_balance",
    question_type=SCENARIO,
    label="Word problem",
    applies=_profit_applies,
    render=_profit_render,
)


TEMPLATES: dict[str, Template] = {
    "quad_zero_root": Template(
        id="quad_zero_root",
        misconception_tags=("divided_by_variable_lost_root", "lost_solution"),
        make_problem=_zero_root_problem,
        framings=(BARE_FRAMING, GARDEN_AREA),
    ),
    "quad_plus_minus": Template(
        id="quad_plus_minus",
        misconception_tags=("dropped_plus_minus",),
        make_problem=_plus_minus_problem,
        framings=(BARE_FRAMING, SQUARE_COURTYARD),
    ),
    "quad_sign_check": Template(
        id="quad_sign_check",
        misconception_tags=(
            "sign_error",
            "gained_solution",
            "squaring_introduced_spurious_root",
            "no_working_shown",
        ),
        make_problem=_sign_check_problem,
        framings=(BARE_FRAMING, PROJECT_BALANCE),
    ),
}

_FALLBACK = "quad_sign_check"


def generate_practice(
    misconception_tags: list[str],
    count: int = 3,
    seed: int | None = None,
    question_type: str = BARE,
) -> list[PracticeQuestion]:
    """Produce `count` practice questions targeting the given misconceptions.

    Cycles through the matching templates so a student with one misconception
    still gets several distinct problems.
    """
    matching = [
        template
        for template in TEMPLATES.values()
        if any(tag in template.misconception_tags for tag in misconception_tags)
    ]
    if not matching:
        matching = [TEMPLATES[_FALLBACK]]

    base = seed if seed is not None else random.randint(0, 10_000)

    questions: list[PracticeQuestion] = []
    seen_prompts: set[str] = set()

    # Consecutive seeds can draw the same small parameters, so asking for three
    # questions can hand a student the same one twice. Keep advancing the seed
    # until we have `count` distinct prompts. The attempt budget is a safety net
    # only - a template with fewer than `count` distinct outputs would otherwise
    # spin forever - and on exhaustion we return duplicates rather than fewer
    # questions than asked for.
    attempt = 0
    while len(questions) < count and attempt < count * 20:
        template = matching[len(questions) % len(matching)]
        generated = template.generate(base + attempt, question_type)
        attempt += 1
        if generated.prompt_latex in seen_prompts:
            continue
        seen_prompts.add(generated.prompt_latex)
        questions.append(_to_question(generated, template, misconception_tags))

    while len(questions) < count:
        template = matching[len(questions) % len(matching)]
        questions.append(
            _to_question(
                template.generate(base + len(questions), question_type),
                template,
                misconception_tags,
            )
        )

    return questions


def _to_question(
    generated: Generated, template: Template, misconception_tags: list[str]
) -> PracticeQuestion:
    tag = next(
        (t for t in misconception_tags if t in template.misconception_tags),
        template.misconception_tags[0],
    )
    return PracticeQuestion(
        prompt_latex=generated.prompt_latex,
        answer_latex=generated.answer_latex,
        misconception_tag=tag,
        template_id=template.id,
        question_type=generated.question_type,
        framing_id=generated.framing_id,
        admissible_roots=generated.admissible_roots,
        rejected_note=generated.rejected_note,
    )
