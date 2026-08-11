"""Handwritten image -> ordered LaTeX steps.

This module is deliberately ignorant of the question, the model solution and
the rubric. Its only job is to report what is written on the page, including
the mistakes.

It knows only whose page it is looking at, and only so it can be told what
*not* to assume about it. Neither prompt is ever given the answer, and neither
is ever told the page is correct - least of all the lecturer's own. See
_MODEL_SOLUTION_FRAMING for why that matters more than it might appear.
"""

from typing import Literal

from app.config import VISION_MODEL
from app.llm import complete_json
from app.models import IdentityExtraction, Step, Transcription

Source = Literal["student", "model_solution"]

_STEP_PROPERTIES = {
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
}

# Model solution photos carry no student identity to extract - this schema is
# also used for `Question.solution_transcription`, which has no field for it.
_BASE_SCHEMA = {
    "type": "object",
    "properties": _STEP_PROPERTIES,
    "required": ["steps", "notes"],
}

# Student submissions only: the same photo the student wrote their working on
# often has their name and/or student id at the top, so one vision call
# reports both rather than paying for a second call over the same image.
_STUDENT_SCHEMA = {
    "type": "object",
    "properties": {
        **_STEP_PROPERTIES,
        "student_name": {
            "type": ["string", "null"],
            "description": "The student's name exactly as handwritten on the page, or null if no name is visible or it cannot be read with confidence.",
        },
        "student_id": {
            "type": ["string", "null"],
            "description": "The student id exactly as handwritten on the page, or null if none is visible or it cannot be read with confidence.",
        },
        "identity_confidence": {
            "type": "string",
            "enum": ["high", "low"],
            "description": "low if student_name or student_id is uncertain, illegible, or absent.",
        },
    },
    "required": ["steps", "notes", "student_name", "student_id", "identity_confidence"],
}


_STUDENT_FRAMING = (
    "You are transcribing a photograph of a student's handwritten mathematics.\n"
    "\n"
    "The same page may also carry the student's name and/or student id, "
    "usually near the top or in a margin. Report them exactly as handwritten "
    "in student_name / student_id. If neither is visible, or you cannot read "
    "one with confidence, report it as null rather than guessing - a wrong "
    "name misattributes this work to the wrong student, which is worse than "
    "leaving the field blank. Set identity_confidence to \"low\" whenever "
    "either field is uncertain, illegible, or absent."
)

# The "transcribe exactly, do not correct" rule matters MORE here than on a
# student's page, not less. If the vision model silently repairs an error on the
# lecturer's own page, validate_question() sees a sound solution, passes it, and
# the lecturer never learns their worked solution was wrong - and then every
# student in the cohort is marked against it. Faithful transcription is the only
# thing that puts the mistake in front of SymPy, which is the only thing that
# can catch it.
#
# So this framing deliberately refuses to tell the model the page is correct.
# Naming it an expert's model solution would be an authority cue, and an
# authority cue is exactly what makes a vision model tidy up an inconsistency
# instead of reporting it.
_MODEL_SOLUTION_FRAMING = (
    "You are transcribing a photograph of a lecturer's own handwritten worked "
    "solution to a mathematics problem.\n"
    "\n"
    "This page is NOT authoritative and you must not treat it as correct. It "
    "was written by hand, in a hurry, by a human being who makes mistakes. Any "
    "mistake on it is the most important thing you can report: this "
    "transcription is about to be checked line by line by a symbolic algebra "
    "engine, and an error you silently repair is an error that engine can no "
    "longer catch. The lecturer would then mark an entire class against working "
    "that is wrong. Report the page exactly as written and let the checker do "
    "its job."
)

_FRAMINGS: dict[str, str] = {
    "student": _STUDENT_FRAMING,
    "model_solution": _MODEL_SOLUTION_FRAMING,
}

# Shared verbatim by both framings. Kept as one constant on purpose: duplicated
# rules would drift, and the drift would be invisible.
_FIDELITY_RULES = """Your ONLY task is to report what is written on the page.

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


def build_prompt(source: Source = "student") -> str:
    """The transcription prompt for whichever kind of page this is.

    Both sources share _FIDELITY_RULES verbatim, and the default reconstructs
    the original student prompt byte for byte. That is load-bearing: the prompt
    string is hashed into llm.cache_key, so any change to it invalidates every
    warmed transcription and turns the offline demo into a 503. There is a
    sha256 test pinning it.
    """
    return f"{_FRAMINGS[source]}\n\n{_FIDELITY_RULES}"


def transcribe(
    image_b64: str, media_type: str = "image/jpeg"
) -> tuple[Transcription, IdentityExtraction]:
    """Transcribe a student's handwritten working, plus any visible identity.

    One vision call reports both: the model already sees the full page, and a
    second call over the same image to look for a name would double the cost
    per submission for no real benefit.
    """
    payload = _call(build_prompt("student"), _STUDENT_SCHEMA, image_b64, media_type)
    identity = IdentityExtraction(
        name=payload.get("student_name") or None,
        student_id=payload.get("student_id") or None,
        confidence=payload.get("identity_confidence", "high"),
    )
    return _to_transcription(payload), identity


def transcribe_model_solution(
    image_b64: str, media_type: str = "image/jpeg"
) -> Transcription:
    """Transcribe a lecturer's own worked solution.

    Same fidelity rules, different framing. A separate public function rather
    than a flag so that callers are greppable, and so `transcribe`'s signature
    stays exactly as it was for every existing stub. No identity extraction:
    this page carries no student to identify.
    """
    payload = _call(build_prompt("model_solution"), _BASE_SCHEMA, image_b64, media_type)
    return _to_transcription(payload)


def _call(
    prompt: str, schema: dict, image_b64: str, media_type: str
) -> dict:
    return complete_json(
        model=VISION_MODEL,
        prompt=prompt,
        schema=schema,
        image_b64=image_b64,
        image_media_type=media_type,
    )


def _to_transcription(payload: dict) -> Transcription:
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
