"""Seed the LLM cache for the flagship typed-in demo, with no API key needed.

The full pipeline normally needs two model calls (marking, then feedback). This
script writes plausible, hand-authored responses for the q2 "divided through by
x" case straight into `fixtures/llm_cache/`, keyed exactly as `app.llm` would
key a real call. With those in place the entire flow runs under
DEMO_MODE=offline: upload nothing, type the two steps, get marks, feedback and
practice.

Two reasons this exists:

1. It lets anyone run and demo the app before an API key is available, and lets
   the frontend be exercised end to end in a browser.
2. It is a live test of the offline mechanism itself. If the demo laptop loses
   Wi-Fi at the venue, this is the code path that saves the presentation, so it
   should be exercised early and often rather than trusted.

Run:  .venv/Scripts/python.exe scripts/seed_demo_cache.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import feedback as feedback_module  # noqa: E402
from app import llm, marker  # noqa: E402
from app.config import MARKING_MODEL  # noqa: E402
from app.models import Step  # noqa: E402
from app.store import get_question  # noqa: E402
from app.verifier import verify  # noqa: E402

QUESTION_ID = "q2"
STEP_LATEX = ["x^2 = 5x", "x = 5"]

MARK_RESPONSE = {
    "criteria": [
        {
            "criterion_id": "C1",
            "proposed": 0,
            "justification": (
                "At step 2 both sides were divided by x rather than rearranged so "
                "that one side is zero, so this criterion is not met."
            ),
            "evidence_step": 2,
        },
        {
            "criterion_id": "C2",
            "proposed": 1,
            "justification": (
                "Symbolic checking shows step 2 lost the solution x = 0, so the "
                "method did not preserve the solution set. Partial credit for "
                "correctly reducing to x = 5."
            ),
            "evidence_step": 2,
        },
        {
            "criterion_id": "C3",
            "proposed": 2,
            "justification": (
                "The arithmetic that was carried out is correct: dividing 5x by x "
                "does give 5."
            ),
            "evidence_step": 2,
        },
        {
            "criterion_id": "C4",
            "proposed": 0,
            "justification": (
                "Only x = 5 is stated. The expected solutions are 0 and 5, so not "
                "all solutions were given."
            ),
            "evidence_step": 2,
        },
    ],
    "misconceptions": ["divided_by_variable_lost_root"],
}

FEEDBACK_RESPONSE = {
    "what_went_well": (
        "You spotted straight away that this equation has an x in every term and "
        "that it could be simplified, and the arithmetic you did was correct."
    ),
    "what_went_wrong": (
        "At step 2 you divided both sides by x. That is only valid when x is not "
        "zero, so it silently threw away the solution x = 0. The equation has two "
        "solutions, 0 and 5, and your answer only gives one of them."
    ),
    "how_to_improve": (
        "Move everything to one side instead of dividing: from x^2 = 5x, subtract "
        "5x to get x^2 - 5x = 0, factorise to x(x - 5) = 0, then read off both "
        "solutions. Whenever you are about to divide by something containing the "
        "unknown, stop and factorise instead."
    ),
    "references": ["Notes §2 — the zero-product principle"],
}


def main() -> None:
    question = get_question(QUESTION_ID)
    steps = [Step(index=i, latex=t) for i, t in enumerate(STEP_LATEX, start=1)]
    report = verify(steps, question.model_solution_steps, question.variable)

    print(f"Question {QUESTION_ID}: {question.prompt}")
    print(f"Student steps: {STEP_LATEX}")
    print(f"Verifier: divergence at step {report.first_divergence_index}, "
          f"misconceptions {report.candidate_misconceptions}")

    mark_prompt = marker.build_prompt(question, steps, report)
    mark_key = llm.cache_key(MARKING_MODEL, mark_prompt, None)
    llm.write_cache(mark_key, MARK_RESPONSE)
    print(f"  wrote marking response   -> fixtures/llm_cache/{mark_key}.json")

    # Build the proposal the same way the app does, so the feedback prompt (and
    # therefore its cache key) matches byte for byte at request time.
    proposal = marker.mark(question, steps, report)

    feedback_prompt = feedback_module.build_prompt(question, steps, proposal, report)
    feedback_key = llm.cache_key(MARKING_MODEL, feedback_prompt, None)
    llm.write_cache(feedback_key, FEEDBACK_RESPONSE)
    print(f"  wrote feedback response  -> fixtures/llm_cache/{feedback_key}.json")

    written = feedback_module.write(question, steps, proposal, report)

    print()
    print(f"Marks: {proposal.total_proposed}/{proposal.total_max}")
    for criterion in proposal.criteria:
        print(f"  {criterion.criterion_id}: {criterion.proposed}/{criterion.max}")
    print(f"Warnings: {proposal.warnings or 'none'}")
    print(f"Feedback opens: {written.what_went_well[:60]}...")
    print()
    print("Now run with DEMO_MODE=offline, choose q2, click 'Use a sample script',")
    print("then 'Confirm & Mark'. No API key and no network required.")


if __name__ == "__main__":
    main()
