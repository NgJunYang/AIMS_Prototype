"""Whole-document workflow with real synthetic PDF bytes and mocked Claude."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import ingestion_api, main, store, tutorial_ingestion as ingestion, uploads
from app.ingestion_models import (
    AnswerDetection, ExtractedQuestion, MappedWorking, QuestionDetection, QuestionDraft,
)
from app.models import IdentityExtraction, Question
from tests.test_api import isolate_disk_writes, _stub_llm
from tests.test_uploads import _pdf_bytes

client = TestClient(main.app)
FIXTURES = Path(__file__).resolve().parents[1] / "test_fixtures" / "tutorial_5"
EQUATIONS = ["x + 7 = 19", "x^2 - 5x + 6 = 0", "2x^2 - 8x = 0", "x^2 = 49", "x^2 + x - 12 = 0"]
SOLUTIONS = [
    [EQUATIONS[0], "x = 19 - 7", "x = 12"],
    [EQUATIONS[1], "(x - 2)(x - 3) = 0", "x = 2, x = 3"],
    [EQUATIONS[2], "2x(x - 4) = 0", "x = 0, x = 4"],
    [EQUATIONS[3], r"x = \pm\sqrt{49}", "x = 7, x = -7"],
    [EQUATIONS[4], "(x + 4)(x - 3) = 0", "x = -4, x = 3"],
]
WORKING = [SOLUTIONS[0], SOLUTIONS[1], [EQUATIONS[2], "x - 4 = 0", "x = 4"],
           [EQUATIONS[3], "x = 7"], [EQUATIONS[4], "(x + 3)(x - 4) = 0", "x = -3, x = 4"]]


@pytest.fixture(autouse=True)
def isolated_imports(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "IMPORTS_DIR", tmp_path / "imports")
    def unexpected(**kwargs):
        pytest.fail("Automated ingestion tests must mock Claude")
    monkeypatch.setattr(ingestion, "complete_json", unexpected)


def response(monkeypatch, payload):
    calls = []
    def fake(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(payload)
    monkeypatch.setattr(ingestion, "complete_json", fake)
    return calls


def response_sequence(monkeypatch, *payloads):
    calls = []
    remaining = list(payloads)
    def fake(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(remaining.pop(0))
    monkeypatch.setattr(ingestion, "complete_json", fake)
    return calls


def upload(url, prefix, data=None):
    file = next(FIXTURES.glob(f"{prefix}_*.pdf"))
    return client.post(url, files={"file": (file.name, file.read_bytes(), "application/pdf")}, data=data or {})


def question_import(monkeypatch):
    assert client.post("/api/assignments", json={"id": "t5", "title": "Tutorial 5", "kind": "tutorial"}).status_code == 200
    calls = response(monkeypatch, {"title": "Tutorial 5", "questions": [
        {"label": f"Q{i + 1}", "prompt": f"Solve ${equation}$.", "source_pages": [1 if i < 3 else 2]}
        for i, equation in enumerate(EQUATIONS)]})
    result = upload("/api/assignments/t5/imports/questions", "01")
    assert result.status_code == 200, result.text
    assert len(calls) == 1 and len(calls[0]["images_b64"]) == 2
    return result.json()


def confirm_questions(draft):
    result = client.post(f"/api/tutorial-imports/{draft['id']}/confirm-questions", json={"revision": draft["revision"], "questions": draft["questions"]})
    assert result.status_code == 200, result.text
    return result.json()


def working_rows(draft, solutions=True):
    return [{"label": q["label"], "question_id": q["question_id"], "source_pages": [1 if i < 2 else 2 if i < 4 else 3] if solutions else [1 if i < 3 else 2],
             "steps": [{"index": j + 1, "latex": latex} for j, latex in enumerate((SOLUTIONS if solutions else WORKING)[i])],
             "criteria": [{"id": "C1", "max": 4, "description": "Valid working and all roots"}] if solutions else []}
            for i, q in enumerate(draft["questions"])]


def solution_import(monkeypatch, draft):
    calls = response(monkeypatch, {"solutions": working_rows(draft)})
    result = upload(f"/api/tutorial-imports/{draft['id']}/solutions", "02", {"revision": draft["revision"]})
    assert result.status_code == 200, result.text
    assert len(calls) == 1 and len(calls[0]["images_b64"]) == 3
    return result.json()


def confirm_solutions(draft):
    body = {"revision": draft["revision"], "questions": draft["questions"], "solutions": draft["solutions"]}
    for solution in body["solutions"]:
        solution["confirmed"] = True
    return client.post(f"/api/tutorial-imports/{draft['id']}/confirm-solutions", json=body)


def setup_tutorial(monkeypatch):
    draft = solution_import(monkeypatch, confirm_questions(question_import(monkeypatch)))
    result = confirm_solutions(draft)
    assert result.status_code == 200, result.text
    return result.json()


def student_import(monkeypatch, setup, rows=None):
    calls = response(monkeypatch, {"identity": {"name": "Alex Tan", "student_id": "2500123", "confidence": "high"},
                                  "answers": rows if rows is not None else working_rows(setup, False)})
    result = upload("/api/assignments/t5/imports/student", "03")
    assert result.status_code == 200, result.text
    assert len(calls) == 1 and len(calls[0]["images_b64"]) == 2
    # Only prompts/labels are supplied to the student transcriber, never answers.
    assert "model_solution_steps" not in calls[0]["prompt"]
    return result.json()


def student_payload(setup, rows=None):
    return {"identity": {"name": "Alex Tan", "student_id": "2500123", "confidence": "high"},
            "answers": rows if rows is not None else working_rows(setup, False), "warnings": []}


def confirm_answers(draft):
    return client.post(f"/api/tutorial-imports/{draft['id']}/confirm-answers", json={
        "revision": draft["revision"], "identity": draft["identity"], "answers": draft["answers"]})


def test_real_fixture_end_to_end_reuses_mark_review_and_group_publication(monkeypatch):
    original_hashes = {p: p.read_bytes() for p in FIXTURES.glob("*.pdf")}
    setup = setup_tutorial(monkeypatch)
    assert store.load_assignment("t5").question_ids == [q["question_id"] for q in setup["questions"]]
    draft = student_import(monkeypatch, setup)
    assert not store.list_submissions()
    created = confirm_answers(draft)
    assert created.status_code == 200, created.text
    ids = created.json()["submission_ids"]
    for sid, question in zip(ids, setup["questions"]):
        submission = store.load_submission(sid)
        assert submission.student_pseudonym == "Alex Tan" and submission.student_id == "2500123"
        assert submission.assignment_id == "t5" and submission.question_id == question["question_id"]
        assert submission.marks is None and not submission.reviewed and not submission.published
        assert submission.source_import_id == draft["id"]
        assert client.get(f"/api/submissions/{sid}/student-view").status_code == 403
    _stub_llm(monkeypatch)
    settings = {"variation": "focused", "custom_instructions": "Use simple hints.", "reveal_full_solution": False}
    assert client.put("/api/assignments/t5/feedback-settings", json=settings).status_code == 200
    result = client.post(f"/api/tutorial-imports/{draft['id']}/mark")
    assert result.status_code == 200 and result.json()["complete"]
    assert all(store.load_submission(sid).feedback_settings_used.model_dump() == settings for sid in ids)
    reports = [store.load_submission(sid).verification for sid in ids]
    assert [report.final_answer_correct for report in reports] == [True, True, False, False, False]
    assert reports[2].steps[1].lost_roots == ["0"]
    assert reports[3].steps[1].lost_roots == ["-7"]
    for index, sid in enumerate(ids):
        assert client.get(f"/api/submissions/{sid}/student-view").status_code == 403
        if index == 3:
            assert client.get(f"/api/submissions/{sid}/assignment-review-status").json()["reviewed_count"] == 3
            assert client.post(f"/api/submissions/{sid}/publish-assignment").status_code == 409
        assert client.post(f"/api/submissions/{sid}/override", json={"criterion_id": "C1", "proposed": 1}).status_code == 200
        assert client.post(f"/api/submissions/{sid}/review", json={"identity": {"name": "Alex Tan", "student_id": "2500123"}, "feedback": {
            "what_went_well": "Professor approved", "what_went_wrong": "Check all roots", "how_to_improve": "Factor carefully"}}).status_code == 200
    assert client.post(f"/api/submissions/{ids[0]}/publish-assignment").json()["published"] is True
    for sid in ids:
        view = client.get(f"/api/submissions/{sid}/student-view").json()
        assert view["total_proposed"] == 1 and view["feedback"]["what_went_well"] == "Professor approved"
    # Retry after success must not re-mark/invalidate already reviewed questions.
    assert client.post(f"/api/tutorial-imports/{draft['id']}/mark").json()["complete"]
    assert all(store.load_submission(sid).reviewed for sid in ids)
    assert all(p.read_bytes() == content for p, content in original_hashes.items())


def test_live_student_schema_validates_and_fixture_preserves_q1_to_q5(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    payload = student_payload(setup)
    validated = AnswerDetection.model_validate(payload)
    assert len(validated.answers) == 5

    calls = response(monkeypatch, payload)
    result = upload("/api/assignments/t5/imports/student", "03")
    assert result.status_code == 200, result.text
    draft = result.json()
    answers = {answer["label"]: answer for answer in draft["answers"]}
    assert [answer["question_id"] for answer in draft["answers"]] == [
        question["question_id"] for question in setup["questions"]
    ]
    assert "x = 0" not in " ".join(step["latex"] for step in answers["Q3"]["steps"][1:])
    assert answers["Q3"]["steps"][-1]["latex"] == "x = 4"
    assert "-7" not in " ".join(step["latex"] for step in answers["Q4"]["steps"])
    assert answers["Q4"]["steps"][-1]["latex"] == "x = 7"
    assert answers["Q5"]["steps"][1]["latex"] == "(x + 3)(x - 4) = 0"
    assert answers["Q5"]["steps"][-1]["latex"] == "x = -3, x = 4"
    assert len(calls) == 1 and len(calls[0]["images_b64"]) == 2
    assert calls[0]["cache_contract"] == ingestion.STUDENT_SUBMISSION_EXTRACTION_CONTRACT
    assert "model_solution_steps" not in calls[0]["prompt"]
    assert "rubric" not in calls[0]["prompt"].split("Confirmed question context", 1)[-1].casefold()


def test_legacy_question_paper_uses_minimal_extraction_contract_and_keeps_simple_labels(monkeypatch):
    payload = {"title": "Tutorial 5", "questions": [
        {"label": f"Q{i + 1}", "prompt": f"Solve ${equation}$.", "source_pages": [1 if i < 3 else 2]}
        for i, equation in enumerate(EQUATIONS)
    ]}
    calls = response(monkeypatch, payload)

    title, questions, warnings = ingestion.extract_tutorial_questions([b"page 1", b"page 2"])

    assert title == "Tutorial 5" and warnings == []
    assert [question.label for question in questions] == [f"Q{i}" for i in range(1, 6)]
    assert all(isinstance(question, QuestionDraft) for question in questions)
    assert all(question.verification_tier == "verified" for question in questions)
    assert all(question.verification_tier_notes == [] for question in questions)
    assert all(question.model_solution_steps == [] and question.criteria == [] for question in questions)
    assert calls[0]["cache_contract"] == ingestion.QUESTIONS_EXTRACTION_CONTRACT

    schema_text = str(calls[0]["schema"])
    assert calls[0]["schema"] == QuestionDetection.model_json_schema()
    for application_field in (
        "question_id", "variable", "topic_tag", "model_solution_steps", "criteria",
        "solution_source_pages", "solution_transcription", "problems", "verification_tier",
        "verification_tier_notes",
    ):
        assert application_field not in schema_text


def test_professor_question_paper_prompt_ignores_non_questions_and_splits_subquestions(monkeypatch):
    payload = {"title": "Discrete Mathematics", "questions": [
        {"label": "Question 1 (a)", "prompt": "Define $A$.", "source_pages": [3]},
        {"label": "Part (b)", "prompt": "Using the same $A$, prove $P$.", "source_pages": [3]},
        {"label": "Part (c)", "prompt": "Using the same $A$, find $|A|$.", "source_pages": [4]},
        {"label": "Question 2", "prompt": "Evaluate the proposition.", "source_pages": [5]},
        {"label": "Question 3(a)", "prompt": "Draw the graph.", "source_pages": [6]},
        {"label": "Question 3(b)", "prompt": "State whether it is connected.", "source_pages": [6]},
        {"label": "Question 4(a)", "prompt": "Give a recurrence.", "source_pages": [7]},
        {"label": "Question 4(b)", "prompt": "Solve the recurrence.", "source_pages": [8]},
    ]}
    calls = response(monkeypatch, payload)

    title, questions, warnings = ingestion.extract_tutorial_questions([b"page"] * 9)

    assert title == "Discrete Mathematics" and warnings == []
    assert [question.label for question in questions] == [
        "Q1(a)", "Q1(b)", "Q1(c)", "Q2", "Q3(a)", "Q3(b)", "Q4(a)", "Q4(b)",
    ]
    assert "Q1" not in [question.label for question in questions]
    assert all(1 not in question.source_pages and 2 not in question.source_pages for question in questions)
    assert all(9 not in question.source_pages for question in questions)

    prompt = calls[0]["prompt"].casefold()
    for instruction in (
        "cover pages", "blank pages", "headers", "footers", "administrative instructions",
        "formula or reference sheets", "do not invent missing questions", "subquestion",
        "duplicate parent entry", "simple standalone",
    ):
        assert instruction in prompt


def test_professor_marking_guide_maps_workings_and_rubric_before_ai_tiering(monkeypatch):
    question = QuestionDraft(
        question_id="dm-q1a", label="Q1(a)", prompt="Prove the statement by induction.", source_pages=[3],
    )
    payload = {"solutions": [{
        "label": "Question 1(a)", "question_id": "dm-q1a", "source_pages": [2, 3],
        "steps": [
            {"index": 1, "latex": r"P(1)\text{ is true}"},
            {"index": 2, "latex": r"P(k)\Rightarrow P(k+1)"},
        ],
        "criteria": [
            {"id": "C1", "max": 1, "description": "Establishes the base case"},
            {"id": "C2", "max": 3, "description": "Completes the inductive step"},
        ],
    }]}
    response(monkeypatch, payload)

    solutions, warnings = ingestion.extract_model_solutions([b"page 1", b"page 2", b"page 3"], [question])
    problems, tier, tier_notes = ingestion.solution_review(question, solutions[0])

    assert warnings == [] and solutions[0].question_id == "dm-q1a"
    assert [criterion.max for criterion in solutions[0].criteria] == [1, 3]
    assert problems == []
    assert tier == "ai_graded" and tier_notes


def test_extracted_question_rejects_application_only_fields():
    with pytest.raises(ValueError):
        ExtractedQuestion.model_validate({
            "label": "Q1", "prompt": "Answer this.", "source_pages": [1],
            "verification_tier": "ai_graded",
        })


def test_first_malformed_question_response_retries_with_correction(monkeypatch):
    valid = {"title": "Tutorial 5", "questions": [
        {"label": "Q1", "prompt": "Solve $x=1$.", "source_pages": [1]},
    ]}
    calls = response_sequence(monkeypatch, {}, valid)

    _, questions, _ = ingestion.extract_tutorial_questions([b"page"])

    assert [question.label for question in questions] == ["Q1"]
    assert len(calls) == 2
    assert "correction after invalid structured output" not in calls[0]["prompt"].casefold()
    assert "correction after invalid structured output" in calls[1]["prompt"].casefold()


def test_first_malformed_solution_response_retries_with_correction(monkeypatch):
    question = QuestionDraft(question_id="q1", label="Q1", prompt="Solve $x=1$.", source_pages=[1])
    valid = {"solutions": [{
        "label": "Q1", "question_id": "q1", "source_pages": [1],
        "steps": [{"index": 1, "latex": "x = 1"}],
        "criteria": [{"id": "C1", "max": 1, "description": "Correct answer"}],
    }]}
    calls = response_sequence(monkeypatch, {}, valid)

    solutions, _ = ingestion.extract_model_solutions([b"page"], [question])

    assert len(solutions) == 1 and solutions[0].question_id == "q1"
    assert len(calls) == 2
    assert calls[0]["cache_contract"] == ingestion.SOLUTIONS_EXTRACTION_CONTRACT
    assert "correction after invalid structured output" in calls[1]["prompt"].casefold()


def test_first_malformed_student_response_retries_once_and_then_succeeds(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    calls = response_sequence(monkeypatch, {}, student_payload(setup))
    result = upload("/api/assignments/t5/imports/student", "03")
    assert result.status_code == 200, result.text
    assert [answer["label"] for answer in result.json()["answers"]] == [f"Q{i}" for i in range(1, 6)]
    assert len(calls) == 2


@pytest.mark.parametrize(
    "payload,category",
    [({}, "malformed structured response"), ({"answers": [None]}, "schema validation")],
)
def test_two_invalid_student_responses_return_clear_502(monkeypatch, payload, category):
    setup = setup_tutorial(monkeypatch)
    before = len(store.list_imports("t5"))
    calls = response_sequence(monkeypatch, payload, payload)
    result = upload("/api/assignments/t5/imports/student", "03")
    assert result.status_code == 502
    assert category in result.json()["detail"].casefold()
    assert len(calls) == 2
    assert len(store.list_imports("t5")) == before


def test_question_drafts_are_editable_ordered_and_not_markable_yet(monkeypatch):
    draft = question_import(monkeypatch)
    assert [q["label"] for q in draft["questions"]] == [f"Q{i}" for i in range(1, 6)]
    assert store.load_assignment("t5").question_ids == []
    before = store.list_questions()
    draft["questions"][0]["prompt"] = "Professor corrected question text"
    draft["questions"] = draft["questions"][::-1]
    saved = confirm_questions(draft)
    assert saved["questions"][-1]["prompt"] == "Professor corrected question text"
    assert saved["questions"][0]["label"] == "Q5"
    assert store.list_questions() == before
    assert store.load_assignment("t5").question_ids == []


@pytest.mark.parametrize("kind", ["ca", "exam"])
def test_whole_pdf_import_is_allowed_for_ca_and_exam_assignments(monkeypatch, kind):
    assert client.post("/api/assignments", json={"id": "g1", "title": "Graded CA 1", "kind": kind}).status_code == 200
    calls = response(monkeypatch, {"title": "Graded CA 1", "questions": [
        {"label": f"Q{i + 1}", "prompt": f"Solve ${equation}$.", "source_pages": [1 if i < 3 else 2]}
        for i, equation in enumerate(EQUATIONS)]})
    result = upload("/api/assignments/g1/imports/questions", "01")
    assert result.status_code == 200, result.text
    assert len(calls) == 1


@pytest.mark.parametrize("label,expected", [("Q1", "Q1"), ("Question 1", "Q1"), ("1.", "Q1"), ("1)", "Q1"),
    ("Q2(a)", "Q2(a)"), ("2(a)", "Q2(a)"), ("2b", "Q2(b)"), ("Part (a)", "Q2(a)")])
def test_common_labels(label, expected):
    assert ingestion.normalize_label(label, "Q2") == expected


@pytest.mark.parametrize("change", ["missing_label", "duplicate_label", "blank_prompt", "bad_page"])
def test_question_confirmation_rejects_invalid_drafts(monkeypatch, change):
    draft = question_import(monkeypatch)
    if change == "missing_label": draft["questions"][0]["label"] = ""
    if change == "duplicate_label": draft["questions"][0]["label"] = "Question 2"
    if change == "blank_prompt": draft["questions"][0]["prompt"] = " "
    if change == "bad_page": draft["questions"][0]["source_pages"] = [99]
    result = client.post(f"/api/tutorial-imports/{draft['id']}/confirm-questions", json={"revision": draft["revision"], "questions": draft["questions"]})
    assert result.status_code == 400
    assert store.load_assignment("t5").question_ids == []


def test_solution_errors_are_flagged_and_final_validation_stays_strict(monkeypatch):
    draft = confirm_questions(question_import(monkeypatch))
    rows = working_rows(draft)
    rows[2]["steps"] = [{"index": 1, "latex": "2x^2 - 8x = 0"}, {"index": 2, "latex": "x = 4"}]
    response(monkeypatch, {"solutions": rows})
    extracted = upload(f"/api/tutorial-imports/{draft['id']}/solutions", "02", {"revision": draft["revision"]}).json()
    assert any("loses 0" in p for p in extracted["questions"][2]["problems"])
    assert confirm_solutions(extracted).status_code == 409
    assert store.load_assignment("t5").question_ids == []
    extracted["solutions"][2]["steps"] = [{"index": i + 1, "latex": s} for i, s in enumerate(SOLUTIONS[2])]
    assert confirm_solutions(extracted).status_code == 200


def test_an_unparseable_solution_step_is_ai_graded_not_rejected(monkeypatch):
    draft = confirm_questions(question_import(monkeypatch))
    rows = working_rows(draft)
    rows[2]["steps"] = [{"index": 1, "latex": "2x^2 - 8x = 0"}, {"index": 2, "latex": "then I expanded it somehow"}]
    response(monkeypatch, {"solutions": rows})
    extracted = upload(f"/api/tutorial-imports/{draft['id']}/solutions", "02", {"revision": draft["revision"]}).json()
    assert extracted["questions"][2]["verification_tier"] == "ai_graded"
    assert not extracted["questions"][2]["problems"]
    result = confirm_solutions(extracted)
    assert result.status_code == 200, result.text
    assert store.get_question(extracted["questions"][2]["question_id"]).verification_tier == "ai_graded"


def test_ambiguous_solution_mapping_and_missing_solution_are_not_guessed(monkeypatch):
    draft = confirm_questions(question_import(monkeypatch))
    rows = working_rows(draft)
    rows[0].update(label="Unclear", question_id=None)
    rows[1].update(label="Faint label")
    response(monkeypatch, {"solutions": rows})
    extracted = upload(f"/api/tutorial-imports/{draft['id']}/solutions", "02", {"revision": draft["revision"]}).json()
    assert any(s["question_id"] is None and s["status"] == "uncertain" for s in extracted["solutions"])
    assert any(s["question_id"] == draft["questions"][0]["question_id"] and s["status"] == "not_detected" for s in extracted["solutions"])
    assert extracted["solutions"][1]["status"] == "uncertain"
    assert confirm_solutions(extracted).status_code == 409


def test_missing_rubrics_use_editable_defaults_and_require_confirmation(monkeypatch):
    draft = confirm_questions(question_import(monkeypatch))
    rows = working_rows(draft)
    rows[0]["criteria"] = []
    response(monkeypatch, {"solutions": rows})
    extracted = upload(f"/api/tutorial-imports/{draft['id']}/solutions", "02", {"revision": draft["revision"]}).json()
    assert extracted["solutions"][0]["criteria"]
    assert "Default rubric draft" in extracted["solutions"][0]["notes"]
    result = client.post(f"/api/tutorial-imports/{draft['id']}/confirm-solutions", json={"revision": extracted["revision"], "questions": extracted["questions"], "solutions": extracted["solutions"]})
    assert result.status_code == 409
    extracted["solutions"][0]["criteria"][0]["max"] = 3
    assert confirm_solutions(extracted).status_code == 200
    assert store.get_question(extracted["questions"][0]["question_id"]).criteria[0].max == 3


def test_cross_page_work_and_multiple_questions_per_page_survive_segmentation(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    rows = working_rows(setup, False)
    rows[1]["source_pages"] = [1, 2]
    draft = student_import(monkeypatch, setup, rows)
    result = confirm_answers(draft)
    assert result.status_code == 200
    submissions = [store.load_submission(sid) for sid in result.json()["submission_ids"]]
    assert submissions[0].source_pages == [1] and submissions[1].source_pages == [1, 2]
    assert submissions[1].confirmed_steps[-1].latex == SOLUTIONS[1][-1]
    assert client.get(f"/api/tutorial-imports/{draft['id']}/pages/2").headers["content-type"] == "image/png"
    assert client.get(f"/api/tutorial-imports/{draft['id']}/pages/3").status_code == 404


def test_missing_answer_is_a_confirmed_blank_submission(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    draft = student_import(monkeypatch, setup, working_rows(setup, False)[:-1])
    assert draft["answers"][-1]["status"] == "not_detected" and draft["answers"][-1]["steps"] == []
    result = confirm_answers(draft)
    assert result.status_code == 200
    blank = store.load_submission(result.json()["submission_ids"][-1])
    assert blank.confirmed_steps == [] and blank.transcription.steps == []
    assert blank.marks is None and not blank.reviewed
    assert client.post(f"/api/submissions/{blank.id}/publish-assignment").status_code == 409


def test_confirm_answers_is_the_single_student_mapping_confirmation(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    draft = student_import(monkeypatch, setup)
    assert all(not answer["confirmed"] for answer in draft["answers"])
    result = confirm_answers(draft)
    assert result.status_code == 200, result.text
    assert all(answer["confirmed"] for answer in result.json()["answers"])


def test_duplicate_import_never_overwrites_reviewed_work(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    first = student_import(monkeypatch, setup)
    assert confirm_answers(first).status_code == 200
    existing = store.list_submissions()
    existing[0].reviewed, existing[0].published = True, True
    store.save_submission(existing[0])
    duplicate = student_import(monkeypatch, setup)
    result = confirm_answers(duplicate)
    assert result.status_code == 409 and "already exist" in result.text
    assert store.list_submissions() == existing


def test_bulk_import_isolated_from_legacy_single_question_work(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    first_question = setup["questions"][0]["question_id"]
    legacy = client.post("/api/submissions", json={
        "question_id": first_question, "assignment_id": "t5", "channel": "tutorial",
        "student_pseudonym": "Alex Tan",
    })
    assert legacy.status_code == 200
    legacy_id = legacy.json()["id"]
    assert client.put(f"/api/submissions/{legacy_id}/identity", json={
        "name": "Alex Tan", "student_id": "2500123",
    }).status_code == 200

    draft = student_import(monkeypatch, setup)
    created = confirm_answers(draft)
    assert created.status_code == 200, created.text
    imported_ids = created.json()["submission_ids"]
    imported_status = client.get(
        f"/api/submissions/{imported_ids[0]}/assignment-review-status"
    ).json()
    assert [row["submission_id"] for row in imported_status["questions"]] == imported_ids
    assert all("multiple submissions" not in row["problems"] for row in imported_status["questions"])

    legacy_status = client.get(
        f"/api/submissions/{legacy_id}/assignment-review-status"
    ).json()
    assert legacy_status["questions"][0]["submission_id"] == legacy_id
    assert all(row["submission_id"] is None for row in legacy_status["questions"][1:])


def test_instructor_corrects_identity_mapping_and_transcription_before_creation(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    draft = student_import(monkeypatch, setup)
    draft["identity"] = {"name": "Corrected Alex", "student_id": "2500456"}
    draft["answers"][0]["steps"][-1]["latex"] = "x = 11"
    result = confirm_answers(draft)
    assert result.status_code == 200
    submissions = [store.load_submission(sid) for sid in result.json()["submission_ids"]]
    assert all(s.student_id == "2500456" and s.student_pseudonym == "Corrected Alex" for s in submissions)
    assert submissions[0].extracted_identity.student_id == "2500123"
    assert submissions[0].transcription.steps[-1].latex == "x = 12"
    assert submissions[0].confirmed_steps[-1].latex == "x = 11" and submissions[0].confirmed_steps[-1].edited_by_human


def test_marking_failure_retains_successes_and_retry_only_marks_incomplete(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    draft = student_import(monkeypatch, setup)
    created = confirm_answers(draft).json()
    _stub_llm(monkeypatch)
    original = main.mark_submission
    failed_id = setup["questions"][2]["question_id"]
    calls = []
    def mark(question, *args):
        calls.append(question.id)
        if question.id == failed_id: raise RuntimeError("mock provider failure")
        return original(question, *args)
    monkeypatch.setattr(main, "mark_submission", mark)
    result = client.post(f"/api/tutorial-imports/{draft['id']}/mark").json()
    assert not result["complete"] and sum(r["marked"] for r in result["results"]) == 4
    assert all(not store.load_submission(sid).published for sid in created["submission_ids"])
    calls.clear()
    def retry(question, *args):
        calls.append(question.id)
        return original(question, *args)
    monkeypatch.setattr(main, "mark_submission", retry)
    assert client.post(f"/api/tutorial-imports/{draft['id']}/mark").json()["complete"]
    assert calls == [failed_id]


def test_import_commit_rolls_back_new_files_on_failure(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    draft = student_import(monkeypatch, setup)
    original = store._replace_file
    calls = 0
    def failing(path, content):
        nonlocal calls
        calls += 1
        if calls == 3: raise OSError("simulated disk failure")
        original(path, content)
    monkeypatch.setattr(store, "_replace_file", failing)
    with pytest.raises(OSError): confirm_answers(draft)
    assert store.list_submissions() == []
    assert store.load_import(draft["id"]).stage == "answers"


def test_stale_drafts_and_changed_question_context_are_rejected(monkeypatch):
    draft = question_import(monkeypatch)
    saved = confirm_questions(draft)
    assert client.post(f"/api/tutorial-imports/{draft['id']}/confirm-questions", json={"revision": draft["revision"], "questions": draft["questions"]}).status_code == 409
    setup = solution_import(monkeypatch, saved)
    assert confirm_solutions(setup).status_code == 200
    student = student_import(monkeypatch, setup)
    question = store.get_question(setup["questions"][0]["question_id"])
    question.prompt += " Changed context."
    store.save_question(question)
    assert confirm_answers(student).status_code == 409


def test_partial_malformed_output_keeps_good_items(monkeypatch):
    response(monkeypatch, {"questions": [{"label": "Q1", "prompt": "Good question", "source_pages": [1]}, {"label": "Q2", "source_pages": "not a list"}]})
    _, questions, warnings = ingestion.extract_tutorial_questions([b"png"])
    assert questions[0].prompt == "Good question" and len(questions) == 2
    assert questions[1].confidence == "low" and warnings


def test_partial_malformed_student_answer_keeps_valid_siblings_and_safe_fields(monkeypatch, caplog):
    questions = [
        Question(id="q1", label="Q1", prompt="Solve one", model_solution_steps=[], criteria=[]),
        Question(id="q2", label="Q2", prompt="Solve two", model_solution_steps=[], criteria=[]),
    ]
    response(monkeypatch, {"answers": [
        {"label": "Q1", "question_id": "q1", "source_pages": [1],
         "steps": [{"index": 1, "latex": "x = 1"}]},
        {"label": "Q2", "question_id": "q2", "source_pages": "page one",
         "steps": [{"index": 1, "latex": "x = 2"}]},
    ]})
    _, answers, warnings = ingestion.segment_student_tutorial([b"png"], questions)
    by_label = {answer.label: answer for answer in answers}
    assert by_label["Q1"].steps[0].latex == "x = 1"
    assert by_label["Q2"].steps[0].latex == "x = 2"
    assert by_label["Q2"].question_id == "q2"
    assert by_label["Q2"].source_pages == [] and by_label["Q2"].confidence == "low"
    assert "manual correction" in by_label["Q2"].notes.casefold()
    assert warnings
    assert "answers.1.source_pages" in caplog.text
    assert "page one" not in caplog.text


@pytest.mark.parametrize("payload", [{}, {"questions": "prose"}, {"questions": [None] * 101}])
def test_malformed_root_output_returns_useful_error(monkeypatch, payload):
    client.post("/api/assignments", json={"id": "t5", "title": "Tutorial 5"})
    calls = response(monkeypatch, payload)
    assert upload("/api/assignments/t5/imports/questions", "01").status_code == 502
    assert len(calls) == 2
    assert store.list_imports("t5") == []


def test_two_invalid_solution_responses_do_not_mutate_or_partially_save_the_draft(monkeypatch):
    draft = confirm_questions(question_import(monkeypatch))
    before = store.load_import(draft["id"]).model_dump()
    calls = response_sequence(monkeypatch, {}, {})

    result = upload(f"/api/tutorial-imports/{draft['id']}/solutions", "02", {"revision": draft["revision"]})

    assert result.status_code == 502
    assert len(calls) == 2
    assert store.load_import(draft["id"]).model_dump() == before


@pytest.mark.parametrize("raw", [b"not PDF", b"%PDF-invalid", b"", b"x" * (uploads.MAX_DOCUMENT_BYTES + 1)], ids=["not-pdf", "corrupt", "empty", "oversized"])
def test_invalid_or_oversized_pdf_rejected_before_claude(raw):
    client.post("/api/assignments", json={"id": "t5", "title": "Tutorial 5"})
    result = client.post("/api/assignments/t5/imports/questions", files={"file": ("bad.pdf", raw, "application/pdf")})
    assert result.status_code == 400


def test_document_page_limit_and_encryption():
    with pytest.raises(uploads.UnsupportedUpload, match="20-page"):
        uploads.render_document(_pdf_bytes(21))
    import fitz
    with fitz.open() as doc:
        doc.new_page()
        encrypted = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    with pytest.raises(uploads.UnsupportedUpload, match="Encrypted"):
        uploads.render_document(encrypted)


def test_model_cannot_confirm_mappings_or_invent_source_page_numbers(monkeypatch):
    response(monkeypatch, {"answers": [{"label": "Q1", "question_id": "q1", "source_pages": [5], "confirmed": True,
                                       "steps": [{"index": 9, "latex": "x = 1"}]}]})
    _, answers, _ = ingestion.segment_student_tutorial([b"png"], [Question(id="q1", label="Q1", prompt="Solve", model_solution_steps=[], criteria=[])])
    assert not answers[0].confirmed and answers[0].status == "uncertain" and answers[0].source_pages == []
    assert answers[0].steps[0].index == 1


def test_empty_pdf_and_rendered_image_budget_are_rejected(monkeypatch):
    empty_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
    with pytest.raises(uploads.UnsupportedUpload, match="no pages"):
        uploads.render_document(empty_pdf)
    monkeypatch.setattr(uploads, "MAX_RENDERED_BYTES", 1)
    with pytest.raises(uploads.UnsupportedUpload, match="image budget"):
        uploads.render_document(_pdf_bytes())


@pytest.mark.parametrize("offline", [False, True])
def test_provider_errors_do_not_create_imports(monkeypatch, offline):
    from anthropic import AnthropicError
    from app.llm import OfflineCacheMiss
    client.post("/api/assignments", json={"id": "t5", "title": "Tutorial 5"})
    calls = 0
    def failure(**kwargs):
        nonlocal calls
        calls += 1
        raise OfflineCacheMiss("not cached") if offline else AnthropicError("private provider details")
    monkeypatch.setattr(ingestion, "complete_json", failure)
    result = upload("/api/assignments/t5/imports/questions", "01")
    assert result.status_code == (503 if offline else 502)
    assert calls == 1
    assert "private provider details" not in result.text
    assert store.list_imports("t5") == []


def test_question_bank_and_assignment_roll_back_together(monkeypatch):
    draft = solution_import(monkeypatch, confirm_questions(question_import(monkeypatch)))
    before = store.list_questions()
    original = store._replace_file
    failed = False
    def fail_assignment(path, content):
        nonlocal failed
        if path.parent == store.ASSIGNMENTS_DIR and not failed:
            failed = True
            raise OSError("simulated assignment write failure")
        original(path, content)
    monkeypatch.setattr(store, "_replace_file", fail_assignment)
    with pytest.raises(OSError): confirm_solutions(draft)
    assert store.list_questions() == before
    assert store.load_assignment("t5").question_ids == []
    assert store.load_import(draft["id"]).stage == "solutions"


def test_marking_requires_confirmed_segmentation(monkeypatch):
    setup = setup_tutorial(monkeypatch)
    draft = student_import(monkeypatch, setup)
    assert client.post(f"/api/tutorial-imports/{draft['id']}/mark").status_code == 409
    assert store.list_submissions() == []


def test_ca_submissions_imported_via_whole_pdf_use_individual_publication(monkeypatch):
    """A CA/exam assignment's whole-PDF-imported submissions must reach the
    channel the rest of the app expects (test, not tutorial), or they can
    never be published through either the individual or group publish path.
    """
    assert client.post("/api/assignments", json={"id": "g2", "title": "Graded CA 2", "kind": "ca"}).status_code == 200
    response(monkeypatch, {"title": "Graded CA 2", "questions": [
        {"label": f"Q{i + 1}", "prompt": f"Solve ${equation}$.", "source_pages": [1 if i < 3 else 2]}
        for i, equation in enumerate(EQUATIONS)]})
    draft = upload("/api/assignments/g2/imports/questions", "01").json()
    draft = confirm_questions(draft)
    response(monkeypatch, {"solutions": working_rows(draft)})
    draft = upload(f"/api/tutorial-imports/{draft['id']}/solutions", "02", {"revision": draft["revision"]}).json()
    result = confirm_solutions(draft)
    assert result.status_code == 200, result.text
    setup = result.json()

    response(monkeypatch, student_payload(setup))
    draft = upload("/api/assignments/g2/imports/student", "03").json()
    answered = client.post(f"/api/tutorial-imports/{draft['id']}/confirm-answers", json={
        "revision": draft["revision"], "identity": draft["identity"], "answers": draft["answers"]})
    assert answered.status_code == 200, answered.text
    submission_ids = answered.json()["submission_ids"]
    assert all(store.load_submission(sid).channel == "test" for sid in submission_ids)

    _stub_llm(monkeypatch)
    mark_result = client.post(f"/api/tutorial-imports/{draft['id']}/mark")
    assert mark_result.status_code == 200 and mark_result.json()["complete"]
    for sid in submission_ids:
        assert client.post(f"/api/submissions/{sid}/review", json={
            "identity": {"name": "Alex Tan", "student_id": "2500123"},
            "feedback": {"what_went_well": "Good", "what_went_wrong": "Check roots", "how_to_improve": "Factor carefully"},
        }).status_code == 200
        assert client.post(f"/api/submissions/{sid}/publish").status_code == 200
        assert store.load_submission(sid).published is True
