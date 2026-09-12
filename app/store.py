"""Loading seed data and persisting submissions. The only file-I/O module."""

import json
import os
import tempfile
from functools import lru_cache, wraps
from threading import RLock
from typing import Any

from app.config import ASSIGNMENTS_DIR, IMPORTS_DIR, QUESTIONS_FILE, SEEDS_DIR, SUBMISSIONS_DIR
from app.ingestion_models import TutorialImport
from app.models import Assignment, Question, Submission


# The JSON store runs in one server process. Serialize assessment transactions
# so a concurrent edit cannot race final publication or a student-facing read.
submission_lock = RLock()


def submission_transaction(function):
    @wraps(function)
    def locked(*args, **kwargs):
        with submission_lock:
            return function(*args, **kwargs)
    return locked


@lru_cache(maxsize=1)
def _seeded_questions() -> dict[str, Question]:
    raw = json.loads((SEEDS_DIR / "questions.json").read_text(encoding="utf-8"))
    return {item["id"]: Question.model_validate(item) for item in raw}


def _overlay() -> dict:
    """Lecturer edits, layered over the seeded bank.

    Deliberately not cached: it changes at runtime whenever a lecturer saves,
    and a stale question bank is far more confusing than one extra file read.
    """
    if not QUESTIONS_FILE.exists():
        return {"questions": {}, "deleted": []}
    try:
        raw = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"questions": {}, "deleted": []}
    return {
        "questions": raw.get("questions", {}),
        "deleted": raw.get("deleted", []),
    }


def _write_overlay(overlay: dict) -> None:
    QUESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUESTIONS_FILE.write_text(json.dumps(overlay, indent=2), encoding="utf-8")


def _questions() -> dict[str, Question]:
    """The seeded bank with lecturer additions, edits and deletions applied."""
    merged = dict(_seeded_questions())
    overlay = _overlay()

    for question_id in overlay["deleted"]:
        merged.pop(question_id, None)

    for question_id, item in overlay["questions"].items():
        try:
            merged[question_id] = Question.model_validate(item)
        except ValueError:
            continue  # a hand-corrupted entry must not break the whole bank

    return merged


def is_seeded_question(question_id: str) -> bool:
    return question_id in _seeded_questions()


def save_question(question: Question) -> None:
    """Create or update a question. Editing a seeded one writes an override."""
    overlay = _overlay()
    overlay["questions"][question.id] = question.model_dump()
    overlay["deleted"] = [i for i in overlay["deleted"] if i != question.id]
    _write_overlay(overlay)


def delete_question(question_id: str) -> None:
    """Remove a question. A seeded one gets a tombstone rather than an edit to
    the seed file, so the shipped bank stays exactly as committed."""
    overlay = _overlay()
    overlay["questions"].pop(question_id, None)
    if is_seeded_question(question_id) and question_id not in overlay["deleted"]:
        overlay["deleted"].append(question_id)
    _write_overlay(overlay)


@lru_cache(maxsize=1)
def _misconceptions() -> dict[str, dict[str, Any]]:
    return json.loads((SEEDS_DIR / "misconceptions.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _notes() -> dict[str, list[dict[str, str]]]:
    return json.loads((SEEDS_DIR / "notes.json").read_text(encoding="utf-8"))


def list_questions() -> list[Question]:
    return list(_questions().values())


def get_question(question_id: str) -> Question:
    try:
        return _questions()[question_id]
    except KeyError as error:
        raise KeyError(f"unknown question id: {question_id}") from error


def get_misconception(tag: str) -> dict[str, Any]:
    return _misconceptions().get(tag, {})


def all_misconceptions() -> dict[str, dict[str, Any]]:
    return _misconceptions()


def get_notes(topic_tag: str) -> list[dict[str, str]]:
    return _notes().get(topic_tag, [])


def save_submission(submission: Submission) -> None:
    path = SUBMISSIONS_DIR / f"{submission.id}.json"
    _replace_submission_file(path, submission.model_dump_json(indent=2))


def _replace_submission_file(path, content: str) -> None:
    _replace_file(path, content.encode("utf-8"))


def _replace_file(path, content: bytes) -> None:
    # Readers never see a truncated JSON file during a write.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@submission_transaction
def save_submissions(submissions: list[Submission]) -> None:
    """Persist a validated group; restore its previous files if a write fails.

    Student access also checks the entire group, failing closed if a process
    stops between file replacements. This is not a multi-process database.
    """
    previous = {
        s.id: (SUBMISSIONS_DIR / f"{s.id}.json").read_text(encoding="utf-8")
        for s in submissions
    }
    try:
        for submission in submissions:
            save_submission(submission)
    except OSError:
        for submission_id, content in previous.items():
            _replace_submission_file(SUBMISSIONS_DIR / f"{submission_id}.json", content)
        raise


def load_submission(submission_id: str) -> Submission:
    path = SUBMISSIONS_DIR / f"{submission_id}.json"
    if not path.exists():
        raise KeyError(f"unknown submission id: {submission_id}")
    return Submission.model_validate_json(path.read_text(encoding="utf-8"))


def list_submissions() -> list[Submission]:
    """Every submission currently on disk, in stable filename order.

    A file that fails to parse is skipped rather than raised. This directory
    is written to live by the running server, so a half-flushed or
    hand-edited file is a normal transient state; one bad file must not take
    the whole cohort view down.
    """
    submissions: list[Submission] = []
    for path in sorted(SUBMISSIONS_DIR.glob("*.json")):
        try:
            submissions.append(
                Submission.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError):
            # ValueError covers both json.JSONDecodeError and pydantic's
            # ValidationError, which both subclass it.
            continue
    return submissions


# ---------- assignments ----------


def save_assignment(assignment: Assignment) -> None:
    path = ASSIGNMENTS_DIR / f"{assignment.id}.json"
    _replace_file(path, assignment.model_dump_json(indent=2).encode())


def load_assignment(assignment_id: str) -> Assignment:
    path = ASSIGNMENTS_DIR / f"{assignment_id}.json"
    if not path.exists():
        raise KeyError(f"unknown assignment id: {assignment_id}")
    return Assignment.model_validate_json(path.read_text(encoding="utf-8"))


def delete_assignment(assignment_id: str) -> None:
    (ASSIGNMENTS_DIR / f"{assignment_id}.json").unlink(missing_ok=True)


def list_assignments() -> list[Assignment]:
    """Every assignment on disk, newest first. A bad file is skipped, not fatal."""
    assignments: list[Assignment] = []
    for path in sorted(ASSIGNMENTS_DIR.glob("*.json")):
        try:
            assignments.append(
                Assignment.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError):
            continue
    return sorted(assignments, key=lambda a: a.created_at, reverse=True)


@submission_transaction
def _atomic_files(files: dict) -> None:
    """Commit related import files; roll back both new and existing records."""
    previous = {path: path.read_bytes() if path.exists() else None for path in files}
    written = []
    try:
        for path, content in files.items():
            _replace_file(path, content)
            written.append(path)
    except OSError:
        for path in reversed(written):
            if previous[path] is None:
                path.unlink(missing_ok=True)
            else:
                _replace_file(path, previous[path])
        raise


def _import_path(import_id: str):
    import re
    if not re.fullmatch(r"[0-9a-f]{12}", import_id):
        raise KeyError("unknown tutorial import")
    return IMPORTS_DIR / import_id


def save_import(draft: TutorialImport, pages: list[bytes] | None = None,
                solution_pages: list[bytes] | None = None) -> None:
    folder = _import_path(draft.id)
    files = {folder / "draft.json": draft.model_dump_json(indent=2).encode()}
    for prefix, images in [("page", pages), ("solution", solution_pages)]:
        for number, png in enumerate(images or [], start=1):
            files[folder / f"{prefix}-{number}.png"] = png
    _atomic_files(files)


def load_import(import_id: str) -> TutorialImport:
    path = _import_path(import_id) / "draft.json"
    if not path.is_file():
        raise KeyError("unknown tutorial import")
    return TutorialImport.model_validate_json(path.read_text(encoding="utf-8"))


def list_imports(assignment_id: str) -> list[TutorialImport]:
    imports = []
    for path in sorted(IMPORTS_DIR.glob("*/draft.json")):
        try:
            draft = TutorialImport.model_validate_json(path.read_text(encoding="utf-8"))
            if draft.assignment_id == assignment_id:
                imports.append(draft)
        except (OSError, ValueError):
            continue
    return imports


def import_page_path(import_id: str, page: int, *, solution: bool = False):
    draft = load_import(import_id)
    if page < 1 or page > (draft.solution_page_count if solution else draft.page_count):
        raise KeyError("unknown import page")
    path = _import_path(import_id) / f"{'solution' if solution else 'page'}-{page}.png"
    if not path.is_file():
        raise KeyError("unknown import page")
    return path


@submission_transaction
def commit_tutorial_questions(draft: TutorialImport, questions: list[Question], assignment: Assignment) -> None:
    overlay = _overlay()
    overlay["questions"].update({q.id: q.model_dump() for q in questions})
    _atomic_files({
        QUESTIONS_FILE: json.dumps(overlay, indent=2).encode(),
        ASSIGNMENTS_DIR / f"{assignment.id}.json": assignment.model_dump_json(indent=2).encode(),
        _import_path(draft.id) / "draft.json": draft.model_dump_json(indent=2).encode(),
    })


@submission_transaction
def commit_tutorial_submissions(draft: TutorialImport, submissions: list[Submission]) -> None:
    files = {SUBMISSIONS_DIR / f"{s.id}.json": s.model_dump_json(indent=2).encode() for s in submissions}
    files[_import_path(draft.id) / "draft.json"] = draft.model_dump_json(indent=2).encode()
    _atomic_files(files)
