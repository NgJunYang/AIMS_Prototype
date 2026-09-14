# Math Verification Trust Tiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop hard-blocking a question's model solution just because it isn't a single-variable algebraic equation SymPy can parse, by classifying it into a `verified`/`ai_graded` trust tier instead of refusing to save it, and unlock whole-PDF import for Graded CA and Final Exam assignments.

**Architecture:** A new `compute_verification_tier(question)` in `app/authoring.py` reuses the exact per-step parse check `_mathematical_problems` already runs, but returns a tier instead of a blocking error when a step can't be read as mathematics. `_mathematical_problems` keeps blocking only when every step parses but the chain doesn't self-verify (the case the tool can actually prove is wrong). The tier is persisted on `Question`/`QuestionDraft`, surfaced through the existing `QuestionCheck`/import-review responses, and shown as a badge everywhere marks or a model solution are displayed. `app/verifier.py` and `app/marker.py` need no changes — they already degrade gracefully for unparseable content.

**Tech Stack:** FastAPI + Pydantic backend (Python), React + TypeScript frontend, pytest, vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-09-14-math-verification-trust-tiers-design.md`

---

### Task 1: Data model — add the tier fields

**Files:**
- Modify: `app/models.py`
- Modify: `app/ingestion_models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_old_question_json_defaults_to_verified_tier_with_no_override():
    question = Question.model_validate_json(
        '{"id":"q1","prompt":"Solve $x=1$.","model_solution_steps":["x=1","x=1"],"criteria":[]}'
    )
    assert question.verification_tier == "verified"
    assert question.verification_tier_override is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_old_question_json_defaults_to_verified_tier_with_no_override -v`
Expected: FAIL with `AttributeError: 'Question' object has no attribute 'verification_tier'`

- [ ] **Step 3: Add `VerificationTier` and the `Question` fields**

In `app/models.py`, right after the existing `Divergence = Literal[...]` block (line 12, before the `# ---------- Assignment definition (seed data) ----------` comment), add:

```python
VerificationTier = Literal[
    "verified",    # every model-solution step parsed and the chain self-checks with SymPy
    "ai_graded",   # at least one step falls outside what the symbolic verifier can check
]
```

In the `Question` class (`app/models.py`), add two fields right after `criteria: list[Criterion]`:

```python
class Question(BaseModel):
    id: str
    label: str | None = None
    source_import_id: str | None = None
    source_pages: list[int] = Field(default_factory=list)
    solution_source_pages: list[int] = Field(default_factory=list)
    prompt: str
    model_solution_steps: list[str]
    variable: str = "x"
    topic_tag: str = "quadratics"
    criteria: list[Criterion]
    # Whether the model solution is SymPy-verified or falls outside what the
    # symbolic verifier can check (a proof, a sum, set notation, ...), plus an
    # instructor's explicit override of that computed value. The computed
    # value is never overwritten by the override - see compute_verification_tier
    # in app/authoring.py, which is the only place that sets verification_tier.
    verification_tier: VerificationTier = "verified"
    verification_tier_override: VerificationTier | None = None
    ...
```

(Keep every other field on `Question` exactly as it is - only insert the two new lines.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py::test_old_question_json_defaults_to_verified_tier_with_no_override -v`
Expected: PASS

- [ ] **Step 5: Add the matching fields to `QuestionDraft`**

In `app/ingestion_models.py`, add the import and two fields:

```python
from app.models import Criterion, IdentityExtraction, Step, Transcription, VerificationTier
```

```python
class QuestionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(default="", max_length=100)
    prompt: str = Field(default="", max_length=12000)
    source_pages: list[int] = Field(default_factory=list, max_length=20)
    confidence: Literal["high", "low"] = "high"
    notes: str = ""
    question_id: str | None = None
    variable: str = "x"
    topic_tag: str = "quadratics"
    model_solution_steps: list[str] = Field(default_factory=list, max_length=200)
    criteria: list[Criterion] = Field(default_factory=list, max_length=30)
    solution_source_pages: list[int] = Field(default_factory=list, max_length=20)
    solution_transcription: Transcription | None = None
    problems: list[str] = Field(default_factory=list)
    # Live-preview tiering shown during whole-PDF import, before any Question
    # is actually saved. See app/authoring.py::compute_verification_tier.
    verification_tier: VerificationTier = "verified"
    verification_tier_notes: list[str] = Field(default_factory=list)
```

- [ ] **Step 6: Run the full backend test suite to check for regressions**

Run: `pytest tests/ -q`
Expected: PASS, same pass count as before this task plus the one new test (no existing test constructs `Question`/`QuestionDraft` with `extra="forbid"`-breaking unknown fields, and every new field has a default, so nothing else should move)

- [ ] **Step 7: Commit**

```bash
git add app/models.py app/ingestion_models.py tests/test_models.py
git commit -m "feat: add verification_tier fields to Question and QuestionDraft"
```

---

### Task 2: `app/authoring.py` — compute the tier instead of hard-blocking

**Files:**
- Modify: `app/authoring.py`
- Test: `tests/test_authoring.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_authoring.py`, change the import line to:

```python
from app.authoring import DEFAULT_CRITERIA, compute_verification_tier, default_criteria, validate_question
```

Replace the two existing tests below (they currently assert hard-blocking behavior that this task changes on purpose) with new versions asserting the tiering behavior:

Delete:
```python
def test_an_unparseable_model_solution_line_is_rejected():
    problems = validate_question(
        _question(
            model_solution_steps=[
                "x^2 - 7x + 12 = 0",
                "then I factorised it somehow",
                "x = 3, x = 4",
            ]
        )
    )
    assert problems
    assert any("could not be read" in p.lower() for p in problems)
```

Replace with:
```python
def test_an_unparseable_model_solution_line_is_ai_graded_not_rejected():
    """Non-algebraic content (a proof, a sum, prose) is not an authoring
    error: it falls outside what SymPy can check, so it is tiered instead of
    refused. The instructor still sees why, just as a non-blocking note.
    """
    question = _question(
        model_solution_steps=[
            "x^2 - 7x + 12 = 0",
            "then I factorised it somehow",
            "x = 3, x = 4",
        ]
    )
    assert validate_question(question) == []
    tier, notes = compute_verification_tier(question)
    assert tier == "ai_graded"
    assert any("step 2" in n.lower() for n in notes)
```

Delete:
```python
def test_a_solution_in_a_different_variable_from_the_declared_one_is_rejected():
    """Declaring `y` but writing the solution in `x` would make every step
    unverifiable, so it is caught here rather than at marking time."""
    problems = validate_question(_question(variable="y"))
    assert problems
```

Replace with:
```python
def test_a_solution_in_a_different_variable_from_the_declared_one_is_ai_graded():
    """A model solution written in x but declared as y cannot be checked by
    SymPy either - the free-symbol guard in parse_equation_line treats a
    variable mismatch exactly like any other unparseable line (see
    app/latex_utils.py). It downgrades to ai_graded rather than being
    silently accepted as sound; the notes keep the mismatch visible to the
    instructor every time the question is viewed, not just at save time.
    """
    question = _question(variable="y")
    assert validate_question(question) == []
    tier, notes = compute_verification_tier(question)
    assert tier == "ai_graded"
    assert notes
```

Also add, near the top of the `# ---------- the invariant that matters ----------` section:

```python
def test_a_sound_question_is_tiered_verified():
    assert compute_verification_tier(_question()) == ("verified", [])
```

- [ ] **Step 2: Run tests to verify the new/changed ones fail**

Run: `pytest tests/test_authoring.py -v`
Expected: `test_a_sound_question_is_tiered_verified`, `test_an_unparseable_model_solution_line_is_ai_graded_not_rejected`, and `test_a_solution_in_a_different_variable_from_the_declared_one_is_ai_graded` FAIL with `ImportError: cannot import name 'compute_verification_tier'` (it doesn't exist yet)

- [ ] **Step 3: Add `compute_verification_tier` and narrow `_mathematical_problems`**

In `app/authoring.py`, change the import line at the top:

```python
from app.models import Criterion, Question, Step, VerificationTier
```

Add a new function right before `_mathematical_problems`:

```python
def compute_verification_tier(question: Question) -> tuple[VerificationTier, list[str]]:
    """Classify a model solution as SymPy-verified or not, without blocking either way.

    Mirrors the per-step parse check `_mathematical_problems` runs, but a
    step that can't be read as mathematics in the declared variable - a
    proof, a sum, set notation, or simply the wrong variable - downgrades
    the tier instead of failing validation. Only a self-contradiction
    *within* content that does parse remains a hard block; that stays in
    `_mathematical_problems`, unchanged.
    """
    if len(question.model_solution_steps) < 2:
        return "verified", []
    notes = [
        f"Step {index} could not be read as mathematics in "
        f"'{question.variable}': {latex!r}"
        for index, latex in enumerate(question.model_solution_steps, start=1)
        if solution_set(latex, question.variable) is None
    ]
    return ("ai_graded", notes) if notes else ("verified", [])
```

Replace `_mathematical_problems` with:

```python
def _mathematical_problems(question: Question) -> list[str]:
    """Run the lecturer's own model solution through the student verifier.

    Only runs the self-consistency check when every step parses as an
    equation in the declared variable. A question that can't be read that
    way is tiered by compute_verification_tier instead of being refused.
    """
    if len(question.model_solution_steps) < 2:
        return []  # already reported; verifying one line says nothing useful

    tier, _ = compute_verification_tier(question)
    if tier == "ai_graded":
        return []

    problems: list[str] = []
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_authoring.py -v`
Expected: PASS, all tests including `test_a_model_solution_that_loses_a_root_is_rejected` and `test_a_model_solution_with_a_sign_error_is_rejected` (those two are unaffected - every step in their fixtures parses fine, so they still hit the divergence check exactly as before)

- [ ] **Step 5: Run the seed integrity test to confirm zero regression on real content**

Run: `pytest tests/test_seed_integrity.py -v`
Expected: PASS (all seeded quadratics still fully parse and self-verify, so they're still tiered `verified`)

- [ ] **Step 6: Commit**

```bash
git add app/authoring.py tests/test_authoring.py
git commit -m "feat: tier non-algebraic model solutions as ai_graded instead of rejecting them"
```

---

### Task 3: `app/ingestion_api.py` — unlock CA/exam import and surface the tier

**Files:**
- Modify: `app/ingestion_api.py`
- Modify: `app/tutorial_ingestion.py`
- Test: `tests/test_tutorial_ingestion.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_tutorial_ingestion.py`:

```python
@pytest.mark.parametrize("kind", ["ca", "exam"])
def test_whole_pdf_import_is_allowed_for_ca_and_exam_assignments(monkeypatch, kind):
    assert client.post("/api/assignments", json={"id": "g1", "title": "Graded CA 1", "kind": kind}).status_code == 200
    calls = response(monkeypatch, {"title": "Graded CA 1", "questions": [
        {"label": f"Q{i + 1}", "prompt": f"Solve ${equation}$.", "source_pages": [1 if i < 3 else 2]}
        for i, equation in enumerate(EQUATIONS)]})
    result = upload("/api/assignments/g1/imports/questions", "01")
    assert result.status_code == 200, result.text
    assert len(calls) == 1


def test_an_unparseable_solution_step_is_ai_graded_not_rejected(monkeypatch):
    draft = confirm_questions(question_import(monkeypatch))
    rows = working_rows(draft)
    rows[2]["steps"] = [{"index": 1, "latex": "2x^2 - 8x = 0"}, {"index": 2, "latex": "then I expanded it somehow"}]
    response(monkeypatch, {"solutions": rows})
    extracted = upload(f"/api/tutorial-imports/{draft['id']}/solutions", "02", {"revision": draft["revision"]}).json()
    assert extracted["questions"][2]["verification_tier"] == "ai_graded"
    assert not extracted["questions"][2]["problems"]
    result = confirm_solutions(extracted)
    assert result.status_code == 200, result.text
    assert store.get_question(extracted["questions"][2]["question_id"]).verification_tier == "ai_graded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tutorial_ingestion.py -k "ai_graded_not_rejected or ca_and_exam" -v`
Expected: `test_whole_pdf_import_is_allowed_for_ca_and_exam_assignments` FAILs with `assert 409 == 200`; `test_an_unparseable_solution_step_is_ai_graded_not_rejected` FAILs with a `KeyError: 'verification_tier'` (the draft response has no such field yet)

- [ ] **Step 3: Remove the kind gate and rename `solution_problems` to carry the tier**

In `app/tutorial_ingestion.py`, change the import line:

```python
from app.authoring import compute_verification_tier, default_criteria, validate_question
```

Replace `solution_problems` (the last function in the file) with:

```python
def solution_review(question: QuestionDraft, solution: MappedWorking) -> tuple[list[str], "VerificationTier", list[str]]:
    """Problems, verification tier, and tier notes for a proposed model
    solution, without saving anything. Used for the live preview shown right
    after a solutions PDF is matched, before confirmation.
    """
    candidate = Question(id=question.question_id or "draft", prompt=question.prompt,
                         variable=question.variable, topic_tag=question.topic_tag,
                         model_solution_steps=[s.latex for s in solution.steps], criteria=solution.criteria)
    tier, notes = compute_verification_tier(candidate)
    return validate_question(candidate), tier, notes
```

Add `VerificationTier` to the existing `from app.models import IdentityExtraction, Question` import line, so it reads:

```python
from app.models import IdentityExtraction, Question, VerificationTier
```

In `app/ingestion_api.py`, change the import line:

```python
from app.authoring import compute_verification_tier, validate_question
```

Remove the kind gate from `_assignment`:

```python
def _assignment(assignment_id: str) -> Assignment:
    try:
        assignment = store.load_assignment(assignment_id)
    except KeyError:
        raise HTTPException(404, "Unknown assignment.")
    return assignment
```

In `solution_pdf`, replace the loop that builds `question.problems`:

```python
            for question in draft.questions:
                matches = [s for s in solutions if s.question_id == question.question_id]
                if len(matches) == 1:
                    question.problems, question.verification_tier, question.verification_tier_notes = ingestion.solution_review(question, matches[0])
                else:
                    question.problems = ["Solution mapping needs correction."]
                    question.verification_tier, question.verification_tier_notes = "ai_graded", []
```

In `confirm_solutions`, after building `candidate` and before `problems.extend(...)`, add the tier computation:

```python
        for question in body.questions:
            _pages(question.source_pages, draft.page_count)
            solution = next(s for s in body.solutions if s.question_id == question.question_id)
            candidate = Question(id=question.question_id, label=ingestion.normalize_label(question.label),
                                 prompt=question.prompt.strip(), variable=question.variable, topic_tag=question.topic_tag,
                                 model_solution_steps=[s.latex for s in solution.steps], criteria=solution.criteria,
                                 source_import_id=draft.id, source_pages=question.source_pages,
                                 solution_source_pages=solution.source_pages,
                                 solution_source_page=next(iter(solution.source_pages), None),
                                 solution_transcription=Transcription(steps=next((s.steps for s in draft.solutions if s.block_id == solution.block_id), []), notes=solution.notes))
            candidate.verification_tier, _ = compute_verification_tier(candidate)
            problems.extend(f"{candidate.label}: {p}" for p in validate_question(candidate))
            questions.append(candidate)
```

(Only the one new line `candidate.verification_tier, _ = compute_verification_tier(candidate)` is added; everything else in that loop is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tutorial_ingestion.py -v`
Expected: PASS, including `test_solution_errors_are_flagged_and_final_validation_stays_strict` (unaffected - that test corrupts a step to lose a root, which still parses fine and still hits the hard divergence block)

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/ingestion_api.py app/tutorial_ingestion.py tests/test_tutorial_ingestion.py
git commit -m "feat: unlock whole-PDF import for CA/exam assignments and tier non-algebraic solutions"
```

---

### Task 4: `app/main.py` — surface the tier on manual question authoring

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`, near `test_validate_reports_problems_without_saving_anything`:

```python
def test_validate_reports_the_verification_tier():
    good = client.post("/api/questions/validate", json=NEW_QUESTION).json()
    assert good["verification_tier"] == "verified"
    assert good["verification_tier_notes"] == []

    non_algebraic = {**NEW_QUESTION, "model_solution_steps": [
        "x^2 - 7x + 12 = 0", "then I factorised it somehow", "x = 3, x = 4",
    ]}
    checked = client.post("/api/questions/validate", json=non_algebraic).json()
    assert checked["ok"] is True
    assert checked["verification_tier"] == "ai_graded"
    assert checked["verification_tier_notes"]


def test_a_non_algebraic_model_solution_saves_as_ai_graded_not_rejected():
    non_algebraic = {**NEW_QUESTION, "model_solution_steps": [
        "x^2 - 7x + 12 = 0", "then I factorised it somehow", "x = 3, x = 4",
    ]}
    created = client.post("/api/questions", json=non_algebraic)
    assert created.status_code == 200, created.text
    assert created.json()["verification_tier"] == "ai_graded"
    assert client.get("/api/questions/authored1").json()["verification_tier"] == "ai_graded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -k "verification_tier or ai_graded" -v`
Expected: FAIL with `KeyError: 'verification_tier'` (not on the response yet)

- [ ] **Step 3: Extend `QuestionCheck` and the question endpoints**

In `app/main.py`, add `VerificationTier` to the existing `from app.models import (...)` block (insert alphabetically, right after `Submission,`):

```python
from app.models import (
    Assignment,
    AssignmentReviewStatus,
    ClassSummary,
    Feedback,
    FeedbackSettings,
    IdentityExtraction,
    Question,
    Step,
    Submission,
    Transcription,
    VerificationTier,
)
```

Change the import line for authoring:

```python
from app.authoring import compute_verification_tier, default_criteria, validate_question
```

Update `QuestionCheck`:

```python
class QuestionCheck(BaseModel):
    ok: bool
    problems: list[str] = Field(default_factory=list)
    verification_tier: VerificationTier = "verified"
    verification_tier_notes: list[str] = Field(default_factory=list)
```

Update `api_validate_question`:

```python
@app.post("/api/questions/validate")
def api_validate_question(question: Question) -> QuestionCheck:
    """Dry-run the same checks saving would apply, without saving.

    Lets the lecturer see their own model solution verified before committing
    to it, which is the point: the tool holds the author to the standard it
    holds the student to.
    """
    problems = validate_question(question)
    tier, notes = compute_verification_tier(question)
    return QuestionCheck(ok=not problems, problems=problems, verification_tier=tier, verification_tier_notes=notes)
```

Update `api_create_question` to persist the computed tier (add the one new line before `save_question(question)`):

```python
@app.post("/api/questions")
def api_create_question(question: Question) -> Question:
    if question.id in {q.id for q in list_questions()}:
        raise HTTPException(
            status_code=409, detail=f"a question with id {question.id!r} already exists"
        )
    problems = validate_question(question)
    if problems:
        raise HTTPException(status_code=400, detail=problems)
    question.verification_tier, _ = compute_verification_tier(question)
    save_question(question)
    return question
```

Update `api_update_question` the same way (add the one new line before `save_question(question)`, after its `if problems:` check):

```python
@app.put("/api/questions/{question_id}")
@submission_transaction
def api_update_question(question_id: str, question: Question) -> Question:
    existing = _question(question_id)
    if question.id != question_id:
        raise HTTPException(
            status_code=400, detail="a question's id cannot be changed"
        )
    problems = validate_question(question)
    if problems:
        raise HTTPException(status_code=400, detail=problems)
    question.verification_tier, _ = compute_verification_tier(question)

    save_question(question)
    ...
```

(Leave everything after `save_question(question)` in `api_update_question` - the stale-mark-clearing logic - exactly as it is.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS, full file

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_api.py
git commit -m "feat: surface verification tier on question validate/create/update endpoints"
```

---

### Task 5: Frontend types — add the tier fields

**Files:**
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Add `VerificationTier` and extend `Question`, `ImportQuestion`, and a new `QuestionCheck` type**

In `frontend/src/types.ts`, add near the top (right after `export type Confidence = "high" | "low";`):

```ts
export type VerificationTier = "verified" | "ai_graded";
```

In the `Question` interface, add two optional fields (optional because many existing test fixtures construct a `Question` without knowing about this field, and `undefined` should behave exactly like `"verified"` everywhere it's read):

```ts
export interface Question {
  id: string;
  label?: string | null;
  source_import_id?: string | null;
  source_pages?: number[];
  solution_source_pages?: number[];
  prompt: string;
  variable: string;
  topic_tag: string;
  model_solution_steps: string[];
  criteria: Criterion[];
  solution_image_filename?: string | null;
  solution_source_page?: number | null;
  solution_transcription?: SolutionTranscription | null;
  verification_tier?: VerificationTier;
  verification_tier_override?: VerificationTier | null;
}
```

In the `ImportQuestion` interface, add the same-spirit fields (also optional, for the same reason):

```ts
export interface ImportQuestion {
  question_id: string | null;
  label: string;
  prompt: string;
  variable: string;
  topic_tag: string;
  source_pages: number[];
  confidence: "high" | "low";
  notes: string;
  problems: string[];
  verification_tier?: VerificationTier;
  verification_tier_notes?: string[];
}
```

Add a new exported interface for the `/api/questions/validate` response, right after `ApiErrorLike`:

```ts
export interface QuestionCheck {
  ok: boolean;
  problems: string[];
  verification_tier: VerificationTier;
  verification_tier_notes: string[];
}
```

- [ ] **Step 2: Type-check the frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors (every new field is optional or on a brand-new type, so no existing fixture/call site needs to change yet)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat: add VerificationTier to frontend Question/ImportQuestion types"
```

---

### Task 6: Unlock whole-PDF import for CA/exam and show the tier badge

**Files:**
- Modify: `frontend/src/pages/Assignments.tsx`
- Modify: `frontend/src/components/TutorialImportPanel.tsx`
- Modify: `frontend/tests/tutorial-import.test.tsx`
- Create: `frontend/tests/assignments-import-gate.test.tsx`

- [ ] **Step 1: Write the failing test for the Assignments-level gate**

Create `frontend/tests/assignments-import-gate.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Assignments from "../src/pages/Assignments";
import { api } from "../src/lib/api";
import { ingestionApi } from "../src/lib/ingestionApi";

vi.mock("../src/components/ui/Toast", () => ({ useToast: () => ({ error: vi.fn(), success: vi.fn() }) }));

afterEach(cleanup);

test("whole-PDF import is offered for graded CA and final exam assignments, not just tutorials", async () => {
  vi.spyOn(api, "listAssignments").mockResolvedValue([
    { id: "ca1", title: "CA 1", kind: "ca", question_ids: [], roster: [], created_at: "" },
    { id: "exam1", title: "Final Exam", kind: "exam", question_ids: [], roster: [], created_at: "" },
  ]);
  vi.spyOn(api, "listQuestions").mockResolvedValue([]);
  vi.spyOn(ingestionApi, "list").mockResolvedValue([]);
  render(<Assignments />);
  await screen.findByText("CA 1");
  expect(screen.getAllByLabelText("Upload Question Paper PDF")).toHaveLength(2);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run tests/assignments-import-gate.test.tsx`
Expected: FAIL - `getAllByLabelText` finds 0 elements, because `TutorialImportPanel` only renders for `kind === "tutorial"`

- [ ] **Step 3: Remove the kind gate in `Assignments.tsx`**

In `frontend/src/pages/Assignments.tsx`, replace:

```tsx
      {assignment.kind === "tutorial" && <TutorialImportPanel assignmentId={assignment.id} ready={assignment.question_ids.length > 0} onChanged={onChanged} onOpen={onOpenReview} />}
```

with:

```tsx
      <TutorialImportPanel assignmentId={assignment.id} ready={assignment.question_ids.length > 0} onChanged={onChanged} onOpen={onOpenReview} />
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run tests/assignments-import-gate.test.tsx`
Expected: PASS

- [ ] **Step 5: Write the failing test for the tier badge**

In `frontend/tests/tutorial-import.test.tsx`, update the `questions()` fixture helper to include the new fields (backend always sends them, so the fixture should model that):

```tsx
const questions = () => ["Q1", "Q2(a)"].map((label, i) => ({ question_id: `qid${i}`, label,
  prompt: `Solve x = ${i + 1}`, variable: "x", topic_tag: "algebra", source_pages: [1, 2], confidence: "high" as const, notes: "",
  problems: [], verification_tier: "verified" as const, verification_tier_notes: [] }));
```

Add a new test after `"solutions and rubrics require per-block confirmation and remain editable"`:

```tsx
test("model solutions that cannot be parsed as mathematics show an AI-graded badge instead of blocking confirmation", async () => {
  vi.spyOn(ingestionApi, "solutions").mockImplementation(async (draft) => {
    remote = { ...copy(draft), solutions: working(), solution_page_count: 2, revision: draft.revision + 1,
      questions: draft.questions.map((q, i) => i === 0
        ? { ...q, verification_tier: "ai_graded" as const, verification_tier_notes: ["Step 2 could not be read as mathematics in 'x': 'then I expanded it somehow'"] }
        : q) };
    return copy(remote);
  });
  mount();
  await upload("Upload Question Paper PDF");
  await click("Confirm Questions");
  await upload("Upload Model Solutions PDF");
  expect(screen.getByText("AI-graded — not symbolically verified")).toBeTruthy();
  expect(screen.getByText(/Step 2 could not be read as mathematics/)).toBeTruthy();
  fireEvent.click(screen.getByLabelText("Confirm block 1"));
  fireEvent.click(screen.getByLabelText("Confirm block 2"));
  expect((screen.getByRole("button", { name: "Confirm Solutions & Rubrics" }) as HTMLButtonElement).disabled).toBe(false);
});
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd frontend && npx vitest run tests/tutorial-import.test.tsx -t "AI-graded badge"`
Expected: FAIL - `screen.getByText("AI-graded — not symbolically verified")` finds nothing

- [ ] **Step 7: Add the tier badge and kind-neutral copy to `TutorialImportPanel.tsx`**

In `frontend/src/components/TutorialImportPanel.tsx`, change the section header/description:

```tsx
  return <section className="mt-5 border-t border-border pt-4" aria-label="Whole assignment PDF import">
    <h3 className="text-sm font-semibold tracking-tight">Whole assignment PDF import</h3>
    <p className="mb-4 mt-1.5 max-w-2xl text-xs leading-relaxed text-text-muted">Review the detected content before saving or marking. Up to 20 pages / 20 MB per PDF. Results stay private until final publication.</p>
```

Change the student-PDF upload label:

```tsx
        {ready && <PdfInput label="Upload Completed Assignment PDF" onFile={(file) => run("Detecting student answers…", async () => { setDraft(await ingestionApi.student(assignmentId, file)); setMarkErrors([]); })} />}
```

Insert the tier badge right after the `question.notes` line and before `question.problems.map`:

```tsx
            {question.notes && <p className="text-xs text-text-muted">{question.notes}</p>}
            {draft.stage === "solutions" && draft.solution_page_count > 0 && (
              <Badge tone={question.verification_tier === "ai_graded" ? "warning" : "success"}>
                {question.verification_tier === "ai_graded" ? "AI-graded — not symbolically verified" : "SymPy-verified"}
              </Badge>
            )}
            {(question.verification_tier_notes || []).map((note, i) => <p key={i} className="text-xs text-text-muted">{note}</p>)}
            {question.problems.map((problem, i) => <p key={i} className="text-xs text-warning">{problem}</p>)}
```

- [ ] **Step 8: Update the existing "Upload Completed Tutorial PDF" label references**

In `frontend/tests/tutorial-import.test.tsx`, replace every occurrence of the string `"Upload Completed Tutorial PDF"` with `"Upload Completed Assignment PDF"` (this label appears 5 times: in the tests `"student segmentation saves corrected identity/working before marking and opens existing review"`, `"missing student answers are visible and can be confirmed blank"`, `"unmatched or duplicate mappings prevent confirmation until corrected"`, `"conflict errors preserve corrections and do not launch marking"`, and `"partial marking errors expose retry without repeating confirmation"`).

- [ ] **Step 9: Run all frontend tests to verify they pass**

Run: `cd frontend && npx vitest run tests/tutorial-import.test.tsx tests/assignments-import-gate.test.tsx`
Expected: PASS, every test in both files

- [ ] **Step 10: Run the full frontend test suite for regressions**

Run: `cd frontend && npx vitest run`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/Assignments.tsx frontend/src/components/TutorialImportPanel.tsx frontend/tests/tutorial-import.test.tsx frontend/tests/assignments-import-gate.test.tsx
git commit -m "feat: unlock whole-PDF import for CA/exam assignments and show the verification tier badge"
```

---

### Task 7: `QuestionEditor.tsx` — tier badge and instructor override

**Files:**
- Modify: `frontend/src/components/QuestionEditor.tsx`
- Create: `frontend/tests/question-editor.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/question-editor.test.tsx`:

```tsx
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { QuestionEditor } from "../src/components/QuestionEditor";
import { api } from "../src/lib/api";

vi.mock("../src/components/ui/Dialog", () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

afterEach(cleanup);

test("a non-algebraic model solution shows the AI-graded tier instead of a blocking error", async () => {
  vi.spyOn(api, "questionTemplate").mockResolvedValue({ variable: "x", criteria: [] });
  vi.spyOn(api, "validateQuestion").mockResolvedValue({
    ok: true, problems: [], verification_tier: "ai_graded",
    verification_tier_notes: ["Step 2 could not be read as mathematics in 'x': 'a proof step'"],
  });
  render(<QuestionEditor question={null} onClose={vi.fn()} onSaved={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Id"), { target: { value: "q9" } });
  fireEvent.change(screen.getByLabelText(/Prompt/), { target: { value: "Prove something." } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check the maths" })); });
  expect(screen.getByText(/AI-graded, not symbolically verified/)).toBeTruthy();
  expect(screen.getByText(/Step 2 could not be read as mathematics/)).toBeTruthy();
});

test("saving includes the instructor's tier override", async () => {
  vi.spyOn(api, "questionTemplate").mockResolvedValue({ variable: "x", criteria: [] });
  vi.spyOn(api, "validateQuestion").mockResolvedValue({ ok: true, problems: [], verification_tier: "verified", verification_tier_notes: [] });
  vi.spyOn(api, "createQuestion").mockResolvedValue({});
  render(<QuestionEditor question={null} onClose={vi.fn()} onSaved={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Id"), { target: { value: "q9" } });
  fireEvent.change(screen.getByLabelText(/Prompt/), { target: { value: "Solve $x=1$." } });
  fireEvent.change(screen.getByLabelText("Verification tier override"), { target: { value: "ai_graded" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save question" })); });
  expect(vi.mocked(api.createQuestion).mock.calls[0][0].verification_tier_override).toBe("ai_graded");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run tests/question-editor.test.tsx`
Expected: FAIL - `getByLabelText("Verification tier override")` finds nothing, and the AI-graded text isn't rendered

- [ ] **Step 3: Add the tier display and override control to `QuestionEditor.tsx`**

Change the type import at the top:

```tsx
import type { Criterion, Question, QuestionCheck, SolutionTranscription, VerificationTier } from "../types";
```

Change the `checkResult` state type and add tier-override state (right after the existing `checkResult`/`saveError`/`saving` state declarations):

```tsx
  const [checkResult, setCheckResult] = useState<QuestionCheck | null>(null);
  const [saveError, setSaveError] = useState<string[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [tierOverride, setTierOverride] = useState<VerificationTier | "">(question?.verification_tier_override || "");
```

Update `questionFromEditor` to include the override (add the one new field to the returned object):

```tsx
  function questionFromEditor() {
    return {
      ...question,
      id: id.trim(),
      prompt: prompt.trim(),
      variable: variable.trim() || "x",
      topic_tag: "quadratics",
      model_solution_steps: steps.map((s) => s.trim()).filter((s) => s.length > 0),
      criteria: criteria.map((c) => ({ id: c.id, max: Number(c.max) || 0, description: c.description })),
      solution_image_filename: solutionImageFilename,
      solution_source_page: solutionSourcePage,
      solution_transcription: solutionTranscription,
      verification_tier_override: tierOverride || null,
    };
  }
```

Update `runCheck` to use the new response type:

```tsx
  async function runCheck(override?: ReturnType<typeof questionFromEditor>) {
    try {
      const result: QuestionCheck = await api.validateQuestion(override || questionFromEditor());
      setCheckResult(result);
    } catch (err) {
      setCheckResult({ ok: false, problems: problemsFrom(err), verification_tier: "verified", verification_tier_notes: [] });
    }
  }
```

Replace the `checkResult` display block near the bottom of the component:

```tsx
      {checkResult && (
        <div className={`mb-4 rounded-lg p-3 text-sm ${checkResult.ok ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>
          {checkResult.ok ? (
            <p>
              {checkResult.verification_tier === "ai_graded"
                ? "This will be AI-graded, not symbolically verified — the model solution isn't a single-variable equation SymPy can check."
                : "The model solution verifies against itself — every step preserves the solution set."}
            </p>
          ) : (
            <ul className="list-inside list-disc space-y-1">
              {checkResult.problems.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          )}
          {checkResult.verification_tier_notes.map((note, i) => (
            <p key={i} className="mt-1 text-xs text-text-muted">{note}</p>
          ))}
        </div>
      )}
      <div className="mb-4">
        <Label>Verification tier</Label>
        <select
          aria-label="Verification tier override"
          value={tierOverride}
          onChange={(e) => setTierOverride(e.target.value as VerificationTier | "")}
          className="rounded-lg border border-border bg-surface-2 px-2 py-1.5 text-sm"
        >
          <option value="">
            {checkResult ? `Auto (currently: ${checkResult.verification_tier === "ai_graded" ? "AI-graded" : "SymPy-verified"})` : "Auto"}
          </option>
          <option value="verified">Verified</option>
          <option value="ai_graded">AI-graded</option>
        </select>
      </div>
      {saveError && (
```

(This drops the old `{saveError && (` line's leading position only insofar as the new `<div>` block is inserted immediately before it - the `saveError` block itself is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run tests/question-editor.test.tsx`
Expected: PASS

- [ ] **Step 5: Run the full frontend test suite for regressions**

Run: `cd frontend && npx vitest run`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/QuestionEditor.tsx frontend/tests/question-editor.test.tsx
git commit -m "feat: show verification tier and instructor override in the question editor"
```

---

### Task 8: `Confirm.tsx` — tier badge in the assessment desk

**Files:**
- Modify: `frontend/src/pages/Confirm.tsx`
- Modify: `frontend/tests/tutorial-review.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/tutorial-review.test.tsx`, after the last existing test in the file:

```tsx
test("a question tiered ai_graded shows an AI-graded badge in the assessment desk", async () => {
  const sub: Submission = {
    id: "s4", question_id: "Q4", assignment_id: "tutorial5", channel: "tutorial",
    student_pseudonym: "Student A", student_id: "2500001", published: false, reviewed: false,
    confirmed_steps: [{ index: 1, latex: "x = 5", confidence: "high" }],
    verification: { steps: [], final_answer_correct: false, final_answer_verified: false, model_solutions: [], candidate_misconceptions: [] },
  };
  vi.spyOn(api, "getSubmission").mockResolvedValue(sub);
  vi.spyOn(api, "listQuestions").mockResolvedValue([{
    id: "Q4", prompt: "Prove something.", criteria: [{ id: "C1", max: 3, description: "Method" }],
    model_solution_steps: ["step one", "step two"], variable: "x", topic_tag: "proofs",
    verification_tier: "ai_graded",
  } satisfies Question]);
  vi.spyOn(api, "assignmentReviewStatus").mockResolvedValue({
    assignment_id: "tutorial5", assignment_title: "Tutorial 5", student_pseudonym: "Student A", student_id: "2500001",
    total_questions: 1, reviewed_count: 0, ready_to_publish: false, published: false,
    questions: [{ question_id: "Q4", submission_id: "s4", marked: false, has_feedback: false, reviewed: false, published: false, problems: [] }],
  });
  render(<WorkbenchProvider><Resume /><Confirm /></WorkbenchProvider>);
  await act(async () => { fireEvent.click(screen.getByText("Load saved question")); });
  expect(screen.getByText("AI-graded — not symbolically verified")).toBeTruthy();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run tests/tutorial-review.test.tsx -t "AI-graded badge in the assessment desk"`
Expected: FAIL - `screen.getByText("AI-graded — not symbolically verified")` finds nothing

- [ ] **Step 3: Add the tier badge to `Confirm.tsx`**

In `frontend/src/pages/Confirm.tsx`, find the header row that currently starts with:

```tsx
        <div className="flex flex-wrap items-center gap-2">
          {verified > 0 && <Badge tone="success">{verified} lines parsed</Badge>}
```

and add the tier badge immediately before it:

```tsx
        <div className="flex flex-wrap items-center gap-2">
          {submissionQuestion?.verification_tier === "ai_graded" && (
            <Badge tone="warning">AI-graded — not symbolically verified</Badge>
          )}
          {verified > 0 && <Badge tone="success">{verified} lines parsed</Badge>}
```

(Everything else in that row - `suggestionsStale`/`marks` badges, the total-marks box - is unchanged.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run tests/tutorial-review.test.tsx`
Expected: PASS, every test in the file (the new one and all pre-existing ones)

- [ ] **Step 5: Run the full frontend test suite for regressions**

Run: `cd frontend && npx vitest run`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Confirm.tsx frontend/tests/tutorial-review.test.tsx
git commit -m "feat: show the AI-graded verification tier badge in the assessment desk"
```

---

### Final check

- [ ] Run the whole backend suite once more: `pytest tests/ -q` — expect PASS
- [ ] Run the whole frontend suite once more: `cd frontend && npx vitest run` — expect PASS
- [ ] Manually smoke-test in the running app: create a Graded CA assignment, upload a question paper PDF, upload a solutions PDF containing a proof/summation question alongside a normal quadratic, confirm that the proof question shows an "AI-graded" badge, that Confirm Solutions & Rubrics succeeds, and that the CA assignment's whole-PDF import panel was visible in the first place.
