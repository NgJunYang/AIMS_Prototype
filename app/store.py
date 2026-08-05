"""Loading seed data and persisting submissions. The only file-I/O module."""

import json
from functools import lru_cache
from typing import Any

from app.config import QUESTIONS_FILE, SEEDS_DIR, SUBMISSIONS_DIR
from app.models import Question, Submission


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
    path.write_text(submission.model_dump_json(indent=2), encoding="utf-8")


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
