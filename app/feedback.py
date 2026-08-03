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
