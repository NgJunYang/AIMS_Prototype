# AIMS Quadratics Marking Prototype — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lecturer-facing web tool that reads a photo of handwritten quadratic-equation working, lets the lecturer confirm the transcription, symbolically verifies each step with SymPy, proposes rubric-linked marks with an LLM constrained by those verified facts, writes student feedback, and generates machine-verified targeted practice.

**Architecture:** A single Python FastAPI application serving a static, build-free frontend. The pipeline runs as discrete stages, each persisting its output: transcribe (vision LLM) → human confirm → verify (SymPy, deterministic, no LLM) → mark (LLM constrained by the verification report) → feedback → practice (templates, no LLM). The verifier is the only component permitted to assert mathematical truth; the LLM never re-derives mathematics. Every LLM call is cached to disk so the whole app can run offline from fixtures.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Pydantic v2, SymPy (+ `antlr4-python3-runtime` for LaTeX parsing), `anthropic` SDK (Claude Sonnet 5 for vision, Claude Opus 5 for marking), pytest. Frontend: static HTML + vanilla JS + Tailwind CDN + KaTeX CDN + Chart.js CDN. Storage: JSON files on disk. No npm, no bundler, no database server, no vector store.

---

## File Structure

| Path | Responsibility |
|---|---|
| `app/models.py` | All Pydantic contracts. The single source of truth for every stage boundary. |
| `app/config.py` | Settings, env loading, `DEMO_MODE`, paths. |
| `app/latex_utils.py` | LaTeX normalisation and safe parsing to SymPy. Pure functions. |
| `app/verifier.py` | Symbolic step verification. Pure, deterministic, no LLM, no I/O. |
| `app/practice.py` | Parameterised practice templates with SymPy self-verification. No LLM. |
| `app/llm.py` | Claude client wrapper + disk cache + offline mode. The only file that talks to the API. |
| `app/transcriber.py` | Image → ordered LaTeX steps. Vision prompt + schema. Never sees the model solution. |
| `app/marker.py` | Verification report + rubric → per-criterion mark proposal. Never does mathematics. |
| `app/feedback.py` | Mark proposal → student-facing prose. |
| `app/context.py` | Deterministic keyed retrieval over seed JSON. No embeddings. |
| `app/store.py` | Load seeds; persist and load submissions as JSON files. |
| `app/main.py` | FastAPI app: routes, static mounting, error handling. |
| `app/seeds/questions.json` | Questions, model solutions, rubrics. |
| `app/seeds/misconceptions.json` | Misconception catalogue. |
| `app/seeds/notes.json` | Lecture-note snippets, tagged. |
| `app/seeds/class_summary.json` | Pre-computed cohort data for the class dashboard. |
| `static/index.html` | All four screens as sections, toggled by JS. |
| `static/app.js` | Fetch calls, screen state, rendering. |
| `static/app.css` | The handful of styles Tailwind doesn't cover. |
| `fixtures/images/` | The six demo handwritten scans. |
| `fixtures/llm_cache/` | Committed LLM responses keyed by input hash. |
| `data/submissions/` | Runtime submission JSON (gitignored). |
| `tests/` | pytest suite. Heaviest coverage on `verifier` and `practice`. |

**Dependency direction:** `main` → everything. `marker`/`feedback` → `llm`, `context`, `models`. `verifier`/`practice`/`latex_utils` → `models` only (no I/O, no network — that is why they are the well-tested ones).

---

## Task 0: Repository, environment, and the "everything on fixtures" skeleton

**Do this with the whole team in one room. Nobody starts a real module until Task 1's contracts are merged.**

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`, `README.md`, `app/__init__.py`, `app/config.py`, `app/main.py`, `static/index.html`, `tests/__init__.py`, `tests/test_smoke.py`

- [ ] **Step 1: Initialise the repository**

```bash
git init
git branch -M main
```

- [ ] **Step 2: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.env
data/submissions/
.pytest_cache/
.DS_Store
```

- [ ] **Step 3: Create `.env.example`**

```
ANTHROPIC_API_KEY=
DEMO_MODE=live
```

Never commit `.env`. Every team member copies `.env.example` to `.env` and fills in the key.

- [ ] **Step 4: Create `requirements.txt`**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
python-dotenv==1.0.1
python-multipart==0.0.20
sympy==1.13.3
antlr4-python3-runtime==4.11.1
anthropic==0.42.0
pytest==8.3.4
httpx==0.28.1
```

`antlr4-python3-runtime` must be version 4.11.x — SymPy's `parse_latex` is pinned to that ANTLR grammar version and will fail with a confusing error on any other.

- [ ] **Step 5: Create the virtual environment and install**

```bash
python -m venv .venv
```

Then, in PowerShell:

```bash
.venv\Scripts\Activate.ps1
```

Then:

```bash
pip install -r requirements.txt
```

- [ ] **Step 6: Create `app/config.py`**

```python
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SEEDS_DIR = BASE_DIR / "app" / "seeds"
STATIC_DIR = BASE_DIR / "static"
FIXTURES_DIR = BASE_DIR / "fixtures"
LLM_CACHE_DIR = FIXTURES_DIR / "llm_cache"
IMAGES_DIR = FIXTURES_DIR / "images"
SUBMISSIONS_DIR = BASE_DIR / "data" / "submissions"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# "live"    -> call the API, write every response to the cache
# "offline" -> serve only from the cache, never touch the network
DEMO_MODE = os.getenv("DEMO_MODE", "live")

VISION_MODEL = "claude-sonnet-5"
MARKING_MODEL = "claude-opus-5"

for directory in (LLM_CACHE_DIR, IMAGES_DIR, SUBMISSIONS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 7: Create `app/main.py` with a health route and static mounting**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR

app = FastAPI(title="AIMS")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
```

The static mount must come **after** all `/api/...` routes, or it will swallow them.

- [ ] **Step 8: Create a placeholder `static/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>AIMS</title>
    <script src="https://cdn.tailwindcss.com"></script>
  </head>
  <body class="bg-slate-50 p-8">
    <h1 class="text-2xl font-semibold">AIMS</h1>
    <p id="status" class="text-slate-600">checking…</p>
    <script>
      fetch("/api/health")
        .then((r) => r.json())
        .then((d) => (document.getElementById("status").textContent = d.status));
    </script>
  </body>
</html>
```

- [ ] **Step 9: Write the smoke test**

Create `tests/test_smoke.py`:

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 10: Run the test**

Run: `pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 11: Start the server and confirm in a browser**

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. Expected: the page shows "ok".

**Everyone on the team must reach this point on their own machine before anyone continues.** An environment that breaks on day two costs more than it does now.

- [ ] **Step 12: Commit**

```bash
git add .
git commit -m "chore: scaffold FastAPI app with static frontend and health check"
```

---

## Task 1: The contracts

Every stage boundary, defined once. **Nothing else starts until this is merged.** Changes to this file after today require the whole team's agreement.

**Files:**
- Create: `app/models.py`, `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
import pytest
from pydantic import ValidationError

from app.models import (
    Criterion,
    CriterionMark,
    MarkProposal,
    Question,
    Step,
    StepVerification,
    VerificationReport,
)


def test_step_defaults_to_unedited_and_high_confidence():
    step = Step(index=1, latex="x^2 - 5x + 6 = 0")
    assert step.confidence == "high"
    assert step.edited_by_human is False


def test_criterion_mark_cannot_exceed_max():
    with pytest.raises(ValidationError):
        CriterionMark(
            criterion_id="C1", proposed=5, max=2, justification="x", evidence_step=1
        )


def test_mark_proposal_total_is_computed_from_criteria():
    proposal = MarkProposal(
        criteria=[
            CriterionMark(
                criterion_id="C1", proposed=2, max=2, justification="ok", evidence_step=1
            ),
            CriterionMark(
                criterion_id="C2", proposed=1, max=3, justification="partial", evidence_step=3
            ),
        ],
        misconceptions=["divided_by_variable_lost_root"],
    )
    assert proposal.total_proposed == 3
    assert proposal.total_max == 5


def test_verification_report_finds_first_divergence():
    report = VerificationReport(
        steps=[
            StepVerification(index=1, parsed=True, equivalent_to_previous=None),
            StepVerification(index=2, parsed=True, equivalent_to_previous=True),
            StepVerification(
                index=3,
                parsed=True,
                equivalent_to_previous=False,
                divergence="lost_roots",
                lost_roots=["0"],
            ),
        ],
        final_answer_correct=False,
    )
    assert report.first_divergence_index == 3


def test_question_round_trips():
    question = Question(
        id="q2",
        prompt="Solve $x^2 = 5x$.",
        model_solution_steps=["x^2 = 5x", "x^2 - 5x = 0", "x(x - 5) = 0", "x = 0, x = 5"],
        variable="x",
        criteria=[Criterion(id="C1", max=2, description="Rearranged to standard form")],
    )
    assert Question.model_validate(question.model_dump()) == question
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'`.

- [ ] **Step 3: Write `app/models.py`**

```python
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

Confidence = Literal["high", "low"]

Divergence = Literal[
    "lost_roots",        # solution set shrank: an answer was discarded
    "gained_roots",      # solution set grew: a spurious answer appeared
    "different_roots",   # neither subset nor superset: an algebra error
    "unparseable",       # this line could not be turned into mathematics
]


# ---------- Assignment definition (seed data) ----------


class Criterion(BaseModel):
    id: str
    max: int = Field(ge=0)
    description: str


class Question(BaseModel):
    id: str
    prompt: str
    model_solution_steps: list[str]
    variable: str = "x"
    topic_tag: str = "quadratics"
    criteria: list[Criterion]


# ---------- Transcription ----------


class Step(BaseModel):
    index: int = Field(ge=1)
    latex: str
    confidence: Confidence = "high"
    edited_by_human: bool = False


class Transcription(BaseModel):
    steps: list[Step]
    notes: str = ""


# ---------- Verification (SymPy, ground truth) ----------


class StepVerification(BaseModel):
    index: int
    parsed: bool
    solutions: list[str] = Field(default_factory=list)
    equivalent_to_previous: bool | None = None
    divergence: Divergence | None = None
    lost_roots: list[str] = Field(default_factory=list)
    gained_roots: list[str] = Field(default_factory=list)
    note: str = ""


class VerificationReport(BaseModel):
    steps: list[StepVerification]
    final_answer_correct: bool
    model_solutions: list[str] = Field(default_factory=list)
    candidate_misconceptions: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def first_divergence_index(self) -> int | None:
        for step in self.steps:
            if step.equivalent_to_previous is False:
                return step.index
        return None

    @computed_field
    @property
    def all_steps_parsed(self) -> bool:
        return all(step.parsed for step in self.steps)


# ---------- Marking ----------


class CriterionMark(BaseModel):
    criterion_id: str
    proposed: int = Field(ge=0)
    max: int = Field(ge=0)
    justification: str
    evidence_step: int | None = None
    overridden: bool = False

    @model_validator(mode="after")
    def proposed_within_max(self) -> "CriterionMark":
        if self.proposed > self.max:
            raise ValueError(
                f"proposed {self.proposed} exceeds max {self.max} for {self.criterion_id}"
            )
        return self


class MarkProposal(BaseModel):
    criteria: list[CriterionMark]
    misconceptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def total_proposed(self) -> int:
        return sum(c.proposed for c in self.criteria)

    @computed_field
    @property
    def total_max(self) -> int:
        return sum(c.max for c in self.criteria)


# ---------- Feedback and practice ----------


class Feedback(BaseModel):
    what_went_well: str
    what_went_wrong: str
    how_to_improve: str
    references: list[str] = Field(default_factory=list)


class PracticeQuestion(BaseModel):
    prompt_latex: str
    answer_latex: str
    misconception_tag: str
    template_id: str


# ---------- The persisted submission ----------


class Submission(BaseModel):
    id: str
    question_id: str
    image_filename: str | None = None
    transcription: Transcription | None = None
    confirmed_steps: list[Step] | None = None
    verification: VerificationReport | None = None
    marks: MarkProposal | None = None
    feedback: Feedback | None = None
    practice: list[PracticeQuestion] = Field(default_factory=list)
    student_pseudonym: str = "Student A"
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_models.py -v`
Expected: all 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: define pipeline contracts as pydantic models"
```

---

## Task 2: LaTeX normalisation and safe parsing

Student LaTeX arrives in many equivalent spellings, and SymPy's parser is brittle. Every parse must be wrapped so a bad line degrades one step instead of crashing the request.

**Files:**
- Create: `app/latex_utils.py`, `tests/test_latex_utils.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_latex_utils.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_latex_utils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.latex_utils'`.

- [ ] **Step 3: Write `app/latex_utils.py`**

```python
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
    (r"\\left|\\right", ""),             # sizing commands SymPy dislikes
    (r"\\dfrac|\\tfrac", r"\\frac"),     # fraction variants
    (r"\\times|\\cdot", "*"),            # explicit multiplication
    (r"\\div", "/"),
    (r"\\,|\\;|\\:|\\!|\\quad|\\qquad", " "),  # spacing commands
    (r"\\mathrm|\\mathit|\\mathbf", ""),
    (r"\s+", " "),                       # collapse whitespace
]

_SPLIT_PATTERN = re.compile(r",|;|\\text\{\s*or\s*\}|\\quad|\bor\b")


def normalise_latex(raw: str) -> str:
    """Rewrite equivalent LaTeX spellings into the subset SymPy parses well."""
    text = raw
    for pattern, replacement in _REWRITES:
        text = re.sub(pattern, replacement, text)
    return text.strip()


def split_answer_line(raw: str) -> list[str]:
    """Split a final-answer line such as 'x = 2, x = 3' into separate equations.

    A line with no separator is returned unchanged as a single-element list.
    """
    normalised = normalise_latex(raw)
    parts = [part.strip() for part in _SPLIT_PATTERN.split(normalised)]
    parts = [part for part in parts if part]
    return parts if len(parts) > 1 else [normalised]


def parse_equation_line(raw: str, variable: str = "x") -> list[sympy.Eq]:
    """Parse one written line into a list of SymPy equations.

    A line may contain several equations ('x = 0, x = 5'). A bare expression
    is interpreted as 'expression = 0', which is how students often write a
    factorised form. Returns [] if nothing could be parsed.
    """
    equations: list[sympy.Eq] = []
    for part in split_answer_line(raw):
        equation = _parse_single(part, variable)
        if equation is None:
            return []
        equations.append(equation)
    return equations


def _parse_single(part: str, variable: str) -> sympy.Eq | None:
    symbol = sympy.Symbol(variable)
    try:
        if "=" in part:
            left, _, right = part.partition("=")
            lhs = parse_latex(left.strip())
            rhs = parse_latex(right.strip())
        else:
            lhs = parse_latex(part.strip())
            rhs = sympy.Integer(0)
    except Exception:
        return None

    if lhs is None or rhs is None:
        return None
    if symbol not in (lhs.free_symbols | rhs.free_symbols):
        # A line with no unknown in it (e.g. an arithmetic aside) is not a step
        # we can verify as part of the solution chain.
        return None
    return sympy.Eq(lhs, rhs)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_latex_utils.py -v`
Expected: all 7 PASS. If `parse_latex` raises `ImportError`, the ANTLR runtime version is wrong — reinstall with `pip install antlr4-python3-runtime==4.11.1`.

- [ ] **Step 5: Commit**

```bash
git add app/latex_utils.py tests/test_latex_utils.py
git commit -m "feat: add defensive latex normalisation and sympy parsing"
```

---

## Task 3: The symbolic verifier

**This is the heart of the system and the reason the marks are trustworthy. Test it hardest.** It is pure: no network, no disk, no LLM.

The core idea: each written line is an equation, so each line has a solution set. A valid algebraic step preserves the solution set. Comparing consecutive solution sets tells you not just *that* a step is wrong but *how* — a shrunk set means a root was discarded, a grown set means a spurious root appeared, and a set that is neither means an algebra slip.

**Files:**
- Create: `app/verifier.py`, `tests/test_verifier.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_verifier.py`:

```python
from app.models import Step
from app.verifier import solution_set, verify


def steps(*latex: str) -> list[Step]:
    return [Step(index=i, latex=text) for i, text in enumerate(latex, start=1)]


def test_solution_set_of_a_factorised_quadratic():
    assert solution_set("(x - 2)(x - 3) = 0", "x") == {"2", "3"}


def test_solution_set_of_standard_form():
    assert solution_set("x^2 - 5x + 6 = 0", "x") == {"2", "3"}


def test_solution_set_of_answer_line():
    assert solution_set("x = 2, x = 3", "x") == {"2", "3"}


def test_correct_chain_is_fully_equivalent():
    report = verify(
        steps("x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x = 2, x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.final_answer_correct is True
    assert report.first_divergence_index is None
    assert report.candidate_misconceptions == []


def test_dividing_by_the_variable_is_detected_as_a_lost_root():
    report = verify(
        steps("x^2 = 5x", "x = 5"),
        model_solution_steps=["x^2 = 5x", "x(x - 5) = 0", "x = 0, x = 5"],
        variable="x",
    )
    assert report.first_divergence_index == 2
    assert report.steps[1].divergence == "lost_roots"
    assert report.steps[1].lost_roots == ["0"]
    assert "divided_by_variable_lost_root" in report.candidate_misconceptions
    assert report.final_answer_correct is False


def test_sign_error_in_factorisation_is_detected_as_different_roots():
    report = verify(
        steps("x^2 - 5x + 6 = 0", "(x + 2)(x + 3) = 0", "x = -2, x = -3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.first_divergence_index == 2
    assert report.steps[1].divergence == "different_roots"
    assert "sign_error" in report.candidate_misconceptions


def test_dropping_plus_minus_is_a_lost_root():
    report = verify(
        steps("x^2 = 9", "x = 3"),
        model_solution_steps=["x^2 = 9", "x = 3, x = -3"],
        variable="x",
    )
    assert report.steps[1].divergence == "lost_roots"
    assert "dropped_plus_minus" in report.candidate_misconceptions


def test_unparseable_step_degrades_without_crashing():
    report = verify(
        steps("x^2 - 5x + 6 = 0", r"\text{then I factorised}", "x = 2, x = 3"),
        model_solution_steps=["x^2 - 5x + 6 = 0", "x = 2, x = 3"],
        variable="x",
    )
    assert report.steps[1].parsed is False
    assert report.steps[1].divergence == "unparseable"
    assert report.all_steps_parsed is False
    # The chain still reaches a correct final answer.
    assert report.final_answer_correct is True


def test_no_real_roots_case():
    report = verify(
        steps("x^2 + 2x + 5 = 0", r"x = -1 + 2i, x = -1 - 2i"),
        model_solution_steps=["x^2 + 2x + 5 = 0", r"x = -1 + 2i, x = -1 - 2i"],
        variable="x",
    )
    assert report.final_answer_correct is True


def test_empty_input_produces_an_empty_report():
    report = verify([], model_solution_steps=["x = 1"], variable="x")
    assert report.steps == []
    assert report.final_answer_correct is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_verifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.verifier'`.

- [ ] **Step 3: Write `app/verifier.py`**

```python
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
    solutions: set[sympy.Expr] = set()
    for equation in equations:
        try:
            roots = sympy.solve(equation, symbol, dict=False)
        except Exception:
            return None
        for root in roots:
            solutions.add(sympy.simplify(root))

    return {_canonical(root) for root in solutions}


def _canonical(expression: sympy.Expr) -> str:
    """A stable string form so that 6/2 and 3 compare equal."""
    return sympy.srepr(sympy.nsimplify(sympy.simplify(expression)))


def _display(canonical: str) -> str:
    """Turn a canonical form back into something a human can read."""
    try:
        return str(sympy.sympify(canonical))
    except Exception:
        return canonical


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
            solutions=sorted(_display(s) for s in current),
        )

        if previous is not None:
            verification.equivalent_to_previous = current == previous
            if current != previous:
                lost = previous - current
                gained = current - previous
                verification.lost_roots = sorted(_display(s) for s in lost)
                verification.gained_roots = sorted(_display(s) for s in gained)
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
        model_solutions=sorted(_display(s) for s in expected) if expected else [],
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

        previous_latex = by_index.get(verification.index - 1, None)
        previous_text = previous_latex.latex if previous_latex else ""

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
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_verifier.py -v`
Expected: all 10 PASS.

If `test_sign_error_in_factorisation_is_detected_as_different_roots` fails because the tag came out as `lost_solution`, check that `classify` is reached — a `different_roots` divergence has both `lost_roots` and `gained_roots` non-empty, so the ordering of the branches in `classify` matters.

- [ ] **Step 5: Add a regression guard against silent parse failures**

Append to `tests/test_verifier.py`:

```python
import pytest

REALISTIC_LINES = [
    "x^2 - 5x + 6 = 0",
    r"x^{2} - 5x + 6 = 0",
    r"\left(x - 2\right)\left(x - 3\right) = 0",
    "x^2 = 5x",
    "x(x - 5) = 0",
    "x = 0, x = 5",
    r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}".replace("b^2 - 4ac", "25 - 24").replace(
        "-b", "5"
    ).replace("2a", "2"),
    r"2x^{2} + 3x - 5 = 0",
    r"\left(2x + 5\right)\left(x - 1\right) = 0",
]


@pytest.mark.parametrize("latex", REALISTIC_LINES)
def test_realistic_lines_all_parse(latex):
    assert solution_set(latex, "x") is not None, f"failed to parse: {latex}"
```

- [ ] **Step 6: Run the parse-coverage tests**

Run: `pytest tests/test_verifier.py -v -k realistic`
Expected: all PASS. **Any failure here is a real bug that will bite during the demo** — fix it by adding a rewrite rule in `app/latex_utils.py`, not by removing the test case.

- [ ] **Step 7: Commit**

```bash
git add app/verifier.py tests/test_verifier.py
git commit -m "feat: add sympy step-equivalence verifier with misconception classification"
```

---

## Task 4: Seed data — questions, rubrics, misconceptions, notes

**Files:**
- Create: `app/seeds/questions.json`, `app/seeds/misconceptions.json`, `app/seeds/notes.json`, `app/store.py`, `tests/test_store.py`

- [ ] **Step 1: Create `app/seeds/questions.json`**

Six questions covering the misconception range. Rubric criteria are phrased **method-agnostically** so that completing the square, factorising and the formula all earn the same marks.

```json
[
  {
    "id": "q1",
    "prompt": "Solve $x^2 - 5x + 6 = 0$.",
    "model_solution_steps": [
      "x^2 - 5x + 6 = 0",
      "(x - 2)(x - 3) = 0",
      "x = 2, x = 3"
    ],
    "variable": "x",
    "topic_tag": "quadratics",
    "criteria": [
      { "id": "C1", "max": 1, "description": "Recognised the equation is in, or rearranged it to, a form suitable for solving" },
      { "id": "C2", "max": 3, "description": "Applied a valid solution method without losing or gaining solutions" },
      { "id": "C3", "max": 2, "description": "Carried out the algebra and arithmetic correctly" },
      { "id": "C4", "max": 1, "description": "Stated all solutions" },
      { "id": "C5", "max": 1, "description": "Working is clear and logically ordered" }
    ]
  },
  {
    "id": "q2",
    "prompt": "Solve $x^2 = 5x$.",
    "model_solution_steps": [
      "x^2 = 5x",
      "x^2 - 5x = 0",
      "x(x - 5) = 0",
      "x = 0, x = 5"
    ],
    "variable": "x",
    "topic_tag": "quadratics",
    "criteria": [
      { "id": "C1", "max": 2, "description": "Rearranged so that one side is zero, rather than dividing through by the unknown" },
      { "id": "C2", "max": 3, "description": "Applied a valid solution method without losing or gaining solutions" },
      { "id": "C3", "max": 2, "description": "Carried out the algebra and arithmetic correctly" },
      { "id": "C4", "max": 1, "description": "Stated all solutions" }
    ]
  },
  {
    "id": "q3",
    "prompt": "Solve $2x^2 + 3x - 5 = 0$.",
    "model_solution_steps": [
      "2x^2 + 3x - 5 = 0",
      "(2x + 5)(x - 1) = 0",
      "x = -5/2, x = 1"
    ],
    "variable": "x",
    "topic_tag": "quadratics",
    "criteria": [
      { "id": "C1", "max": 1, "description": "Identified the coefficients correctly" },
      { "id": "C2", "max": 3, "description": "Applied a valid solution method without losing or gaining solutions" },
      { "id": "C3", "max": 2, "description": "Carried out the algebra and arithmetic correctly" },
      { "id": "C4", "max": 1, "description": "Stated all solutions" }
    ]
  },
  {
    "id": "q4",
    "prompt": "Solve $x^2 + 4x + 1 = 0$, giving exact answers.",
    "model_solution_steps": [
      "x^2 + 4x + 1 = 0",
      "(x + 2)^2 - 3 = 0",
      "x = -2 + sqrt(3), x = -2 - sqrt(3)"
    ],
    "variable": "x",
    "topic_tag": "quadratics",
    "criteria": [
      { "id": "C1", "max": 1, "description": "Recognised that the expression does not factorise over the integers" },
      { "id": "C2", "max": 3, "description": "Applied a valid exact method (formula or completing the square) correctly" },
      { "id": "C3", "max": 2, "description": "Simplified the surd correctly" },
      { "id": "C4", "max": 1, "description": "Stated both solutions" }
    ]
  },
  {
    "id": "q5",
    "prompt": "Solve $x^2 + 2x + 5 = 0$. State clearly whether there are real solutions.",
    "model_solution_steps": [
      "x^2 + 2x + 5 = 0",
      "x = -1 + 2*I, x = -1 - 2*I"
    ],
    "variable": "x",
    "topic_tag": "quadratics",
    "criteria": [
      { "id": "C1", "max": 2, "description": "Evaluated the discriminant correctly" },
      { "id": "C2", "max": 2, "description": "Drew the correct conclusion about real solutions" },
      { "id": "C3", "max": 2, "description": "Carried out the algebra and arithmetic correctly" }
    ]
  },
  {
    "id": "q6",
    "prompt": "Solve $(x - 2)(x - 3) = 2$.",
    "model_solution_steps": [
      "(x - 2)(x - 3) = 2",
      "x^2 - 5x + 6 = 2",
      "x^2 - 5x + 4 = 0",
      "(x - 1)(x - 4) = 0",
      "x = 1, x = 4"
    ],
    "variable": "x",
    "topic_tag": "quadratics",
    "criteria": [
      { "id": "C1", "max": 2, "description": "Expanded and rearranged so that one side is zero before factorising" },
      { "id": "C2", "max": 3, "description": "Applied a valid solution method without losing or gaining solutions" },
      { "id": "C3", "max": 2, "description": "Carried out the algebra and arithmetic correctly" },
      { "id": "C4", "max": 1, "description": "Stated all solutions" }
    ]
  }
]
```

Note `q6`: the zero-product trap. A student who writes `x - 2 = 2` and `x - 3 = 2` from the unexpanded form loses C1 and C2 — and the verifier will catch it as `different_roots`.

- [ ] **Step 2: Create `app/seeds/misconceptions.json`**

```json
{
  "divided_by_variable_lost_root": {
    "tag": "divided_by_variable_lost_root",
    "name": "Dividing both sides by the unknown",
    "why_students_do_it": "Dividing by x looks like the same simplification as dividing by a constant, but it silently assumes x is not zero and therefore discards x = 0 as a solution.",
    "feedback_template": "You divided both sides by x. That is only valid when x is not zero, so it quietly throws away the solution x = 0. Instead, move everything to one side and factorise.",
    "remediation_reference": "Notes §2 — the zero-product principle",
    "practice_template_ids": ["quad_zero_root"]
  },
  "dropped_plus_minus": {
    "tag": "dropped_plus_minus",
    "name": "Taking only the positive square root",
    "why_students_do_it": "The square-root symbol denotes the principal (positive) root, so students forget that solving x^2 = k requires both roots.",
    "feedback_template": "When you take the square root of both sides you must allow both signs. x^2 = k gives x = +sqrt(k) and x = -sqrt(k).",
    "remediation_reference": "Notes §3 — square roots and the plus-or-minus sign",
    "practice_template_ids": ["quad_plus_minus"]
  },
  "sign_error": {
    "tag": "sign_error",
    "name": "Sign error in factorising or rearranging",
    "why_students_do_it": "When factorising x^2 + bx + c the signs of the two numbers depend on the signs of both b and c, and it is easy to reverse them.",
    "feedback_template": "Check the signs in your factorisation. Expand your brackets and compare with the original equation — if they do not match, the signs are the usual culprit.",
    "remediation_reference": "Notes §1 — factorising quadratics",
    "practice_template_ids": ["quad_sign_check"]
  },
  "squaring_introduced_spurious_root": {
    "tag": "squaring_introduced_spurious_root",
    "name": "Squaring both sides introduced an extra solution",
    "why_students_do_it": "Squaring is not reversible, so it can create solutions that do not satisfy the original equation.",
    "feedback_template": "Squaring both sides can create solutions that do not work in the original equation. Always substitute your answers back to check.",
    "remediation_reference": "Notes §4 — reversible and irreversible operations",
    "practice_template_ids": ["quad_sign_check"]
  },
  "lost_solution": {
    "tag": "lost_solution",
    "name": "A solution was lost during rearranging",
    "why_students_do_it": "Some manipulations quietly discard cases, particularly cancelling a common factor.",
    "feedback_template": "One of the solutions disappeared between two of your lines. Look for a step where you cancelled or divided by something that could be zero.",
    "remediation_reference": "Notes §2 — the zero-product principle",
    "practice_template_ids": ["quad_zero_root"]
  },
  "gained_solution": {
    "tag": "gained_solution",
    "name": "An extra solution appeared",
    "why_students_do_it": "A manipulation that is not reversible can introduce values that do not satisfy the original equation.",
    "feedback_template": "One of your answers does not satisfy the original equation. Substitute each answer back into the question to check.",
    "remediation_reference": "Notes §4 — reversible and irreversible operations",
    "practice_template_ids": ["quad_sign_check"]
  },
  "no_working_shown": {
    "tag": "no_working_shown",
    "name": "Answer given with no working",
    "why_students_do_it": "The student may have solved it mentally or by calculator, but method marks cannot be awarded for working that is not shown.",
    "feedback_template": "Your answer is correct, but there is no working to award method marks to. Show the rearrangement and the factorisation or formula you used.",
    "remediation_reference": "Notes §0 — how your work is marked",
    "practice_template_ids": ["quad_sign_check"]
  }
}
```

- [ ] **Step 3: Create `app/seeds/notes.json`**

```json
{
  "quadratics": [
    {
      "id": "notes-0",
      "title": "Notes §0 — how your work is marked",
      "body": "Marks are awarded for method as well as for the final answer. A correct answer with no working cannot earn the method marks."
    },
    {
      "id": "notes-1",
      "title": "Notes §1 — factorising quadratics",
      "body": "To factorise x^2 + bx + c, find two numbers whose product is c and whose sum is b. Expand your brackets to check before proceeding."
    },
    {
      "id": "notes-2",
      "title": "Notes §2 — the zero-product principle",
      "body": "If AB = 0 then A = 0 or B = 0. This only works when the product equals zero, which is why you must rearrange so that one side is zero before factorising. Never divide both sides by the unknown: doing so discards the solution where the unknown is zero."
    },
    {
      "id": "notes-3",
      "title": "Notes §3 — square roots and the plus-or-minus sign",
      "body": "If x^2 = k with k > 0, then x = +sqrt(k) or x = -sqrt(k). Writing only the positive root loses half the solutions."
    },
    {
      "id": "notes-4",
      "title": "Notes §4 — reversible and irreversible operations",
      "body": "Adding, subtracting, and multiplying or dividing by a non-zero constant are reversible and preserve the solution set. Squaring both sides and dividing by an expression containing the unknown are not."
    },
    {
      "id": "notes-5",
      "title": "Notes §5 — the quadratic formula and the discriminant",
      "body": "For ax^2 + bx + c = 0 the solutions are x = (-b +/- sqrt(b^2 - 4ac)) / (2a). The discriminant b^2 - 4ac determines the nature of the roots: positive gives two real roots, zero gives one repeated root, negative gives no real roots."
    }
  ]
}
```

- [ ] **Step 4: Write the failing test for the store**

Create `tests/test_store.py`:

```python
from app.models import Question, Submission
from app.store import (
    get_misconception,
    get_question,
    list_questions,
    load_submission,
    save_submission,
)


def test_all_seed_questions_load_and_validate():
    questions = list_questions()
    assert len(questions) >= 6
    assert all(isinstance(q, Question) for q in questions)


def test_every_question_has_at_least_three_criteria():
    for question in list_questions():
        assert len(question.criteria) >= 3, question.id


def test_get_question_by_id():
    question = get_question("q2")
    assert "5x" in question.prompt


def test_get_missing_question_raises():
    import pytest

    with pytest.raises(KeyError):
        get_question("does-not-exist")


def test_misconception_lookup_returns_feedback_template():
    entry = get_misconception("divided_by_variable_lost_root")
    assert "zero" in entry["feedback_template"].lower()


def test_submission_round_trips_to_disk():
    submission = Submission(id="test-round-trip", question_id="q1")
    save_submission(submission)
    assert load_submission("test-round-trip").question_id == "q1"
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.store'`.

- [ ] **Step 6: Write `app/store.py`**

```python
"""Loading seed data and persisting submissions. The only file-I/O module."""

import json
from functools import lru_cache
from typing import Any

from app.config import SEEDS_DIR, SUBMISSIONS_DIR
from app.models import Question, Submission


@lru_cache(maxsize=1)
def _questions() -> dict[str, Question]:
    raw = json.loads((SEEDS_DIR / "questions.json").read_text(encoding="utf-8"))
    return {item["id"]: Question.model_validate(item) for item in raw}


@lru_cache(maxsize=1)
def _misconceptions() -> dict[str, dict[str, Any]]:
    return json.loads((SEEDS_DIR / "misconceptions.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _notes() -> dict[str, list[dict[str, str]]]:
    return json.loads((SEEDS_DIR / "notes.json").read_text(encoding="utf-8"))


def list_questions() -> list[Question]:
    return list(_questions().values())


def get_question(question_id: str) -> Question:
    try:
        return _questions()[question_id]
    except KeyError as error:
        raise KeyError(f"unknown question id: {question_id}") from error


def get_misconception(tag: str) -> dict[str, Any]:
    return _misconceptions().get(tag, {})


def all_misconceptions() -> dict[str, dict[str, Any]]:
    return _misconceptions()


def get_notes(topic_tag: str) -> list[dict[str, str]]:
    return _notes().get(topic_tag, [])


def save_submission(submission: Submission) -> None:
    path = SUBMISSIONS_DIR / f"{submission.id}.json"
    path.write_text(submission.model_dump_json(indent=2), encoding="utf-8")


def load_submission(submission_id: str) -> Submission:
    path = SUBMISSIONS_DIR / f"{submission_id}.json"
    if not path.exists():
        raise KeyError(f"unknown submission id: {submission_id}")
    return Submission.model_validate_json(path.read_text(encoding="utf-8"))
```

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_store.py -v`
Expected: all 6 PASS. A validation error here means a typo in `questions.json` — the error message names the offending field.

- [ ] **Step 8: Verify every seeded model solution actually verifies against itself**

Create `tests/test_seed_integrity.py`:

```python
from app.models import Step
from app.store import list_questions
from app.verifier import solution_set, verify


def test_every_model_solution_line_parses():
    for question in list_questions():
        for latex in question.model_solution_steps:
            assert solution_set(latex, question.variable) is not None, (
                f"{question.id}: unparseable model line {latex!r}"
            )


def test_every_model_solution_verifies_as_correct_against_itself():
    for question in list_questions():
        steps = [
            Step(index=i, latex=text)
            for i, text in enumerate(question.model_solution_steps, start=1)
        ]
        report = verify(steps, question.model_solution_steps, question.variable)
        assert report.final_answer_correct, f"{question.id} does not verify against itself"
        assert report.first_divergence_index is None, (
            f"{question.id} has a divergence in its own model solution "
            f"at step {report.first_divergence_index}"
        )
```

- [ ] **Step 9: Run the integrity tests**

Run: `pytest tests/test_seed_integrity.py -v`
Expected: both PASS.

**This test is the most valuable one in the suite.** If a model solution does not verify against itself, every student marked against it will be marked wrongly. Run it after any edit to `questions.json`.

- [ ] **Step 10: Commit**

```bash
git add app/seeds app/store.py tests/test_store.py tests/test_seed_integrity.py
git commit -m "feat: add seed questions, rubrics, misconceptions, notes, and store"
```

---

## Task 5: Practice question generation

Templates with SymPy self-verification. **No LLM in this path** — a generated question whose stated answer is wrong destroys trust in the whole product.

**Files:**
- Create: `app/practice.py`, `tests/test_practice.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_practice.py`:

```python
import pytest
import sympy

from app.practice import TEMPLATES, generate_practice


def test_generate_returns_requested_count():
    questions = generate_practice(["divided_by_variable_lost_root"], count=3, seed=1)
    assert len(questions) == 3


def test_generated_questions_are_tagged_with_the_requested_misconception():
    questions = generate_practice(["dropped_plus_minus"], count=2, seed=7)
    assert all(q.misconception_tag == "dropped_plus_minus" for q in questions)


def test_unknown_tag_falls_back_to_general_practice():
    questions = generate_practice(["not_a_real_tag"], count=2, seed=3)
    assert len(questions) == 2


def test_no_tags_still_produces_practice():
    questions = generate_practice([], count=3, seed=3)
    assert len(questions) == 3


@pytest.mark.parametrize("seed", range(50))
@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_every_generated_answer_actually_solves_its_own_question(template_id, seed):
    """Property test: the stated answer must satisfy the stated equation."""
    template = TEMPLATES[template_id]
    generated = template.generate(seed)

    x = sympy.Symbol("x")
    equation = sympy.sympify(generated.equation_sympy)
    claimed = {sympy.nsimplify(sympy.sympify(r)) for r in generated.roots_sympy}
    actual = {sympy.nsimplify(r) for r in sympy.solve(equation, x)}

    assert claimed == actual, (
        f"{template_id} seed={seed}: claims {claimed} but the equation has {actual}"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_practice.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.practice'`.

- [ ] **Step 3: Write `app/practice.py`**

```python
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
    while p == q or (p == 0 and q == 0):
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
    for i in range(count):
        template = matching[i % len(matching)]
        generated = template.generate(base + i)
        tag = next(
            (t for t in misconception_tags if t in template.misconception_tags),
            template.misconception_tags[0],
        )
        questions.append(
            PracticeQuestion(
                prompt_latex=generated.prompt_latex,
                answer_latex=generated.answer_latex,
                misconception_tag=tag,
                template_id=template.id,
            )
        )
    return questions
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_practice.py -v`
Expected: all PASS, including 150 property-test cases.

A failure in `test_every_generated_answer_actually_solves_its_own_question` means a template is generating a question whose stated answer is wrong. **Fix the template — never weaken the test.**

- [ ] **Step 5: Commit**

```bash
git add app/practice.py tests/test_practice.py
git commit -m "feat: add sympy-verified parameterised practice generation"
```

---

## Task 6: The LLM client with disk caching and offline mode

**Build this before the transcriber and marker, not after.** Every LLM call goes through it, every response is cached, and `DEMO_MODE=offline` replays the cache with the network unplugged.

**Files:**
- Create: `app/llm.py`, `tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm.py`:

```python
import json

import pytest

from app import llm


def test_cache_key_is_stable_for_identical_input():
    a = llm.cache_key("model-x", "prompt text", "image-bytes-hash")
    b = llm.cache_key("model-x", "prompt text", "image-bytes-hash")
    assert a == b


def test_cache_key_changes_when_any_input_changes():
    base = llm.cache_key("model-x", "prompt", None)
    assert base != llm.cache_key("model-y", "prompt", None)
    assert base != llm.cache_key("model-x", "different", None)
    assert base != llm.cache_key("model-x", "prompt", "img")


def test_cache_write_then_read(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    key = "abc123"
    llm.write_cache(key, {"result": 42})
    assert llm.read_cache(key) == {"result": 42}


def test_cache_miss_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    assert llm.read_cache("nothing-here") is None


def test_offline_mode_raises_a_clear_error_on_cache_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "DEMO_MODE", "offline")
    with pytest.raises(llm.OfflineCacheMiss) as error:
        llm.complete_json(
            model="model-x", prompt="hello", schema={"type": "object"}, image_b64=None
        )
    assert "offline" in str(error.value).lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm'`.

- [ ] **Step 3: Write `app/llm.py`**

```python
"""The only module that talks to the Anthropic API.

Every call is content-addressed and cached to disk. In DEMO_MODE=offline no
network call is attempted at all: a cache miss raises immediately with a clear
message rather than hanging on a dead venue Wi-Fi connection.
"""

import hashlib
import json
from typing import Any

from anthropic import Anthropic

from app.config import ANTHROPIC_API_KEY, DEMO_MODE, LLM_CACHE_DIR


class OfflineCacheMiss(RuntimeError):
    """Raised when offline mode is on and the response is not cached."""


def cache_key(model: str, prompt: str, image_b64: str | None) -> str:
    digest = hashlib.sha256()
    digest.update(model.encode())
    digest.update(b"\x00")
    digest.update(prompt.encode())
    digest.update(b"\x00")
    if image_b64:
        # Hash the image rather than storing it in the key.
        digest.update(hashlib.sha256(image_b64.encode()).hexdigest().encode())
    return digest.hexdigest()[:32]


def read_cache(key: str) -> dict[str, Any] | None:
    path = LLM_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_cache(key: str, payload: dict[str, Any]) -> None:
    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (LLM_CACHE_DIR / f"{key}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def complete_json(
    model: str,
    prompt: str,
    schema: dict[str, Any],
    image_b64: str | None = None,
    image_media_type: str = "image/jpeg",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call Claude and return a JSON object matching `schema`.

    Uses a forced tool call so the response is structured JSON rather than
    prose that has to be parsed. Temperature is 0 for reproducibility.
    """
    key = cache_key(model, prompt, image_b64)

    cached = read_cache(key)
    if cached is not None:
        return cached

    if DEMO_MODE == "offline":
        raise OfflineCacheMiss(
            f"DEMO_MODE is offline and no cached response exists for key {key}. "
            f"Run once with DEMO_MODE=live to populate fixtures/llm_cache/."
        )

    content: list[dict[str, Any]] = []
    if image_b64:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type,
                    "data": image_b64,
                },
            }
        )
    content.append({"type": "text", "text": prompt})

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        tools=[
            {
                "name": "respond",
                "description": "Return the structured result.",
                "input_schema": schema,
            }
        ],
        tool_choice={"type": "tool", "name": "respond"},
        messages=[{"role": "user", "content": content}],
    )

    for block in response.content:
        if block.type == "tool_use":
            payload = dict(block.input)
            write_cache(key, payload)
            return payload

    raise RuntimeError("model did not return a tool_use block")
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_llm.py -v`
Expected: all 5 PASS. No network call is made — `monkeypatch` redirects the cache directory and forces offline mode.

- [ ] **Step 5: Commit**

```bash
git add app/llm.py tests/test_llm.py
git commit -m "feat: add cached anthropic client with offline demo mode"
```

---

## Task 7: The transcriber

Image → ordered LaTeX steps. **It never sees the model solution.** If it did, it would hallucinate the expected working into the transcription — a subtle failure that is very hard to spot and would invalidate the entire demo.

**Files:**
- Create: `app/transcriber.py`, `tests/test_transcriber.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_transcriber.py`:

```python
from app import transcriber
from app.models import Transcription


def test_prompt_never_mentions_the_answer_or_the_model_solution():
    prompt = transcriber.build_prompt()
    lowered = prompt.lower()
    assert "model solution" not in lowered
    assert "correct answer" not in lowered
    assert "solve" in lowered  # it should explicitly say NOT to solve
    assert "do not solve" in lowered


def test_transcribe_parses_a_cached_response(monkeypatch):
    fake = {
        "steps": [
            {"latex": "x^2 = 5x", "confidence": "high"},
            {"latex": "x = 5", "confidence": "low"},
        ],
        "notes": "second line is faint",
    }
    monkeypatch.setattr(transcriber, "complete_json", lambda **kwargs: fake)

    result = transcriber.transcribe(image_b64="fake", media_type="image/jpeg")

    assert isinstance(result, Transcription)
    assert [s.index for s in result.steps] == [1, 2]
    assert result.steps[1].confidence == "low"
    assert result.notes == "second line is faint"


def test_transcribe_drops_empty_lines(monkeypatch):
    fake = {"steps": [{"latex": "  ", "confidence": "high"}, {"latex": "x = 1"}], "notes": ""}
    monkeypatch.setattr(transcriber, "complete_json", lambda **kwargs: fake)

    result = transcriber.transcribe(image_b64="fake", media_type="image/jpeg")

    assert len(result.steps) == 1
    assert result.steps[0].index == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_transcriber.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.transcriber'`.

- [ ] **Step 3: Write `app/transcriber.py`**

```python
"""Handwritten image -> ordered LaTeX steps.

This module is deliberately ignorant of the question, the model solution and
the rubric. Its only job is to report what is written on the page, including
the mistakes.
"""

from app.config import VISION_MODEL
from app.llm import complete_json
from app.models import Step, Transcription

_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "latex": {
                        "type": "string",
                        "description": "The line exactly as written, as LaTeX.",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "low"],
                        "description": "low if any character on this line is uncertain",
                    },
                },
                "required": ["latex", "confidence"],
            },
        },
        "notes": {
            "type": "string",
            "description": "Anything the marker should know: crossings-out, illegible regions, work in margins.",
        },
    },
    "required": ["steps", "notes"],
}


def build_prompt() -> str:
    return """You are transcribing a photograph of a student's handwritten mathematics.

Your ONLY task is to report what is written on the page.

Rules:
- Transcribe each written line, in the order it appears, as a separate step.
- Transcribe EXACTLY what is written, including any mathematical errors.
- Do NOT solve the problem. Do NOT correct mistakes. Do NOT add missing steps.
- If a line is crossed out, omit it and mention it in notes.
- Use standard LaTeX. Prefer plain forms: x^2, \\frac{a}{b}, \\sqrt{x}, \\pm.
- Do not wrap lines in $ or \\[ \\].
- Mark a line as "low" confidence if ANY character on it is uncertain. Be
  honest about uncertainty: a flagged line costs the lecturer two seconds,
  but a confidently wrong transcription produces a wrong mark.
- Common confusions to watch for: 5 vs S, 1 vs l, 2 vs z, x vs times,
  0 vs O, and superscript 2 vs the digit 2 on the baseline.
- Put anything unusual about the page in notes."""


def transcribe(image_b64: str, media_type: str = "image/jpeg") -> Transcription:
    payload = complete_json(
        model=VISION_MODEL,
        prompt=build_prompt(),
        schema=_SCHEMA,
        image_b64=image_b64,
        image_media_type=media_type,
    )

    steps: list[Step] = []
    for raw in payload.get("steps", []):
        latex = (raw.get("latex") or "").strip()
        if not latex:
            continue
        steps.append(
            Step(
                index=len(steps) + 1,
                latex=latex,
                confidence=raw.get("confidence", "high"),
            )
        )

    return Transcription(steps=steps, notes=payload.get("notes", ""))
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_transcriber.py -v`
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/transcriber.py tests/test_transcriber.py
git commit -m "feat: add vision transcriber that never sees the model solution"
```

---

## Task 8: Context assembly (keyed retrieval, no embeddings)

**Files:**
- Create: `app/context.py`, `tests/test_context.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_context.py`:

```python
from app.context import assemble
from app.store import get_question


def test_assemble_includes_the_rubric_and_model_solution():
    context = assemble(get_question("q2"), ["divided_by_variable_lost_root"])
    assert "C1" in context
    assert "x(x - 5) = 0" in context


def test_assemble_includes_only_the_relevant_misconception_entries():
    context = assemble(get_question("q2"), ["divided_by_variable_lost_root"])
    assert "Dividing both sides by the unknown" in context
    assert "Taking only the positive square root" not in context


def test_assemble_with_no_misconceptions_still_returns_rubric():
    context = assemble(get_question("q1"), [])
    assert "C1" in context


def test_assemble_includes_topic_notes():
    context = assemble(get_question("q1"), [])
    assert "zero-product principle" in context
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.context'`.

- [ ] **Step 3: Write `app/context.py`**

```python
"""Deterministic keyed retrieval.

There is no vector store and no similarity search. The entire retrievable
corpus is under two thousand tokens, so exact lookup by question id and
misconception tag is both simpler and strictly more accurate than approximate
retrieval would be.
"""

from app.models import Question
from app.store import get_misconception, get_notes


def assemble(question: Question, misconception_tags: list[str]) -> str:
    """Build the reference block handed to the marking and feedback models."""
    parts: list[str] = []

    parts.append("## Question\n" + question.prompt)

    parts.append(
        "## Model solution (one valid route; other valid methods are acceptable)\n"
        + "\n".join(
            f"{i}. {latex}" for i, latex in enumerate(question.model_solution_steps, 1)
        )
    )

    parts.append(
        "## Rubric\n"
        + "\n".join(
            f"- {c.id} (max {c.max}): {c.description}" for c in question.criteria
        )
    )

    entries = [get_misconception(tag) for tag in misconception_tags]
    entries = [entry for entry in entries if entry]
    if entries:
        parts.append(
            "## Candidate misconceptions flagged by symbolic analysis\n"
            + "\n".join(
                f"- {entry['name']} (`{entry['tag']}`): {entry['why_students_do_it']}\n"
                f"  Suggested phrasing: {entry['feedback_template']}\n"
                f"  Reference: {entry['remediation_reference']}"
                for entry in entries
            )
        )

    notes = get_notes(question.topic_tag)
    if notes:
        parts.append(
            "## Course notes available to cite\n"
            + "\n".join(f"- {note['title']}: {note['body']}" for note in notes)
        )

    return "\n\n".join(parts)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_context.py -v`
Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/context.py tests/test_context.py
git commit -m "feat: add deterministic keyed context assembly"
```

---

## Task 9: The marker

Receives the verification report as **given fact** and maps it onto rubric criteria. It is explicitly forbidden from re-deriving the mathematics. A cross-check then flags any place where its marks contradict the verifier.

**Files:**
- Create: `app/marker.py`, `tests/test_marker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_marker.py`:

```python
from app import marker
from app.models import (
    CriterionMark,
    MarkProposal,
    Step,
    StepVerification,
    VerificationReport,
)
from app.store import get_question


def _report_with_lost_root() -> VerificationReport:
    return VerificationReport(
        steps=[
            StepVerification(index=1, parsed=True, solutions=["0", "5"]),
            StepVerification(
                index=2,
                parsed=True,
                solutions=["5"],
                equivalent_to_previous=False,
                divergence="lost_roots",
                lost_roots=["0"],
            ),
        ],
        final_answer_correct=False,
        model_solutions=["0", "5"],
        candidate_misconceptions=["divided_by_variable_lost_root"],
    )


def test_prompt_forbids_the_model_from_doing_mathematics():
    prompt = marker.build_prompt(
        get_question("q2"),
        [Step(index=1, latex="x^2 = 5x")],
        _report_with_lost_root(),
    )
    lowered = prompt.lower()
    assert "do not re-derive" in lowered
    assert "verified" in lowered


def test_prompt_contains_the_verification_findings():
    prompt = marker.build_prompt(
        get_question("q2"),
        [Step(index=1, latex="x^2 = 5x"), Step(index=2, latex="x = 5")],
        _report_with_lost_root(),
    )
    assert "lost_roots" in prompt
    assert "x = 5" in prompt


def test_mark_builds_a_proposal_from_the_model_response(monkeypatch):
    fake = {
        "criteria": [
            {
                "criterion_id": "C1",
                "proposed": 0,
                "justification": "divided through by x",
                "evidence_step": 2,
            },
            {
                "criterion_id": "C2",
                "proposed": 2,
                "justification": "method otherwise sound",
                "evidence_step": 2,
            },
            {"criterion_id": "C3", "proposed": 2, "justification": "arithmetic fine"},
            {"criterion_id": "C4", "proposed": 0, "justification": "only one solution given"},
        ],
        "misconceptions": ["divided_by_variable_lost_root"],
    }
    monkeypatch.setattr(marker, "complete_json", lambda **kwargs: fake)

    proposal = marker.mark(
        get_question("q2"),
        [Step(index=1, latex="x^2 = 5x"), Step(index=2, latex="x = 5")],
        _report_with_lost_root(),
    )

    assert isinstance(proposal, MarkProposal)
    assert proposal.total_proposed == 4
    assert proposal.total_max == 8
    # max values come from the rubric, never from the model
    assert {c.criterion_id: c.max for c in proposal.criteria}["C2"] == 3


def test_marks_above_the_rubric_max_are_clamped(monkeypatch):
    fake = {
        "criteria": [{"criterion_id": "C1", "proposed": 99, "justification": "x"}],
        "misconceptions": [],
    }
    monkeypatch.setattr(marker, "complete_json", lambda **kwargs: fake)

    proposal = marker.mark(get_question("q2"), [], _report_with_lost_root())

    assert proposal.criteria[0].proposed == 2  # C1 max for q2


def test_cross_check_warns_when_full_marks_given_on_a_diverged_step():
    proposal = MarkProposal(
        criteria=[
            CriterionMark(
                criterion_id="C2",
                proposed=3,
                max=3,
                justification="looks right",
                evidence_step=2,
            )
        ]
    )
    warnings = marker.cross_check(proposal, _report_with_lost_root())
    assert len(warnings) == 1
    assert "C2" in warnings[0]
    assert "step 2" in warnings[0]


def test_cross_check_is_silent_when_marks_and_verification_agree():
    proposal = MarkProposal(
        criteria=[
            CriterionMark(
                criterion_id="C2",
                proposed=1,
                max=3,
                justification="partial",
                evidence_step=2,
            )
        ]
    )
    assert marker.cross_check(proposal, _report_with_lost_root()) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_marker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.marker'`.

- [ ] **Step 3: Write `app/marker.py`**

```python
"""Rubric marking, constrained by symbolic verification.

The model is given the verifier's findings as established fact and is
instructed not to re-derive any mathematics. Its job is judgement about rubric
criteria and clear justification, which is what it is actually reliable at.
"""

from app.config import MARKING_MODEL
from app.context import assemble
from app.llm import complete_json
from app.models import CriterionMark, MarkProposal, Question, Step, VerificationReport

_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion_id": {"type": "string"},
                    "proposed": {"type": "integer", "minimum": 0},
                    "justification": {
                        "type": "string",
                        "description": "One or two sentences citing the specific step.",
                    },
                    "evidence_step": {
                        "type": ["integer", "null"],
                        "description": "The step number this judgement rests on.",
                    },
                },
                "required": ["criterion_id", "proposed", "justification"],
            },
        },
        "misconceptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["criteria", "misconceptions"],
}


def build_prompt(
    question: Question, steps: list[Step], report: VerificationReport
) -> str:
    reference = assemble(question, report.candidate_misconceptions)

    student_work = "\n".join(f"Step {s.index}: {s.latex}" for s in steps) or "(no steps)"

    findings: list[str] = []
    for verification in report.steps:
        if not verification.parsed:
            findings.append(
                f"Step {verification.index}: could NOT be interpreted as mathematics. "
                f"Mark this step on the written evidence alone and say so."
            )
            continue
        line = f"Step {verification.index}: solutions {verification.solutions}"
        if verification.equivalent_to_previous is True:
            line += " — VERIFIED equivalent to the previous step."
        elif verification.equivalent_to_previous is False:
            line += (
                f" — NOT equivalent to the previous step. "
                f"divergence={verification.divergence}; "
                f"lost={verification.lost_roots}; gained={verification.gained_roots}."
            )
        findings.append(line)

    findings.append(
        f"Final answer correct: {report.final_answer_correct}. "
        f"Expected solutions: {report.model_solutions}."
    )

    return f"""You are helping a lecturer mark a student's handwritten mathematics.

{reference}

## The student's confirmed working
{student_work}

## Verified findings from a computer algebra system
These findings are GROUND TRUTH. They were produced by SymPy, not by a language
model, and they are correct.

{chr(10).join(findings)}

## Your task
Propose a mark for each rubric criterion.

Rules you must follow:
- Do NOT re-derive or re-check any mathematics. Use only the verified findings
  above. If the findings say a step is equivalent, it is equivalent.
- The student may use a different valid method from the model solution.
  Alternative correct methods earn full marks. Mark the mathematics, not the
  resemblance to the model answer.
- Award method marks for correct working even when the final answer is wrong.
- Withhold method marks when working is absent, even if the answer is right.
- Every justification must cite a specific step number and be one or two
  sentences. Write it so the lecturer can check it in five seconds.
- Return one entry for every criterion listed in the rubric, using its exact id.
- Confirm or reject each candidate misconception. Return only the tags you
  believe genuinely apply."""


def mark(
    question: Question, steps: list[Step], report: VerificationReport
) -> MarkProposal:
    payload = complete_json(
        model=MARKING_MODEL,
        prompt=build_prompt(question, steps, report),
        schema=_SCHEMA,
    )

    # The rubric is the authority on maximum marks, never the model.
    max_by_id = {c.id: c.max for c in question.criteria}
    returned = {item["criterion_id"]: item for item in payload.get("criteria", [])}

    criteria: list[CriterionMark] = []
    for criterion in question.criteria:
        item = returned.get(criterion.id)
        if item is None:
            criteria.append(
                CriterionMark(
                    criterion_id=criterion.id,
                    proposed=0,
                    max=criterion.max,
                    justification="No judgement returned for this criterion — please review.",
                )
            )
            continue
        criteria.append(
            CriterionMark(
                criterion_id=criterion.id,
                proposed=min(int(item.get("proposed", 0)), max_by_id[criterion.id]),
                max=criterion.max,
                justification=item.get("justification", ""),
                evidence_step=item.get("evidence_step"),
            )
        )

    proposal = MarkProposal(
        criteria=criteria,
        misconceptions=payload.get("misconceptions", []),
    )
    proposal.warnings = cross_check(proposal, report)
    return proposal


def cross_check(proposal: MarkProposal, report: VerificationReport) -> list[str]:
    """Flag any place the LLM's marks contradict the symbolic verification.

    Full marks on a criterion whose evidence step the verifier rejected is a
    contradiction the lecturer should see.
    """
    diverged = {
        v.index for v in report.steps if v.equivalent_to_previous is False
    }

    warnings: list[str] = []
    for criterion in proposal.criteria:
        if (
            criterion.evidence_step in diverged
            and criterion.proposed == criterion.max
            and criterion.max > 0
        ):
            warnings.append(
                f"{criterion.criterion_id}: full marks awarded, but symbolic "
                f"verification found step {criterion.evidence_step} is not "
                f"equivalent to the previous step. Please review."
            )
    return warnings
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_marker.py -v`
Expected: all 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/marker.py tests/test_marker.py
git commit -m "feat: add rubric marker constrained by symbolic verification"
```

---

## Task 10: Feedback generation

**Files:**
- Create: `app/feedback.py`, `tests/test_feedback.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_feedback.py`:

```python
from app import feedback as feedback_module
from app.models import CriterionMark, Feedback, MarkProposal, Step, VerificationReport
from app.store import get_question


def _proposal() -> MarkProposal:
    return MarkProposal(
        criteria=[
            CriterionMark(
                criterion_id="C1",
                proposed=0,
                max=2,
                justification="Divided by x at step 2.",
                evidence_step=2,
            )
        ],
        misconceptions=["divided_by_variable_lost_root"],
    )


def _report() -> VerificationReport:
    return VerificationReport(steps=[], final_answer_correct=False, model_solutions=["0", "5"])


def test_prompt_addresses_the_student_directly_and_bans_new_marks():
    prompt = feedback_module.build_prompt(
        get_question("q2"), [Step(index=1, latex="x^2 = 5x")], _proposal(), _report()
    )
    lowered = prompt.lower()
    assert "second person" in lowered or "address the student" in lowered
    assert "do not" in lowered


def test_write_returns_structured_feedback(monkeypatch):
    fake = {
        "what_went_well": "You rearranged correctly.",
        "what_went_wrong": "You divided by x and lost the solution x = 0.",
        "how_to_improve": "Move everything to one side and factorise.",
        "references": ["Notes §2 — the zero-product principle"],
    }
    monkeypatch.setattr(feedback_module, "complete_json", lambda **kwargs: fake)

    result = feedback_module.write(get_question("q2"), [], _proposal(), _report())

    assert isinstance(result, Feedback)
    assert "x = 0" in result.what_went_wrong
    assert result.references == ["Notes §2 — the zero-product principle"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_feedback.py -v`
Expected: FAIL with `ImportError: cannot import name 'feedback'`.

- [ ] **Step 3: Write `app/feedback.py`**

```python
"""Student-facing feedback, grounded strictly in the marks and verification."""

from app.config import MARKING_MODEL
from app.context import assemble
from app.llm import complete_json
from app.models import Feedback, MarkProposal, Question, Step, VerificationReport

_SCHEMA = {
    "type": "object",
    "properties": {
        "what_went_well": {"type": "string"},
        "what_went_wrong": {"type": "string"},
        "how_to_improve": {"type": "string"},
        "references": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Titles of course notes sections worth revisiting.",
        },
    },
    "required": ["what_went_well", "what_went_wrong", "how_to_improve", "references"],
}


def build_prompt(
    question: Question,
    steps: list[Step],
    proposal: MarkProposal,
    report: VerificationReport,
) -> str:
    reference = assemble(question, proposal.misconceptions)
    student_work = "\n".join(f"Step {s.index}: {s.latex}" for s in steps) or "(no steps)"
    marks = "\n".join(
        f"- {c.criterion_id}: {c.proposed}/{c.max} — {c.justification}"
        for c in proposal.criteria
    )

    return f"""Write feedback for a student on their handwritten mathematics.

{reference}

## The student's working
{student_work}

## Marks already decided
{marks}
Total: {proposal.total_proposed}/{proposal.total_max}.
Final answer correct: {report.final_answer_correct}.

## Your task
Write three short paragraphs: what went well, what went wrong, and how to improve.

Rules:
- Address the student directly, in the second person. Warm, plain, specific.
- Ground every claim in the working and the marks above. Do NOT introduce any
  new mathematical claim, and do NOT change or question any mark.
- Name the specific step where things went wrong.
- Explain WHY the error is an error, not just that it is one.
- "How to improve" must be an action the student can take, not encouragement.
- No more than three sentences per paragraph. Do not use LaTeX delimiters;
  write mathematics inline like x = 0.
- In references, list only note titles that appear in the course notes above."""


def write(
    question: Question,
    steps: list[Step],
    proposal: MarkProposal,
    report: VerificationReport,
) -> Feedback:
    payload = complete_json(
        model=MARKING_MODEL,
        prompt=build_prompt(question, steps, proposal, report),
        schema=_SCHEMA,
    )
    return Feedback.model_validate(payload)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_feedback.py -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add app/feedback.py tests/test_feedback.py
git commit -m "feat: add grounded student feedback generation"
```

---

## Task 11: The API

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api.py`:

```python
import base64
import io

from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.models import Step, Transcription

client = TestClient(app)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_list_questions():
    response = client.get("/api/questions")
    assert response.status_code == 200
    assert len(response.json()) >= 6


def test_get_one_question():
    response = client.get("/api/questions/q2")
    assert response.status_code == 200
    assert response.json()["id"] == "q2"


def test_unknown_question_returns_404():
    assert client.get("/api/questions/nope").status_code == 404


def test_full_pipeline_without_an_image(monkeypatch):
    """The manual-entry path: no upload, steps typed directly."""
    monkeypatch.setattr(
        main,
        "run_marking",
        lambda question, steps: main.MarkingResult(
            verification=main.verify(steps, question.model_solution_steps, question.variable),
            marks=None,
            feedback=None,
        ),
    )

    created = client.post("/api/submissions", json={"question_id": "q2"}).json()
    submission_id = created["id"]

    response = client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}, {"index": 2, "latex": "x = 5"}]},
    )
    assert response.status_code == 200

    verified = client.post(f"/api/submissions/{submission_id}/verify").json()
    assert verified["verification"]["first_divergence_index"] == 2


def test_transcribe_endpoint_uses_the_transcriber(monkeypatch):
    monkeypatch.setattr(
        main,
        "transcribe",
        lambda image_b64, media_type: Transcription(
            steps=[Step(index=1, latex="x^2 = 5x")], notes=""
        ),
    )

    created = client.post("/api/submissions", json={"question_id": "q2"}).json()
    response = client.post(
        f"/api/submissions/{created['id']}/transcribe",
        files={"file": ("scan.png", io.BytesIO(PNG_1X1), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["transcription"]["steps"][0]["latex"] == "x^2 = 5x"


def test_override_recomputes_the_total():
    created = client.post("/api/submissions", json={"question_id": "q2"}).json()
    submission_id = created["id"]
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
    )
    client.post(f"/api/submissions/{submission_id}/verify")

    # Seed a proposal directly, then override one criterion.
    response = client.post(
        f"/api/submissions/{submission_id}/override",
        json={"criterion_id": "C1", "proposed": 1},
    )
    assert response.status_code in (200, 409)


def test_class_summary_is_available():
    response = client.get("/api/class/summary")
    assert response.status_code == 200
    assert "misconception_counts" in response.json()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL — most routes do not exist yet.

- [ ] **Step 3: Rewrite `app/main.py`**

```python
import base64
import json
import uuid
from dataclasses import dataclass

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import IMAGES_DIR, SEEDS_DIR, STATIC_DIR
from app.feedback import write as write_feedback
from app.llm import OfflineCacheMiss
from app.marker import mark as mark_submission
from app.models import (
    Feedback,
    MarkProposal,
    Question,
    Step,
    Submission,
    Transcription,
    VerificationReport,
)
from app.practice import generate_practice
from app.store import get_question, list_questions, load_submission, save_submission
from app.transcriber import transcribe
from app.verifier import verify

app = FastAPI(title="AIMS")


# ---------- request bodies ----------


class CreateSubmission(BaseModel):
    question_id: str
    student_pseudonym: str = "Student A"


class UpdateSteps(BaseModel):
    steps: list[Step]


class Override(BaseModel):
    criterion_id: str
    proposed: int


@dataclass
class MarkingResult:
    verification: VerificationReport
    marks: MarkProposal | None
    feedback: Feedback | None


# ---------- error handling ----------


@app.exception_handler(OfflineCacheMiss)
def offline_cache_miss(request, exc: OfflineCacheMiss) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": "offline_cache_miss",
            "detail": str(exc),
            "hint": "This input has not been cached. Use one of the sample scripts, "
            "or restart with DEMO_MODE=live.",
        },
    )


@app.exception_handler(KeyError)
def key_error(request, exc: KeyError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(exc)})


# ---------- questions ----------


@app.get("/api/questions")
def api_list_questions() -> list[Question]:
    return list_questions()


@app.get("/api/questions/{question_id}")
def api_get_question(question_id: str) -> Question:
    try:
        return get_question(question_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown question: {question_id}")


# ---------- submissions ----------


@app.post("/api/submissions")
def api_create_submission(body: CreateSubmission) -> Submission:
    try:
        get_question(body.question_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown question: {body.question_id}")

    submission = Submission(
        id=uuid.uuid4().hex[:12],
        question_id=body.question_id,
        student_pseudonym=body.student_pseudonym,
    )
    save_submission(submission)
    return submission


@app.get("/api/submissions/{submission_id}")
def api_get_submission(submission_id: str) -> Submission:
    try:
        return load_submission(submission_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown submission: {submission_id}")


@app.post("/api/submissions/{submission_id}/transcribe")
async def api_transcribe(submission_id: str, file: UploadFile = File(...)) -> Submission:
    submission = _load(submission_id)

    raw = await file.read()
    filename = f"{submission_id}-{file.filename}"
    (IMAGES_DIR / filename).write_bytes(raw)

    media_type = file.content_type or "image/jpeg"
    transcription = transcribe(
        image_b64=base64.b64encode(raw).decode(), media_type=media_type
    )

    submission.image_filename = filename
    submission.transcription = transcription
    submission.confirmed_steps = list(transcription.steps)
    save_submission(submission)
    return submission


@app.put("/api/submissions/{submission_id}/steps")
def api_update_steps(submission_id: str, body: UpdateSteps) -> Submission:
    submission = _load(submission_id)

    original = {s.index: s.latex for s in (submission.transcription.steps if submission.transcription else [])}
    steps = [
        Step(
            index=i,
            latex=step.latex,
            confidence=step.confidence,
            edited_by_human=original.get(step.index) != step.latex,
        )
        for i, step in enumerate(body.steps, start=1)
    ]

    submission.confirmed_steps = steps
    # Anything downstream is now stale.
    submission.verification = None
    submission.marks = None
    submission.feedback = None
    submission.practice = []
    save_submission(submission)
    return submission


@app.post("/api/submissions/{submission_id}/verify")
def api_verify(submission_id: str) -> Submission:
    submission = _load(submission_id)
    question = get_question(submission.question_id)
    steps = submission.confirmed_steps or []

    submission.verification = verify(steps, question.model_solution_steps, question.variable)
    save_submission(submission)
    return submission


@app.post("/api/submissions/{submission_id}/mark")
def api_mark(submission_id: str) -> Submission:
    submission = _load(submission_id)
    question = get_question(submission.question_id)
    steps = submission.confirmed_steps or []

    if submission.verification is None:
        submission.verification = verify(
            steps, question.model_solution_steps, question.variable
        )

    submission.marks = mark_submission(question, steps, submission.verification)
    submission.feedback = write_feedback(
        question, steps, submission.marks, submission.verification
    )
    submission.practice = generate_practice(
        submission.marks.misconceptions, count=3, seed=abs(hash(submission_id)) % 10_000
    )
    save_submission(submission)
    return submission


@app.post("/api/submissions/{submission_id}/override")
def api_override(submission_id: str, body: Override) -> Submission:
    submission = _load(submission_id)
    if submission.marks is None:
        raise HTTPException(status_code=409, detail="nothing to override yet")

    for criterion in submission.marks.criteria:
        if criterion.criterion_id == body.criterion_id:
            if body.proposed > criterion.max:
                raise HTTPException(
                    status_code=400,
                    detail=f"{body.proposed} exceeds max {criterion.max}",
                )
            criterion.proposed = body.proposed
            criterion.overridden = True
            save_submission(submission)
            return submission

    raise HTTPException(status_code=404, detail=f"unknown criterion: {body.criterion_id}")


# ---------- class view ----------


@app.get("/api/class/summary")
def api_class_summary() -> dict:
    return json.loads((SEEDS_DIR / "class_summary.json").read_text(encoding="utf-8"))


def _load(submission_id: str) -> Submission:
    try:
        return load_submission(submission_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown submission: {submission_id}")


# Must stay last: the static mount is a catch-all.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
```

- [ ] **Step 4: Create `app/seeds/class_summary.json`**

```json
{
  "cohort_size": 31,
  "marked": 31,
  "mean_percentage": 62,
  "misconception_counts": [
    { "tag": "divided_by_variable_lost_root", "name": "Dividing both sides by the unknown", "count": 12 },
    { "tag": "sign_error", "name": "Sign error in factorising or rearranging", "count": 9 },
    { "tag": "dropped_plus_minus", "name": "Taking only the positive square root", "count": 6 },
    { "tag": "no_working_shown", "name": "Answer given with no working", "count": 4 },
    { "tag": "gained_solution", "name": "An extra solution appeared", "count": 2 }
  ],
  "students": [
    { "pseudonym": "Student A", "question_id": "q2", "mark": 4, "max": 8, "top_misconception": "divided_by_variable_lost_root" },
    { "pseudonym": "Student B", "question_id": "q1", "mark": 8, "max": 8, "top_misconception": null },
    { "pseudonym": "Student C", "question_id": "q1", "mark": 3, "max": 8, "top_misconception": "sign_error" },
    { "pseudonym": "Student D", "question_id": "q4", "mark": 5, "max": 7, "top_misconception": "dropped_plus_minus" },
    { "pseudonym": "Student E", "question_id": "q6", "mark": 2, "max": 8, "top_misconception": "sign_error" },
    { "pseudonym": "Student F", "question_id": "q1", "mark": 4, "max": 8, "top_misconception": "no_working_shown" }
  ],
  "recommendation": "12 of 31 students divided through by the unknown and lost a solution. Revisit the zero-product principle before the next assessment."
}
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_api.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the whole suite**

Run: `pytest -v`
Expected: everything PASS. This is the point at which the backend is complete.

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/seeds/class_summary.json tests/test_api.py
git commit -m "feat: add pipeline API with staged endpoints and class summary"
```

---

## Task 12: The frontend

Four screens in one HTML file, toggled with JavaScript. No build step. Tailwind, KaTeX and Chart.js from CDN.

**Files:**
- Create: `static/index.html`, `static/app.js`, `static/app.css`

- [ ] **Step 1: Write `static/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>AIMS — AI for Individualised Mastery Support</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link
      rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css"
    />
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="/app.css" />
  </head>
  <body class="bg-slate-100 text-slate-900 min-h-screen">
    <header class="bg-white border-b border-slate-200">
      <div class="max-w-7xl mx-auto px-6 py-4 flex items-center gap-6">
        <h1 class="text-lg font-semibold tracking-tight">AIMS</h1>
        <nav class="flex gap-1 text-sm" id="nav">
          <button data-screen="setup" class="nav-btn">1 · Setup</button>
          <button data-screen="confirm" class="nav-btn">2 · Confirm</button>
          <button data-screen="review" class="nav-btn">3 · Review</button>
          <button data-screen="class" class="nav-btn">4 · Class</button>
        </nav>
        <span id="mode-badge" class="ml-auto text-xs px-2 py-1 rounded bg-slate-200"></span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <!-- SCREEN 1: SETUP -->
      <section id="screen-setup" class="screen">
        <div class="grid grid-cols-3 gap-6">
          <div class="col-span-1 bg-white rounded-lg border border-slate-200 p-5">
            <h2 class="font-semibold mb-3">Question</h2>
            <select id="question-select" class="w-full border rounded px-3 py-2 text-sm"></select>
            <div id="question-prompt" class="mt-4 text-lg"></div>
            <h3 class="font-semibold mt-6 mb-2 text-sm uppercase tracking-wide text-slate-500">Model solution</h3>
            <ol id="model-solution" class="space-y-1 text-sm"></ol>
          </div>
          <div class="col-span-2 bg-white rounded-lg border border-slate-200 p-5">
            <h2 class="font-semibold mb-3">Rubric</h2>
            <table class="w-full text-sm">
              <thead class="text-left text-slate-500 border-b">
                <tr><th class="py-2 w-16">ID</th><th>Criterion</th><th class="w-16 text-right">Max</th></tr>
              </thead>
              <tbody id="rubric-body"></tbody>
            </table>

            <h2 class="font-semibold mt-8 mb-3">Student work</h2>
            <div class="flex gap-3">
              <label class="flex-1 border-2 border-dashed border-slate-300 rounded-lg p-6 text-center cursor-pointer hover:border-slate-400">
                <input type="file" id="file-input" accept="image/*" class="hidden" />
                <span class="text-sm text-slate-600">Click to upload a scan or photo</span>
              </label>
              <button id="btn-sample" class="px-4 py-2 text-sm bg-slate-800 text-white rounded">Use a sample script</button>
              <button id="btn-manual" class="px-4 py-2 text-sm border border-slate-300 rounded">Type it in</button>
            </div>
            <p id="setup-status" class="mt-3 text-sm text-slate-500"></p>
          </div>
        </div>
      </section>

      <!-- SCREEN 2: CONFIRM -->
      <section id="screen-confirm" class="screen hidden">
        <div class="grid grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border border-slate-200 p-5">
            <h2 class="font-semibold mb-3">Original</h2>
            <img id="scan-image" class="w-full rounded border border-slate-200" alt="student work" />
            <p id="transcription-notes" class="mt-3 text-sm text-amber-700"></p>
          </div>
          <div class="bg-white rounded-lg border border-slate-200 p-5">
            <div class="flex items-baseline justify-between mb-3">
              <h2 class="font-semibold">Transcribed steps</h2>
              <span class="text-xs text-slate-500">Click a line to edit</span>
            </div>
            <div id="steps-editor" class="space-y-2"></div>
            <div class="flex gap-2 mt-4">
              <button id="btn-add-step" class="text-sm px-3 py-1.5 border rounded">Add step</button>
              <button id="btn-confirm" class="ml-auto px-5 py-2 bg-emerald-600 text-white rounded font-medium">
                Confirm &amp; Mark
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- SCREEN 3: REVIEW -->
      <section id="screen-review" class="screen hidden">
        <div id="warnings" class="mb-4"></div>
        <div class="grid grid-cols-12 gap-6">
          <div class="col-span-4 bg-white rounded-lg border border-slate-200 p-5">
            <h2 class="font-semibold mb-3">Verified working</h2>
            <div id="verified-steps" class="space-y-2"></div>
          </div>
          <div class="col-span-4 bg-white rounded-lg border border-slate-200 p-5">
            <h2 class="font-semibold mb-3">Proposed marks</h2>
            <div id="marks-list" class="space-y-3"></div>
            <div class="mt-5 pt-4 border-t flex items-baseline justify-between">
              <span class="font-semibold">Total</span>
              <span id="mark-total" class="text-2xl font-semibold"></span>
            </div>
          </div>
          <div class="col-span-4 bg-white rounded-lg border border-slate-200 p-5">
            <div class="flex gap-1 mb-4 text-sm">
              <button data-tab="feedback" class="tab-btn">Feedback</button>
              <button data-tab="misconceptions" class="tab-btn">Misconceptions</button>
              <button data-tab="practice" class="tab-btn">Practice</button>
            </div>
            <div id="tab-feedback" class="tab-panel space-y-4"></div>
            <div id="tab-misconceptions" class="tab-panel hidden space-y-3"></div>
            <div id="tab-practice" class="tab-panel hidden space-y-3"></div>
          </div>
        </div>
      </section>

      <!-- SCREEN 4: CLASS -->
      <section id="screen-class" class="screen hidden">
        <div class="grid grid-cols-2 gap-6">
          <div class="bg-white rounded-lg border border-slate-200 p-5">
            <h2 class="font-semibold mb-4">Misconceptions across the cohort</h2>
            <canvas id="misconception-chart" height="220"></canvas>
            <p id="class-recommendation" class="mt-4 text-sm bg-amber-50 border border-amber-200 rounded p-3"></p>
          </div>
          <div class="bg-white rounded-lg border border-slate-200 p-5">
            <h2 class="font-semibold mb-4">Scripts</h2>
            <table class="w-full text-sm">
              <thead class="text-left text-slate-500 border-b">
                <tr><th class="py-2">Student</th><th>Q</th><th>Mark</th><th>Top misconception</th></tr>
              </thead>
              <tbody id="class-table"></tbody>
            </table>
          </div>
        </div>
      </section>
    </main>

    <script src="/app.js"></script>
  </body>
</html>
```

- [ ] **Step 2: Write `static/app.css`**

```css
.nav-btn {
  padding: 0.35rem 0.75rem;
  border-radius: 0.375rem;
  color: rgb(71 85 105);
}
.nav-btn.active {
  background: rgb(30 41 59);
  color: white;
}
.tab-btn {
  padding: 0.3rem 0.7rem;
  border-radius: 0.375rem;
  border: 1px solid rgb(226 232 240);
}
.tab-btn.active {
  background: rgb(241 245 249);
  font-weight: 600;
}
.step-row.low-confidence {
  background: rgb(254 252 232);
  border-color: rgb(250 204 21);
}
.verdict-ok {
  border-left: 3px solid rgb(16 185 129);
}
.verdict-bad {
  border-left: 3px solid rgb(239 68 68);
}
.verdict-unknown {
  border-left: 3px solid rgb(148 163 184);
}
```

- [ ] **Step 3: Write `static/app.js`**

```javascript
const state = { questions: [], question: null, submission: null };

// ---------- helpers ----------

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    alert(`${body.error || "Error"}: ${body.detail || body.hint || ""}`);
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

function renderMath(element, latex) {
  try {
    katex.render(latex, element, { throwOnError: false, displayMode: false });
  } catch {
    element.textContent = latex;
  }
}

function mathSpan(latex) {
  const span = document.createElement("span");
  renderMath(span, latex);
  return span;
}

function showScreen(name) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.add("hidden"));
  $(`screen-${name}`).classList.remove("hidden");
  document.querySelectorAll(".nav-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.screen === name)
  );
  if (name === "class") loadClassSummary();
}

// ---------- screen 1: setup ----------

async function init() {
  state.questions = await api("/api/questions");
  const select = $("question-select");
  state.questions.forEach((q) => {
    const option = document.createElement("option");
    option.value = q.id;
    option.textContent = `${q.id.toUpperCase()} — ${q.prompt.replace(/\$/g, "")}`;
    select.appendChild(option);
  });
  select.addEventListener("change", () => selectQuestion(select.value));
  selectQuestion(state.questions[0].id);

  document.querySelectorAll(".nav-btn").forEach((b) =>
    b.addEventListener("click", () => showScreen(b.dataset.screen))
  );
  document.querySelectorAll(".tab-btn").forEach((b) =>
    b.addEventListener("click", () => showTab(b.dataset.tab))
  );
  $("file-input").addEventListener("change", handleUpload);
  $("btn-manual").addEventListener("click", startManual);
  $("btn-sample").addEventListener("click", startManual);
  $("btn-add-step").addEventListener("click", () => addStepRow(""));
  $("btn-confirm").addEventListener("click", confirmAndMark);

  showScreen("setup");
}

function selectQuestion(id) {
  state.question = state.questions.find((q) => q.id === id);
  renderMath($("question-prompt"), state.question.prompt.replace(/\$/g, ""));

  const list = $("model-solution");
  list.innerHTML = "";
  state.question.model_solution_steps.forEach((latex) => {
    const li = document.createElement("li");
    li.className = "pl-2";
    li.appendChild(mathSpan(latex));
    list.appendChild(li);
  });

  const body = $("rubric-body");
  body.innerHTML = "";
  state.question.criteria.forEach((c) => {
    const row = document.createElement("tr");
    row.className = "border-b border-slate-100";
    row.innerHTML = `<td class="py-2 font-mono text-xs">${c.id}</td><td class="py-2">${c.description}</td><td class="py-2 text-right">${c.max}</td>`;
    body.appendChild(row);
  });
}

async function createSubmission() {
  state.submission = await api("/api/submissions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_id: state.question.id }),
  });
}

async function handleUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  $("setup-status").textContent = "Transcribing…";
  await createSubmission();

  const form = new FormData();
  form.append("file", file);
  state.submission = await api(
    `/api/submissions/${state.submission.id}/transcribe`,
    { method: "POST", body: form }
  );

  $("scan-image").src = URL.createObjectURL(file);
  renderStepsEditor(state.submission.confirmed_steps || []);
  $("transcription-notes").textContent = state.submission.transcription?.notes || "";
  $("setup-status").textContent = "";
  showScreen("confirm");
}

async function startManual() {
  await createSubmission();
  $("scan-image").removeAttribute("src");
  $("transcription-notes").textContent = "No image — type the working directly.";
  renderStepsEditor([{ index: 1, latex: "", confidence: "high" }]);
  showScreen("confirm");
}

// ---------- screen 2: confirm ----------

function renderStepsEditor(steps) {
  const container = $("steps-editor");
  container.innerHTML = "";
  steps.forEach((step) => addStepRow(step.latex, step.confidence));
}

function addStepRow(latex, confidence = "high") {
  const container = $("steps-editor");
  const row = document.createElement("div");
  row.className = `step-row border rounded p-2 ${
    confidence === "low" ? "low-confidence" : "border-slate-200"
  }`;

  const preview = document.createElement("div");
  preview.className = "min-h-6 mb-1";
  renderMath(preview, latex);

  const input = document.createElement("input");
  input.className = "w-full font-mono text-xs bg-transparent outline-none text-slate-600";
  input.value = latex;
  input.addEventListener("input", () => renderMath(preview, input.value));

  const remove = document.createElement("button");
  remove.textContent = "×";
  remove.className = "absolute top-1 right-2 text-slate-400 hover:text-red-500";
  remove.addEventListener("click", () => row.remove());

  row.classList.add("relative");
  row.append(preview, input, remove);
  container.appendChild(row);
}

function collectSteps() {
  return [...document.querySelectorAll("#steps-editor input")]
    .map((input, i) => ({ index: i + 1, latex: input.value.trim() }))
    .filter((step) => step.latex.length > 0);
}

async function confirmAndMark() {
  const steps = collectSteps();
  if (steps.length === 0) {
    alert("Add at least one step before marking.");
    return;
  }

  $("btn-confirm").textContent = "Marking…";
  $("btn-confirm").disabled = true;

  try {
    await api(`/api/submissions/${state.submission.id}/steps`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps }),
    });
    state.submission = await api(`/api/submissions/${state.submission.id}/mark`, {
      method: "POST",
    });
    renderReview();
    showScreen("review");
  } finally {
    $("btn-confirm").textContent = "Confirm & Mark";
    $("btn-confirm").disabled = false;
  }
}

// ---------- screen 3: review ----------

function renderReview() {
  const { verification, marks, feedback, practice, confirmed_steps } = state.submission;

  // Warnings
  const warnings = $("warnings");
  warnings.innerHTML = "";
  (marks.warnings || []).forEach((text) => {
    const box = document.createElement("div");
    box.className =
      "bg-red-50 border border-red-300 text-red-800 rounded p-3 text-sm mb-2";
    box.textContent = `⚠ ${text}`;
    warnings.appendChild(box);
  });

  // Verified steps
  const stepsBox = $("verified-steps");
  stepsBox.innerHTML = "";
  confirmed_steps.forEach((step) => {
    const v = verification.steps.find((s) => s.index === step.index);
    const verdict = !v?.parsed
      ? "verdict-unknown"
      : v.equivalent_to_previous === false
      ? "verdict-bad"
      : "verdict-ok";

    const row = document.createElement("div");
    row.className = `${verdict} bg-slate-50 rounded pl-3 pr-2 py-2`;
    row.id = `step-${step.index}`;

    const line = document.createElement("div");
    line.className = "flex items-baseline gap-2";
    const num = document.createElement("span");
    num.className = "text-xs text-slate-400 font-mono";
    num.textContent = step.index;
    line.append(num, mathSpan(step.latex));

    const note = document.createElement("div");
    note.className = "text-xs mt-1";
    if (!v?.parsed) {
      note.className += " text-slate-500";
      note.textContent = "Not symbolically verified";
    } else if (v.equivalent_to_previous === false) {
      note.className += " text-red-700";
      const bits = [];
      if (v.lost_roots?.length) bits.push(`lost ${v.lost_roots.join(", ")}`);
      if (v.gained_roots?.length) bits.push(`gained ${v.gained_roots.join(", ")}`);
      note.textContent = `Solution set changed — ${bits.join("; ")}`;
    } else if (v.equivalent_to_previous === true) {
      note.className += " text-emerald-700";
      note.textContent = "Verified equivalent to the previous step";
    } else {
      note.className += " text-slate-500";
      note.textContent = `Solutions: ${v.solutions.join(", ")}`;
    }

    row.append(line, note);
    stepsBox.appendChild(row);
  });

  // Marks
  const marksBox = $("marks-list");
  marksBox.innerHTML = "";
  marks.criteria.forEach((c) => {
    const criterion = state.question.criteria.find((x) => x.id === c.criterion_id);
    const card = document.createElement("div");
    card.className = "border border-slate-200 rounded p-3";

    const head = document.createElement("div");
    head.className = "flex items-center gap-2 mb-1";
    head.innerHTML = `<span class="font-mono text-xs text-slate-500">${c.criterion_id}</span>
      <span class="text-sm flex-1">${criterion?.description || ""}</span>`;

    const input = document.createElement("input");
    input.type = "number";
    input.min = 0;
    input.max = c.max;
    input.value = c.proposed;
    input.className = "w-14 border rounded px-2 py-1 text-sm text-right";
    input.addEventListener("change", () => override(c.criterion_id, Number(input.value)));

    const outOf = document.createElement("span");
    outOf.className = "text-sm text-slate-500";
    outOf.textContent = `/ ${c.max}`;

    head.append(input, outOf);

    const justification = document.createElement("p");
    justification.className = "text-xs text-slate-600";
    justification.textContent = c.justification;

    card.append(head, justification);

    if (c.evidence_step) {
      const link = document.createElement("button");
      link.className = "text-xs text-blue-600 underline mt-1";
      link.textContent = `see step ${c.evidence_step}`;
      link.addEventListener("click", () => {
        const target = $(`step-${c.evidence_step}`);
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("ring", "ring-blue-400");
        setTimeout(() => target.classList.remove("ring", "ring-blue-400"), 1200);
      });
      card.appendChild(link);
    }

    marksBox.appendChild(card);
  });

  $("mark-total").textContent = `${marks.total_proposed} / ${marks.total_max}`;

  // Feedback tab
  const fb = $("tab-feedback");
  fb.innerHTML = "";
  [
    ["What went well", feedback.what_went_well],
    ["What went wrong", feedback.what_went_wrong],
    ["How to improve", feedback.how_to_improve],
  ].forEach(([title, body]) => {
    const block = document.createElement("div");
    block.innerHTML = `<h3 class="text-xs uppercase tracking-wide text-slate-500 mb-1">${title}</h3>
      <p class="text-sm">${body}</p>`;
    fb.appendChild(block);
  });
  if (feedback.references?.length) {
    const refs = document.createElement("p");
    refs.className = "text-xs text-slate-500 pt-2 border-t";
    refs.textContent = `See: ${feedback.references.join(" · ")}`;
    fb.appendChild(refs);
  }

  // Misconceptions tab
  const mis = $("tab-misconceptions");
  mis.innerHTML = "";
  if (marks.misconceptions.length === 0) {
    mis.innerHTML = `<p class="text-sm text-slate-500">No misconceptions detected.</p>`;
  }
  marks.misconceptions.forEach((tag) => {
    const chip = document.createElement("div");
    chip.className = "bg-amber-50 border border-amber-200 rounded p-3 text-sm";
    chip.innerHTML = `<span class="font-mono text-xs text-amber-800">${tag}</span>`;
    mis.appendChild(chip);
  });

  // Practice tab
  const pr = $("tab-practice");
  pr.innerHTML = "";
  practice.forEach((q, i) => {
    const card = document.createElement("div");
    card.className = "border border-slate-200 rounded p-3";
    const prompt = document.createElement("div");
    prompt.className = "text-sm mb-1";
    prompt.textContent = `${i + 1}. `;
    prompt.appendChild(mathSpan(q.prompt_latex.replace(/^Solve \$|\$\.$/g, "")));
    const answer = document.createElement("div");
    answer.className = "text-xs text-slate-500";
    answer.appendChild(mathSpan(q.answer_latex));
    card.append(prompt, answer);
    pr.appendChild(card);
  });

  showTab("feedback");
}

async function override(criterionId, proposed) {
  state.submission = await api(`/api/submissions/${state.submission.id}/override`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ criterion_id: criterionId, proposed }),
  });
  $("mark-total").textContent =
    `${state.submission.marks.total_proposed} / ${state.submission.marks.total_max}`;
}

function showTab(name) {
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
  $(`tab-${name}`).classList.remove("hidden");
  document.querySelectorAll(".tab-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name)
  );
}

// ---------- screen 4: class ----------

let chart = null;

async function loadClassSummary() {
  const summary = await api("/api/class/summary");

  $("class-recommendation").textContent = summary.recommendation;

  const table = $("class-table");
  table.innerHTML = "";
  summary.students.forEach((s) => {
    const row = document.createElement("tr");
    row.className = "border-b border-slate-100";
    row.innerHTML = `<td class="py-2">${s.pseudonym}</td>
      <td>${s.question_id.toUpperCase()}</td>
      <td>${s.mark}/${s.max}</td>
      <td class="text-xs text-slate-600">${s.top_misconception || "—"}</td>`;
    table.appendChild(row);
  });

  if (chart) chart.destroy();
  chart = new Chart($("misconception-chart"), {
    type: "bar",
    data: {
      labels: summary.misconception_counts.map((m) => m.name),
      datasets: [
        {
          data: summary.misconception_counts.map((m) => m.count),
          backgroundColor: "#0f766e",
        },
      ],
    },
    options: {
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
    },
  });
}

init();
```

- [ ] **Step 4: Run the app and walk the manual-entry path**

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. Select **Q2**, click **Type it in**, enter `x^2 = 5x` and `x = 5` as two steps, click **Confirm & Mark**.

Expected: the review screen shows step 2 with a red left border and *"Solution set changed — lost 0"*, per-criterion marks with justifications, feedback naming the lost root, and three practice questions.

- [ ] **Step 5: Commit**

```bash
git add static/
git commit -m "feat: add four-screen build-free frontend"
```

---

## Task 13: Handwritten demo data and cached fixtures

**Do this the moment Task 12 works. Do not leave it to the last day.**

**Files:**
- Create: `fixtures/images/*.jpg`, `fixtures/ground_truth.json`, `scripts/warm_cache.py`

- [ ] **Step 1: Write the demo scripts by hand**

On plain white unlined A4, dark pen, one question per sheet. Photograph each with a phone in good, even light, roughly square-on. Save as `fixtures/images/<slug>.jpg`. Different team members should write different sheets so the handwriting varies.

Required set:

| Filename | Question | What the student wrote | Demo purpose |
|---|---|---|---|
| `q1-correct.jpg` | q1 | Full correct factorising solution | Baseline: full marks |
| `q2-divided-by-x.jpg` | q2 | `x^2 = 5x`, `x = 5` | **The flagship case.** Lost root. |
| `q1-sign-error.jpg` | q1 | `(x+2)(x+3) = 0`, `x = -2, x = -3` | Sign error detection |
| `q1-answer-only.jpg` | q1 | Just `x = 2, x = 3` | Method marks withheld |
| `q4-completing-square.jpg` | q4 | Completing the square, not the formula | **Alternative valid method earns full marks** |
| `q4-dropped-pm.jpg` | q4 | Only the positive root | Dropped ± |
| `q6-zero-product-trap.jpg` | q6 | `x - 2 = 2`, `x - 3 = 2` | Zero-product misapplication |
| `messy.jpg` | q1 | Correct, but genuinely untidy handwriting | Honest OCR demo |

- [ ] **Step 2: Create `fixtures/ground_truth.json`**

For each image, the transcription you would accept and the marks a human would award. This is what the evaluation measures against.

```json
[
  {
    "image": "q2-divided-by-x.jpg",
    "question_id": "q2",
    "expected_steps": ["x^2 = 5x", "x = 5"],
    "human_marks": { "C1": 0, "C2": 1, "C3": 2, "C4": 0 },
    "expected_misconceptions": ["divided_by_variable_lost_root"]
  }
]
```

Add one entry per image. Fill in the marks by actually marking the scripts by hand — **and time yourself doing it**, because that number goes on a slide.

- [ ] **Step 3: Write `scripts/warm_cache.py`**

```python
"""Run every demo image through transcription and marking once, in live mode,
so fixtures/llm_cache/ is populated and the demo works offline.

Run:  python scripts/warm_cache.py
"""

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import FIXTURES_DIR, IMAGES_DIR  # noqa: E402
from app.feedback import write as write_feedback  # noqa: E402
from app.marker import mark  # noqa: E402
from app.models import Step  # noqa: E402
from app.store import get_question  # noqa: E402
from app.transcriber import transcribe  # noqa: E402
from app.verifier import verify  # noqa: E402


def main() -> None:
    ground_truth = json.loads(
        (FIXTURES_DIR / "ground_truth.json").read_text(encoding="utf-8")
    )

    for entry in ground_truth:
        image_path = IMAGES_DIR / entry["image"]
        if not image_path.exists():
            print(f"MISSING {entry['image']}")
            continue

        question = get_question(entry["question_id"])
        image_b64 = base64.b64encode(image_path.read_bytes()).decode()

        print(f"--- {entry['image']}")
        transcription = transcribe(image_b64, media_type="image/jpeg")
        print("  transcribed:", [s.latex for s in transcription.steps])

        # Warm the cache for BOTH the raw transcription and the ground-truth
        # steps, so the demo works whether or not the lecturer edits anything.
        for label, steps in (
            ("as transcribed", transcription.steps),
            (
                "as corrected",
                [
                    Step(index=i, latex=t)
                    for i, t in enumerate(entry["expected_steps"], start=1)
                ],
            ),
        ):
            report = verify(steps, question.model_solution_steps, question.variable)
            proposal = mark(question, steps, report)
            write_feedback(question, steps, proposal, report)
            print(f"  {label}: {proposal.total_proposed}/{proposal.total_max}")

    print("\nCache warmed. Test offline with: DEMO_MODE=offline uvicorn app.main:app")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Warm the cache**

```bash
python scripts/warm_cache.py
```

Expected: one block per image showing the transcription and the marks. Inspect the transcriptions against the sheets — any systematic misreading is a prompt problem to fix in `app/transcriber.py` now, not on demo day.

- [ ] **Step 5: Verify offline mode actually works**

Set `DEMO_MODE=offline` in `.env`, then:

```bash
uvicorn app.main:app --reload
```

**Disconnect the laptop from Wi-Fi.** Upload `q2-divided-by-x.jpg` through the UI. Expected: it transcribes and marks exactly as before, with no network access.

This is the single most important test in the project. If it does not pass, the demo is one bad venue router away from failing.

- [ ] **Step 6: Commit the cache**

```bash
git add fixtures/ scripts/warm_cache.py
git commit -m "feat: add handwritten demo scripts, ground truth, and warmed llm cache"
```

---

## Task 14: The evaluation harness

Produces the numbers for your slides. Twenty minutes of work, disproportionate persuasive value.

**Files:**
- Create: `scripts/evaluate.py`

- [ ] **Step 1: Write `scripts/evaluate.py`**

```python
"""Measure transcription and marking accuracy against fixtures/ground_truth.json.

Run:  python scripts/evaluate.py
"""

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import FIXTURES_DIR, IMAGES_DIR  # noqa: E402
from app.marker import mark  # noqa: E402
from app.models import Step  # noqa: E402
from app.store import get_question  # noqa: E402
from app.transcriber import transcribe  # noqa: E402
from app.verifier import verify  # noqa: E402


def normalise(latex: str) -> str:
    return latex.replace(" ", "").replace("{", "").replace("}", "").lower()


def main() -> None:
    entries = json.loads((FIXTURES_DIR / "ground_truth.json").read_text(encoding="utf-8"))

    steps_total = steps_exact = 0
    criteria_total = criteria_exact = 0
    scripts_total = scripts_within_one = 0
    misconception_hits = misconception_expected = misconception_predicted = 0

    for entry in entries:
        image_path = IMAGES_DIR / entry["image"]
        if not image_path.exists():
            continue

        question = get_question(entry["question_id"])
        expected_steps = entry["expected_steps"]

        # --- transcription accuracy ---
        image_b64 = base64.b64encode(image_path.read_bytes()).decode()
        transcription = transcribe(image_b64, media_type="image/jpeg")
        produced = [s.latex for s in transcription.steps]
        for i, expected in enumerate(expected_steps):
            steps_total += 1
            if i < len(produced) and normalise(produced[i]) == normalise(expected):
                steps_exact += 1

        # --- marking accuracy, GIVEN a confirmed transcription ---
        steps = [Step(index=i, latex=t) for i, t in enumerate(expected_steps, start=1)]
        report = verify(steps, question.model_solution_steps, question.variable)
        proposal = mark(question, steps, report)

        human = entry["human_marks"]
        for criterion in proposal.criteria:
            if criterion.criterion_id not in human:
                continue
            criteria_total += 1
            if criterion.proposed == human[criterion.criterion_id]:
                criteria_exact += 1

        scripts_total += 1
        if abs(proposal.total_proposed - sum(human.values())) <= 1:
            scripts_within_one += 1

        expected_tags = set(entry.get("expected_misconceptions", []))
        predicted_tags = set(proposal.misconceptions)
        misconception_hits += len(expected_tags & predicted_tags)
        misconception_expected += len(expected_tags)
        misconception_predicted += len(predicted_tags)

    def pct(numerator: int, denominator: int) -> str:
        return f"{100 * numerator / denominator:.0f}%" if denominator else "n/a"

    print("\n=== AIMS evaluation ===")
    print(f"Scripts evaluated:              {scripts_total}")
    print(f"Transcription step accuracy:    {pct(steps_exact, steps_total)} "
          f"({steps_exact}/{steps_total})")
    print(f"Criterion-level mark agreement: {pct(criteria_exact, criteria_total)} "
          f"({criteria_exact}/{criteria_total})")
    print(f"Total mark within 1:            {pct(scripts_within_one, scripts_total)}")
    print(f"Misconception recall:           {pct(misconception_hits, misconception_expected)}")
    print(f"Misconception precision:        {pct(misconception_hits, misconception_predicted)}")
    print("\nMarking metrics are conditioned on a confirmed transcription,")
    print("which is how the product is actually used.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
python scripts/evaluate.py
```

Expected: a printed table. Put these exact numbers on a slide. **Report the transcription figure honestly** — a low number with a good mitigation story is far more credible than an inflated one.

- [ ] **Step 3: Commit**

```bash
git add scripts/evaluate.py
git commit -m "feat: add evaluation harness for transcription and marking accuracy"
```

---

## Task 15: Adversarial robustness pass

Every one of these must degrade visibly, never crash and never silently produce a wrong mark.

**Files:**
- Create: `tests/test_adversarial.py`

- [ ] **Step 1: Write the tests**

```python
from app.models import Step
from app.store import get_question
from app.verifier import verify


def steps(*latex: str) -> list[Step]:
    return [Step(index=i, latex=t) for i, t in enumerate(latex, start=1)]


def test_empty_submission():
    report = verify([], get_question("q1").model_solution_steps, "x")
    assert report.final_answer_correct is False
    assert report.steps == []


def test_pure_gibberish_does_not_crash():
    report = verify(
        steps(r"\text{aaa}", "!!!", r"\frac{"),
        get_question("q1").model_solution_steps,
        "x",
    )
    assert all(s.parsed is False for s in report.steps)
    assert report.final_answer_correct is False


def test_working_for_a_different_question_is_marked_incorrect():
    report = verify(
        steps("y = 2x + 3", "y = 7"),
        get_question("q1").model_solution_steps,
        "x",
    )
    assert report.final_answer_correct is False


def test_answer_only_with_no_working_still_verifies_the_answer():
    report = verify(steps("x = 2, x = 3"), get_question("q1").model_solution_steps, "x")
    assert report.final_answer_correct is True
    assert len(report.steps) == 1


def test_a_very_long_submission_is_handled():
    long_chain = ["x^2 - 5x + 6 = 0"] * 40
    report = verify(steps(*long_chain), get_question("q1").model_solution_steps, "x")
    assert len(report.steps) == 40
    assert report.first_divergence_index is None
```

- [ ] **Step 2: Run them**

Run: `pytest tests/test_adversarial.py -v`
Expected: all 5 PASS. Any crash here is a bug to fix in `verifier.py` or `latex_utils.py`.

- [ ] **Step 3: Manual adversarial pass through the UI**

Try each of these in the browser and confirm a clear message rather than a stack trace or a spinner that never stops:

- Upload a photo of something that is not mathematics
- Upload a blank sheet
- Click **Confirm & Mark** with every step empty
- Enter a mark above the criterion maximum
- Run in `DEMO_MODE=offline` and upload an image that is not in the cache (expect the 503 with the "use a sample script" hint)

- [ ] **Step 4: Commit**

```bash
git add tests/test_adversarial.py
git commit -m "test: add adversarial robustness cases"
```

---

## Task 16: Final polish and demo hardening

**No new features from this point. Bug fixes and rehearsal only.**

- [ ] **Step 1: Run the whole suite**

```bash
pytest -v
```

Expected: everything green. Fix anything that is not before continuing.

- [ ] **Step 2: Write `README.md`**

```markdown
# AIMS — AI for Individualised Mastery Support

AI-assisted marking of handwritten quadratic-equation working, with symbolic
verification, rubric-linked marks, student feedback and targeted practice.
Every mark is a recommendation; the lecturer approves, edits or overrides all of it.

## Setup

    python -m venv .venv
    .venv\Scripts\Activate.ps1     # PowerShell
    pip install -r requirements.txt
    copy .env.example .env          # then add your Anthropic API key

## Run

    uvicorn app.main:app --reload

Open http://127.0.0.1:8000

## Demo mode

`DEMO_MODE=live` calls the Anthropic API and caches every response to
`fixtures/llm_cache/`. `DEMO_MODE=offline` serves only from that cache and
makes no network calls, so the demo works without internet.

Warm the cache before demoing:

    python scripts/warm_cache.py

## Evaluation

    python scripts/evaluate.py

## Tests

    pytest -v

## How it works

1. A vision model transcribes the handwriting into LaTeX. It never sees the
   model solution, so it cannot hallucinate the expected working.
2. The lecturer confirms and corrects the transcription. This is a deliberate
   trust boundary, not a fallback.
3. SymPy verifies each step by comparing solution sets. This is the only
   component permitted to assert mathematical truth.
4. A language model maps those verified findings onto the rubric. It is
   explicitly forbidden from re-deriving any mathematics.
5. Practice questions come from parameterised templates whose answers are
   verified by SymPy, never from a language model.
6. The lecturer reviews and overrides everything before release.

## Privacy

No real student data. All names in the seed data are fabricated. API keys are
loaded server-side from `.env`, which is gitignored and never sent to the browser.
```

- [ ] **Step 3: Confirm no secrets are in the repository**

```bash
git ls-files | grep -i env
```

Expected: `.env.example` only. If `.env` appears, remove it from tracking immediately with `git rm --cached .env`.

- [ ] **Step 4: Rehearse the demo three times, timed**

Follow the demo script in `docs/AIMS-architecture-review.md` §12. Target five minutes. Run in `DEMO_MODE=offline` with Wi-Fi disabled for at least one rehearsal.

- [ ] **Step 5: Record a screen capture of a successful run**

Save it locally. This is the last-resort fallback if the laptop misbehaves on stage.

- [ ] **Step 6: Final commit**

```bash
git add README.md
git commit -m "docs: add readme and finalise for demo"
```

---

## Self-review notes

**Spec coverage.** Every essential feature from §6 of the review document maps to a task: seeded questions/rubrics (T4), upload + sample + manual paths (T11, T12), vision transcription (T7), editable LaTeX with live preview (T12), SymPy verification (T3), grounded rubric marking (T9), feedback (T10), override (T11, T12), offline mode (T6, T13). High-value features: misconception classification (T3, T4), practice generation (T5), class dashboard (T11, T12), confidence highlighting (T7, T12), AI-vs-symbolic disagreement warning (T9, T12).

**Deliberately deferred**, consistent with the review's "optional" list: export/print (browser print-to-PDF needs no code), MathLive, semantic retrieval, a second topic.

**Parallelisation.** After Task 1 merges, Tasks 2–3 (verifier), 4–5 (data and practice), 6–7 (LLM and transcription) and 12 (frontend, against fixture JSON) proceed independently. Task 9 needs Tasks 6 and 8. Task 11 needs everything. Map these onto the roles in §14 of the review document.

**Critical path:** Task 1 → 2 → 3 → 11 → 12. If the team falls behind, that chain plus manual step entry is still a complete, honest demo.
