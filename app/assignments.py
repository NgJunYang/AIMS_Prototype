"""Assignment validation and roster CSV parsing. No LLM, no file I/O."""

import csv
import io
import re

from app.models import Assignment, RosterEntry

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def validate_assignment(assignment: Assignment, known_question_ids: set[str]) -> list[str]:
    """Everything wrong with this assignment, in plain English. Empty means sound."""
    problems: list[str] = []
    if not _ID_PATTERN.match(assignment.id or ""):
        problems.append(
            "The id must start with a letter or digit and contain only letters, "
            "digits, hyphens and underscores."
        )
    if not (assignment.title or "").strip():
        problems.append("The title cannot be empty.")
    unknown = [q for q in assignment.question_ids if q not in known_question_ids]
    if unknown:
        problems.append(f"Unknown question id(s): {', '.join(unknown)}.")
    if len(set(assignment.question_ids)) != len(assignment.question_ids):
        problems.append("The same question is listed more than once.")
    return problems


def parse_roster_csv(raw: bytes) -> list[RosterEntry]:
    """Parse a `name,student_id` CSV. Tolerates a header row and a single column.

    A blank or malformed line is skipped rather than raised - a roster paste is
    exactly the kind of input that arrives slightly untidy.
    """
    text = raw.decode("utf-8-sig", errors="replace")
    entries: list[RosterEntry] = []
    for row in csv.reader(io.StringIO(text)):
        cells = [c.strip() for c in row if c is not None]
        if not cells or not cells[0]:
            continue
        name, student_id = cells[0], (cells[1] if len(cells) > 1 else "")
        # Skip an obvious header row.
        if name.lower() in {"name", "student", "student name"} and not entries:
            continue
        entries.append(RosterEntry(name=name, student_id=student_id))
    return entries
