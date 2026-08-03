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
        if verification.note:
            line += f" Note: {verification.note}"
        findings.append(line)

    if report.final_answer_verified:
        findings.append(
            f"Final answer correct: {report.final_answer_correct}. "
            f"Expected solutions: {report.model_solutions}."
        )
    else:
        findings.append(
            "The final answer could NOT be established symbolically (the last line "
            "did not parse, or the expected answer was unavailable). Judge any "
            "answer criterion from the written evidence alone, and say clearly in "
            "your justification that it was not machine-verified. Do NOT assume "
            "the answer is wrong."
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
    returned = {item.get("criterion_id"): item for item in payload.get("criteria", [])}

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

        try:
            proposed = int(item.get("proposed", 0))
        except (TypeError, ValueError):
            proposed = 0
        proposed = max(0, min(proposed, max_by_id[criterion.id]))

        criteria.append(
            CriterionMark(
                criterion_id=criterion.id,
                proposed=proposed,
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
