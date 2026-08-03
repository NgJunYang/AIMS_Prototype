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
