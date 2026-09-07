"""The student-facing tutor: a grounded Q&A chatbot and an email drafter.

Both are strictly downstream of the verifier and the marks the lecturer has
already settled. Like `app/feedback.py`, they are handed the established facts
as a reference block and told not to re-derive or re-check any mathematics, and
never to change a mark. Nothing here asserts mathematical truth.

No mail is ever sent. `draft_email` returns text for the student to read, edit
and send themselves.
"""

from app.config import TUTOR_MODEL
from app.context import assemble
from app.llm import complete_json
from app.models import (
    Feedback,
    MarkProposal,
    Question,
    Step,
    VerificationReport,
)

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}

_EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["subject", "body"],
}


def _grounding(
    question: Question,
    steps: list[Step],
    marks: MarkProposal,
    feedback: Feedback,
    report: VerificationReport,
) -> str:
    reference = assemble(question, marks.misconceptions)
    student_work = "\n".join(f"Step {s.index}: {s.latex}" for s in steps) or "(no steps)"
    mark_lines = "\n".join(
        f"- {c.criterion_id}: {c.proposed}/{c.max} — {c.justification}"
        for c in marks.criteria
    )
    diverged = [
        f"Step {s.index}: {s.divergence} ({s.note})"
        for s in report.steps
        if s.equivalent_to_previous is False
    ]
    return f"""{reference}

## The student's working
{student_work}

## Marks already decided (do not change these)
{mark_lines}
Total: {marks.total_proposed}/{marks.total_max}.
Final answer correct: {report.final_answer_correct}. Answer established: {report.final_answer_verified}.
Symbolic checks that failed: {"; ".join(diverged) or "none"}.

## Feedback already given to the student
What went well: {feedback.what_went_well}
What went wrong: {feedback.what_went_wrong}
How to improve: {feedback.how_to_improve}"""


def answer(
    question: Question,
    steps: list[Step],
    marks: MarkProposal,
    feedback: Feedback,
    report: VerificationReport,
    messages: list[dict],
) -> str:
    """Answer the student's latest question about their own marked work."""
    transcript = "\n".join(
        f"{'Student' if m.get('role') == 'user' else 'Tutor'}: {m.get('content', '')}"
        for m in messages
    )
    prompt = f"""You are a maths tutor helping a student understand feedback on
their own handwritten working. Everything you need is below.

{_grounding(question, steps, marks, feedback, report)}

## Conversation so far
{transcript}

## Your task
Answer the student's most recent message.

Rules:
- Address the student directly, in the second person. Warm, plain, specific.
- Ground every claim in the working, marks and checks above. Do NOT re-derive
  or re-check any mathematics, do NOT introduce a new mathematical claim, and
  do NOT change or question any mark. If the findings say a step is wrong, it
  is wrong; if they say the answer is correct, it is correct.
- If the student asks for a mark to be changed, explain that only their
  instructor can do that and suggest they use the "email my instructor" option.
- Point to the specific step, and to a course note by name where one fits.
- Write mathematics inline like x = 0, with no LaTeX delimiters.
- Keep it to a short paragraph or two."""

    payload = complete_json(model=TUTOR_MODEL, prompt=prompt, schema=_ANSWER_SCHEMA)
    return str(payload.get("answer", "")).strip()


def draft_email(
    question: Question,
    steps: list[Step],
    marks: MarkProposal,
    feedback: Feedback,
    report: VerificationReport,
    student_name: str,
    concern: str,
) -> dict:
    """Draft an email from the student to their instructor about this question.

    Returns {subject, body}. Nothing is sent - the student reviews, edits and
    sends it themselves.
    """
    prompt = f"""Draft a short, polite email from a student to their instructor
about one specific marked question. Return a subject line and a body.

{_grounding(question, steps, marks, feedback, report)}

## Who is writing
Student name: {student_name or "(not given - sign off as 'a student')"}

## What the student wants to raise
{concern}

## Rules
- The body opens with a greeting and closes with a sign-off using the student's
  name if given.
- State the question, the mark received ({marks.total_proposed}/{marks.total_max}),
  and the student's specific point clearly and briefly.
- Neutral, respectful tone - a question or a request to review, not a demand.
- Do NOT assert what the correct mark should be or re-argue the mathematics;
  the instructor has the full context.
- Plain text. Mathematics inline like x = 0. Four short paragraphs at most."""

    payload = complete_json(model=TUTOR_MODEL, prompt=prompt, schema=_EMAIL_SCHEMA)
    return {
        "subject": str(payload.get("subject", "")).strip(),
        "body": str(payload.get("body", "")).strip(),
    }
