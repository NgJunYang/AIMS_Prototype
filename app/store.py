"""Loading seed data and persisting submissions. The only file-I/O module."""

import json
from functools import lru_cache
from typing import Any

from app.config import SEEDS_DIR, SUBMISSIONS_DIR
from app.models import Question, Submission


@lru_cache(maxsize=1)
def _questions() -> dict[str, Question]:
    raw = json.loads((SEEDS_DIR / "questions.json").read_text(encoding="utf-8"))
    return {item["id"]: Question.model_validate(item) for item in raw}


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
