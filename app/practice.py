"""Parameterised practice generation, self-verified with SymPy.

No LLM is involved. A template declares both the equation it generated and the
roots it believes that equation has; the property test in tests/test_practice.py
checks those agree for many seeds, so a broken template cannot reach a student.
"""

import random
from dataclasses import dataclass
from typing import Callable

import sympy

from app.models import PracticeQuestion


@dataclass(frozen=True)
class Generated:
    prompt_latex: str
    answer_latex: str
    equation_sympy: str   # e.g. "x**2 - 5*x + 6"  (implicitly = 0)
    roots_sympy: list[str]


@dataclass(frozen=True)
class Template:
    id: str
    misconception_tags: tuple[str, ...]
    generate: Callable[[int], Generated]


def _zero_root(seed: int) -> Generated:
    """a*x^2 = b*x  — the trap is dividing through by x and losing x = 0."""
    rng = random.Random(seed)
    a = rng.randint(1, 4)
    b = rng.randint(2, 12)
    prompt = f"{_coef(a)}x^2 = {b}x"
    root = sympy.Rational(b, a)
    return Generated(
        prompt_latex=f"Solve ${prompt}$.",
        answer_latex=f"x = 0, \\; x = {sympy.latex(root)}",
        equation_sympy=f"{a}*x**2 - {b}*x",
        roots_sympy=["0", str(root)],
    )


def _plus_minus(seed: int) -> Generated:
    """x^2 = k  — the trap is writing only the positive root."""
    rng = random.Random(seed)
    root = rng.randint(2, 12)
    k = root * root
    return Generated(
        prompt_latex=f"Solve $x^2 = {k}$.",
        answer_latex=f"x = {root}, \\; x = -{root}",
        equation_sympy=f"x**2 - {k}",
        roots_sympy=[str(root), str(-root)],
    )


def _sign_check(seed: int) -> Generated:
    """x^2 + bx + c = 0 with integer roots of mixed sign — tests sign handling."""
    rng = random.Random(seed)
    p = rng.randint(-9, 9)
    q = rng.randint(-9, 9)
    while p == q:
        q = rng.randint(-9, 9)
    b = -(p + q)
    c = p * q
    prompt = f"x^2 {_signed(b)}x {_signed(c)} = 0"
    return Generated(
        prompt_latex=f"Solve ${prompt}$.",
        answer_latex=f"x = {p}, \\; x = {q}",
        equation_sympy=f"x**2 + ({b})*x + ({c})",
        roots_sympy=[str(p), str(q)],
    )


def _coef(a: int) -> str:
    return "" if a == 1 else str(a)


def _signed(value: int) -> str:
    if value == 0:
        return "+ 0"
    return f"+ {value}" if value > 0 else f"- {abs(value)}"


TEMPLATES: dict[str, Template] = {
    "quad_zero_root": Template(
        id="quad_zero_root",
        misconception_tags=("divided_by_variable_lost_root", "lost_solution"),
        generate=_zero_root,
    ),
    "quad_plus_minus": Template(
        id="quad_plus_minus",
        misconception_tags=("dropped_plus_minus",),
        generate=_plus_minus,
    ),
    "quad_sign_check": Template(
        id="quad_sign_check",
        misconception_tags=(
            "sign_error",
            "gained_solution",
            "squaring_introduced_spurious_root",
            "no_working_shown",
        ),
        generate=_sign_check,
    ),
}

_FALLBACK = "quad_sign_check"


def generate_practice(
    misconception_tags: list[str], count: int = 3, seed: int | None = None
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
        generated = template.generate(base + attempt)
        attempt += 1
        if generated.prompt_latex in seen_prompts:
            continue
        seen_prompts.add(generated.prompt_latex)
        questions.append(_to_question(generated, template, misconception_tags))

    while len(questions) < count:
        template = matching[len(questions) % len(matching)]
        questions.append(
            _to_question(
                template.generate(base + len(questions)), template, misconception_tags
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
    )
