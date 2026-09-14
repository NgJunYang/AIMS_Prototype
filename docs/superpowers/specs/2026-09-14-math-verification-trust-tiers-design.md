# Math verification trust tiers (Phase 1 of "mark all types of math questions")

## Problem

The product currently only auto-marks single-variable equation-solving questions
(quadratics, per the seed data). Its verifier (`app/verifier.py`) works by parsing
each written line into a SymPy equation and comparing solution sets step to step.
Anything that isn't an equation of that shape — summations, set theory, calculus,
inequalities-as-proof-steps, discrete math — fails to parse and is currently
treated as a fatal authoring error:

- `app/authoring.py::validate_question()` raises a blocking problem for every
  model-solution step that doesn't parse as math (`"Step N could not be read as
  mathematics..."`).
- `app/ingestion_api.py::confirm_solutions()` calls `validate_question()` again
  at save time, so a whole-PDF import can never be confirmed if any question's
  model solution contains non-algebraic content — regardless of how many
  per-block "confirmed" checkboxes the instructor ticks in the UI.
- `app/ingestion_api.py::_assignment()` additionally hard-blocks whole-PDF import
  entirely for any assignment whose `kind` isn't `"tutorial"`, so Graded CA and
  Final Exam assignments can't use this import flow even for content that
  *would* parse fine.

Investigation showed the **student-marking pipeline already tolerates this
gracefully** — `verify()` returns `final_answer_verified=False` and per-step
`parsed=False` findings when math can't be read, and `marker.py`'s prompt
already instructs the LLM to "mark this step on the written evidence alone" in
that case. The only real blocker is at question-authoring/import time.

## Goal (Phase 1 scope)

Stop hard-blocking non-symbolic math at authoring time. Instead, classify each
question's model solution into a trust tier and let non-symbolic content save
and be marked (by LLM judgement against the model solution) while making that
lower trust level visible everywhere marks/feedback for that question appear.

This is Phase 1 of a larger effort. Phases 2+ (broader algebra/trig equation
support, calculus expression-equivalence checking, numeric stats/probability
verification) are separate follow-on specs that move content from the
`ai_graded` tier into `verified` by adding new deterministic checks. They are
explicitly out of scope here.

Also in scope, because it's small and was one of the three original reported
issues: unlocking whole-PDF import for `ca` and `exam` assignment kinds (today
restricted to `tutorial`).

## Non-goals

- No new deterministic verifier for calculus/discrete math/stats in this phase.
  Non-symbolic content is marked by LLM judgement only, clearly labeled.
- No redesign of the publish/review workflow. Submissions created via whole-PDF
  import keep using `channel="tutorial"` (group review/publish per student),
  regardless of the assignment's `kind`. This is an existing behavior of the
  import pipeline, not something this change introduces, and is called out
  here so it isn't a surprise when CA/exam gains the same import path.
- No change to `verifier.py` or `marker.py` internals — both already degrade
  correctly when math can't be parsed.

## Data model

`app/models.py::Question` gains two fields:

```python
VerificationTier = Literal["verified", "ai_graded"]

class Question(BaseModel):
    ...
    verification_tier: VerificationTier = "verified"          # computed at save time
    verification_tier_override: VerificationTier | None = None  # instructor's explicit choice, if any
```

- `verification_tier` is recomputed and stored every time a question's model
  solution is saved (import confirmation, manual create, manual update). It is
  never hand-edited directly.
- `verification_tier_override`, when set, is what UI and API responses show as
  the *effective* tier. It can be set in either direction (instructor may mark
  a computed `ai_graded` question as `verified` if they've manually checked it,
  or downgrade a computed `verified` question to `ai_graded` if they don't
  trust it despite it parsing). The computed `verification_tier` is always kept
  and shown alongside the effective one (e.g. "Verified (instructor override)"
  vs plain "Verified"), so the provenance of the label is never hidden — the
  audit trail survives even when overridden.
- Both fields default such that all existing seed/imported questions come back
  as `verified` with no override, matching current behavior exactly (no
  migration needed, consistent with how every other optional field on
  `Question` was introduced).

## Backend changes

### `app/authoring.py`

Split `_mathematical_problems()`:

- Per-step parse check stays, but a step that fails to parse **no longer
  appends to the blocking `problems` list**. Instead the function also returns
  (or a sibling function computes) the tier: `"ai_graded"` if any step failed
  to parse, else proceed to today's self-consistency check (`verify()` against
  the model solution's own steps) and divergence/final-answer check exactly as
  today — those remain **hard blocks** when every step parses. This preserves
  the existing guarantee for anything that *is* expressible as an equation: a
  self-contradictory "verified" model solution still can't be saved.
- New function `compute_verification_tier(question: Question) -> tuple[VerificationTier, list[str]]`
  returns the tier plus human-readable notes (e.g. which steps didn't parse),
  for UI display. `validate_question()` keeps its existing signature/contract
  (hard-blocking problems only) so every existing caller keeps working; call
  sites that want the tier call the new function alongside it.

### `app/ingestion_api.py`

- `_assignment()`: remove the `assignment.kind != "tutorial"` 409. All three
  kinds proceed.
- `confirm_solutions()`: after building each `candidate` Question, compute and
  store its tier via `compute_verification_tier()`. `validate_question()` is
  still called and its (now-narrower) problems still block saving — but a
  question no longer ends up in that list purely for containing
  non-algebraic math.
- `solution_pdf()` (the live-preview step that currently populates
  `question.problems` via `ingestion.solution_problems()` right after the
  solutions PDF is uploaded, before confirmation): same split applies, so the
  live preview shows the tier/notes instead of a red blocking-looking message
  for content that will actually be accepted.

### `app/main.py`

- `api_validate_question` / `QuestionCheck`: extend the response with the
  computed tier and notes, so the manual "add/edit question" flow in the
  Workbench shows the same information as the PDF-import flow.
- `api_create_question` / `api_update_question`: compute and persist
  `verification_tier` on save (mirrors `confirm_solutions`).

### No changes required

`app/verifier.py`, `app/marker.py`, `app/feedback.py` — confirmed these already
handle unparseable/unverifiable content correctly per-step and per-submission.

## Frontend changes

- `frontend/src/pages/Assignments.tsx`: render the import panel for all three
  `kind` values, not just `"tutorial"`.
- `TutorialImportPanel.tsx` (rename to something kind-neutral, e.g.
  `AssignmentImportPanel.tsx`, since it's no longer tutorial-only): copy
  changes from "Whole tutorial PDF import" / "Upload Completed Tutorial PDF" /
  etc. to kind-neutral wording. Per-question tier badge (`SymPy-verified` /
  `AI-graded`) replaces the current red "problems" text for math-parse
  failures specifically; genuine blocking problems (empty label/prompt, actual
  self-contradiction) still render as errors and still disable Confirm.
- Question bank / Workbench question editor: same tier badge, plus the
  override control (a small dropdown: "Verified" / "AI-graded" / "Auto
  (currently: ...)"), since overriding is a durable editorial decision that
  belongs with the saved question, not the transient import screen.
- Submission review/marking screens: a small badge next to marks/feedback when
  the underlying question's effective tier is `ai_graded`, so instructors
  reviewing a mark know there's no SymPy cross-check behind it.

## Testing

- `tests/test_authoring.py`: add cases — (a) a question with one unparseable
  step now saves with `verification_tier == "ai_graded"` and no blocking
  problems from that step; (b) a question where every step parses but the
  chain doesn't self-verify still raises a blocking problem, unchanged from
  today; (c) existing tests asserting today's blocking behavior for
  unparseable steps are updated to assert the new tiering behavior instead.
- `tests/test_seed_integrity.py`: unchanged — all seeded quadratics still
  fully parse and self-verify, so they remain `verified` with zero behavior
  change.
- New backend test: `confirm_solutions` succeeds end-to-end for a solutions
  PDF containing non-algebraic content, producing `ai_graded` questions.
- New backend test: whole-PDF import endpoints accept `kind="ca"` and
  `kind="exam"` assignments.
- `frontend/tests/tutorial-import.test.tsx`: update/rename as needed; add a
  case asserting the tier badge renders instead of a blocking error for
  non-algebraic content, and a case for a non-tutorial assignment kind.

## Open items carried to later phases (not blocking Phase 1)

- Phase 2: broader algebra/trig/exponential-log equation support (extends
  `verifier.py`'s solve-based model without changing its shape).
- Phase 3: calculus via expression-equivalence (`sympy.diff`/`integrate`/
  `simplify`) — a different comparison model than solution-set equality, needs
  its own verifier module.
- Phase 4: numeric/computational tier for probability & stats questions with a
  single computable correct answer.
- Each of these should, over time, shrink how much content ends up in
  `ai_graded` by giving it a real deterministic check instead.
