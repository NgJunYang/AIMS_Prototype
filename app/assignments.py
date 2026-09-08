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
    """Map recognised headers; headerless files remain name-first.

    Reject ambiguous or malformed rows before replacing an existing roster.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Save the roster as a UTF-8 CSV file.") from exc
    aliases = {"name": "name", "student": "name", "student name": "name",
               "student id": "student_id", "id": "student_id"}
    entries: list[RosterEntry] = []
    columns = None
    seen_ids: set[str] = set()
    try:
        reader = csv.reader(io.StringIO(text), strict=True)
        for row in reader:
            cells = [c.strip() for c in row]
            if not any(cells):
                continue
            if columns is None:
                headers = [aliases.get(re.sub(r"[_\s-]+", " ", c.lower())) for c in cells]
                if any(headers):
                    if None in headers or headers.count("name") != 1 or headers.count("student_id") > 1:
                        raise ValueError("Use headers name,student_id (either order), or a single name column.")
                    columns = headers
                    continue
                columns = ["name", "student_id"]
            if len(cells) > len(columns):
                raise ValueError(f"Row {reader.line_num}: too many columns. Use name,student_id headers.")
            values = dict(zip(columns, cells))
            name, student_id = values.get("name", ""), values.get("student_id", "")
            if not name:
                raise ValueError(f"Row {reader.line_num}: student name is missing.")
            if student_id and student_id.casefold() in seen_ids:
                raise ValueError(f"Row {reader.line_num}: duplicate student ID {student_id}.")
            if student_id:
                seen_ids.add(student_id.casefold())
            entries.append(RosterEntry(name=name, student_id=student_id))
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV near row {reader.line_num}: {exc}.") from exc
    return entries
