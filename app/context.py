"""Deterministic keyed retrieval.

There is no vector store and no similarity search. The entire retrievable
corpus is under two thousand tokens, so exact lookup by question id and
misconception tag is both simpler and strictly more accurate than approximate
retrieval would be.
"""

from app.models import Question
from app.store import get_misconception, get_notes


def assemble(question: Question, misconception_tags: list[str], *, include_model_solution: bool = True) -> str:
    """Build shared references; hints-only feedback omits answer-bearing prose."""
    parts: list[str] = []

    parts.append("## Question\n" + question.prompt)

    if include_model_solution:
        parts.append(
            "## Model solution (one valid route; other valid methods are acceptable)\n"
            + "\n".join(
                f"{i}. {latex}" for i, latex in enumerate(question.model_solution_steps, 1)
            )
        )

    # Rubric descriptions may themselves contain a worked answer.
    if include_model_solution:
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
                (f"- {entry['name']} (`{entry['tag']}`): {entry['why_students_do_it']}\n"
                f"  Suggested phrasing: {entry['feedback_template']}\n"
                f"  Reference: {entry['remediation_reference']}" if include_model_solution
                 else f"- {entry['name']} (`{entry['tag']}`)")
                for entry in entries
            )
        )

    notes = get_notes(question.topic_tag)
    if notes:
        parts.append(
            "## Course notes available to cite\n"
            + "\n".join(f"- {note['title']}: {note['body']}" if include_model_solution
                        else f"- {note['title']}" for note in notes)
        )

    return "\n\n".join(parts)
