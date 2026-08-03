from app.models import Question, Submission
from app.store import (
    get_misconception,
    get_question,
    list_questions,
    load_submission,
    save_submission,
)


def test_all_seed_questions_load_and_validate():
    questions = list_questions()
    assert len(questions) >= 6
    assert all(isinstance(q, Question) for q in questions)


def test_every_question_has_at_least_three_criteria():
    for question in list_questions():
        assert len(question.criteria) >= 3, question.id


def test_get_question_by_id():
    question = get_question("q2")
    assert "5x" in question.prompt


def test_get_missing_question_raises():
    import pytest

    with pytest.raises(KeyError):
        get_question("does-not-exist")


def test_misconception_lookup_returns_feedback_template():
    entry = get_misconception("divided_by_variable_lost_root")
    assert "zero" in entry["feedback_template"].lower()


def test_submission_round_trips_to_disk():
    submission = Submission(id="test-round-trip", question_id="q1")
    save_submission(submission)
    assert load_submission("test-round-trip").question_id == "q1"
