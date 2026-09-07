import io
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import main, store
from app.main import app
from app.models import (
    Feedback,
    IdentityExtraction,
    MarkProposal,
    CriterionMark,
    Step,
    Transcription,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_disk_writes(tmp_path, monkeypatch):
    """Keep the API tests hermetic.

    Without this, uploads land in `fixtures/images/` — which is where the real
    handwritten demo scans live — and every run leaves another submission JSON
    in `data/submissions/`. Redirecting both means the suite can be run any
    number of times without polluting the repo or the demo fixtures.
    """
    images = tmp_path / "images"
    submissions = tmp_path / "submissions"
    images.mkdir()
    submissions.mkdir()
    monkeypatch.setattr(main, "IMAGES_DIR", images)
    monkeypatch.setattr(store, "SUBMISSIONS_DIR", submissions)
    # Question authoring writes an overlay file; without this, tests would
    # add and delete questions in the developer's real bank.
    monkeypatch.setattr(store, "QUESTIONS_FILE", tmp_path / "questions.json")

# A real, byte-correct 1x1 PNG. The previous literal here had a bad IDAT
# checksum and silently worked for years because no code path ever actually
# decoded it - every test using it went straight to a mocked transcribe().
# Once app.uploads started validating uploads for real, Pillow correctly
# rejected it. Generated with PIL rather than hand-typed to avoid repeating
# the mistake: Image.new("RGB", (1, 1), (255, 0, 0)) saved as PNG.
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000"
    "907753de0000000c49444154789c63f8cfc0000003010100c9fe92ef00"
    "00000049454e44ae426082"
)


def _new_submission(question_id: str = "q2") -> str:
    response = client.post("/api/submissions", json={"question_id": question_id})
    assert response.status_code == 200
    return response.json()["id"]


def test_list_questions():
    response = client.get("/api/questions")
    assert response.status_code == 200
    assert len(response.json()) >= 6


def test_get_one_question():
    response = client.get("/api/questions/q2")
    assert response.status_code == 200
    assert response.json()["id"] == "q2"


def test_unknown_question_returns_404():
    assert client.get("/api/questions/nope").status_code == 404


def test_creating_a_submission_for_an_unknown_question_returns_404():
    response = client.post("/api/submissions", json={"question_id": "nope"})
    assert response.status_code == 404


def test_unknown_submission_returns_404():
    assert client.get("/api/submissions/does-not-exist").status_code == 404


def test_manual_entry_then_verify_finds_the_lost_root():
    """The typed-in path: no image, steps entered directly."""
    submission_id = _new_submission("q2")

    response = client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}, {"index": 2, "latex": "x = 5"}]},
    )
    assert response.status_code == 200

    verified = client.post(f"/api/submissions/{submission_id}/verify").json()
    assert verified["verification"]["first_divergence_index"] == 2
    assert verified["verification"]["steps"][1]["divergence"] == "lost_roots"
    assert verified["verification"]["steps"][1]["lost_roots"] == ["0"]


def test_steps_are_reindexed_from_one():
    submission_id = _new_submission()
    response = client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 7, "latex": "x^2 = 5x"}, {"index": 9, "latex": "x = 5"}]},
    )
    assert [s["index"] for s in response.json()["confirmed_steps"]] == [1, 2]


def test_editing_steps_invalidates_everything_downstream(monkeypatch):
    submission_id = _new_submission()
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
    )
    _stub_llm(monkeypatch)
    marked = client.post(f"/api/submissions/{submission_id}/mark").json()
    assert marked["marks"] is not None

    edited = client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 - 5x = 0"}]},
    ).json()
    assert edited["verification"] is None
    assert edited["marks"] is None
    assert edited["feedback"] is None
    assert edited["practice"] == []


def test_transcribe_endpoint_stores_the_image_and_seeds_confirmed_steps(monkeypatch):
    monkeypatch.setattr(
        main,
        "transcribe",
        lambda image_b64, media_type: (
            Transcription(
                steps=[Step(index=1, latex="x^2 = 5x", confidence="low")], notes="faint"
            ),
            IdentityExtraction(),
        ),
    )
    submission_id = _new_submission()

    response = client.post(
        f"/api/submissions/{submission_id}/transcribe",
        files={"file": ("scan.png", io.BytesIO(PNG_1X1), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transcription"]["steps"][0]["latex"] == "x^2 = 5x"
    assert body["transcription"]["notes"] == "faint"
    # confirmed_steps is seeded from the transcription so the editor has content
    assert body["confirmed_steps"][0]["latex"] == "x^2 = 5x"
    assert body["image_filename"] is not None


def _stub_llm(monkeypatch):
    """Stub the two LLM-backed stages with deterministic output."""
    monkeypatch.setattr(
        main,
        "mark_submission",
        lambda question, steps, report: MarkProposal(
            criteria=[
                CriterionMark(
                    criterion_id=c.id,
                    proposed=0,
                    max=c.max,
                    justification="stub",
                    evidence_step=1,
                )
                for c in question.criteria
            ],
            misconceptions=["divided_by_variable_lost_root"],
        ),
    )
    monkeypatch.setattr(
        main,
        "write_feedback",
        lambda question, steps, proposal, report: Feedback(
            what_went_well="a", what_went_wrong="b", how_to_improve="c", references=[]
        ),
    )


def test_mark_runs_verify_marks_feedback_and_practice(monkeypatch):
    _stub_llm(monkeypatch)
    submission_id = _new_submission()
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}, {"index": 2, "latex": "x = 5"}]},
    )

    body = client.post(f"/api/submissions/{submission_id}/mark").json()

    assert body["verification"] is not None
    assert body["marks"] is not None
    assert body["feedback"]["what_went_well"] == "a"
    assert len(body["practice"]) == 3
    # practice targets the detected misconception
    assert body["practice"][0]["misconception_tag"] == "divided_by_variable_lost_root"


def test_mark_with_no_steps_does_not_crash(monkeypatch):
    _stub_llm(monkeypatch)
    submission_id = _new_submission()
    response = client.post(f"/api/submissions/{submission_id}/mark")
    assert response.status_code == 200


def test_override_updates_the_mark_and_flags_it(monkeypatch):
    _stub_llm(monkeypatch)
    submission_id = _new_submission()
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
    )
    client.post(f"/api/submissions/{submission_id}/mark")

    body = client.post(
        f"/api/submissions/{submission_id}/override",
        json={"criterion_id": "C1", "proposed": 2},
    ).json()

    c1 = next(c for c in body["marks"]["criteria"] if c["criterion_id"] == "C1")
    assert c1["proposed"] == 2
    assert c1["overridden"] is True
    assert body["marks"]["total_proposed"] == 2


def test_override_persists_and_can_reset_to_the_latest_suggestion(monkeypatch):
    _stub_llm(monkeypatch)
    submission_id = _new_submission()
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
    )
    marked = client.post(f"/api/submissions/{submission_id}/mark").json()
    suggested = next(c["suggested"] for c in marked["marks"]["criteria"] if c["criterion_id"] == "C1")

    edited = client.post(
        f"/api/submissions/{submission_id}/override",
        json={"criterion_id": "C1", "proposed": 2},
    ).json()
    assert next(c for c in edited["marks"]["criteria"] if c["criterion_id"] == "C1")["overridden"] is True

    persisted = client.get(f"/api/submissions/{submission_id}").json()
    assert next(c for c in persisted["marks"]["criteria"] if c["criterion_id"] == "C1")["proposed"] == 2

    reset = client.post(f"/api/submissions/{submission_id}/reset-overrides").json()
    c1 = next(c for c in reset["marks"]["criteria"] if c["criterion_id"] == "C1")
    assert c1["proposed"] == suggested
    assert c1["overridden"] is False


def test_a_re_mark_keeps_manual_score_edits_but_refreshes_the_suggestion(monkeypatch):
    """Amending the transcription re-runs marking automatically in the UI. The
    model's suggestion should refresh, but an explicit override is a decision,
    not a suggestion - it must survive the re-mark."""
    _stub_llm(monkeypatch)  # every criterion suggested at 0
    submission_id = _new_submission()
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
    )
    client.post(f"/api/submissions/{submission_id}/mark")
    client.post(
        f"/api/submissions/{submission_id}/override",
        json={"criterion_id": "C1", "proposed": 1},
    )

    re_marked = client.post(f"/api/submissions/{submission_id}/mark").json()

    c1 = next(c for c in re_marked["marks"]["criteria"] if c["criterion_id"] == "C1")
    assert c1["proposed"] == 1
    assert c1["overridden"] is True
    assert c1["suggested"] == 0
    # And an untouched criterion follows the fresh suggestion.
    c2 = next(c for c in re_marked["marks"]["criteria"] if c["criterion_id"] == "C2")
    assert c2["proposed"] == 0 and c2["overridden"] is False

    reset = client.post(f"/api/submissions/{submission_id}/reset-overrides").json()
    assert next(c for c in reset["marks"]["criteria"] if c["criterion_id"] == "C1")["proposed"] == 0


def test_override_above_the_maximum_is_rejected(monkeypatch):
    _stub_llm(monkeypatch)
    submission_id = _new_submission()
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
    )
    client.post(f"/api/submissions/{submission_id}/mark")

    response = client.post(
        f"/api/submissions/{submission_id}/override",
        json={"criterion_id": "C1", "proposed": 99},
    )
    assert response.status_code == 400


def test_override_before_marking_returns_409():
    submission_id = _new_submission()
    response = client.post(
        f"/api/submissions/{submission_id}/override",
        json={"criterion_id": "C1", "proposed": 1},
    )
    assert response.status_code == 409


def test_override_unknown_criterion_returns_404(monkeypatch):
    _stub_llm(monkeypatch)
    submission_id = _new_submission()
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
    )
    client.post(f"/api/submissions/{submission_id}/mark")

    response = client.post(
        f"/api/submissions/{submission_id}/override",
        json={"criterion_id": "NOPE", "proposed": 1},
    )
    assert response.status_code == 404


def test_feedback_edit_persists_lecturer_prose(monkeypatch):
    _stub_llm(monkeypatch)
    submission_id = _new_submission()
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
    )
    client.post(f"/api/submissions/{submission_id}/mark")

    body = client.put(
        f"/api/submissions/{submission_id}/feedback",
        json={
            "what_went_well": "Clear first step.",
            "what_went_wrong": "One solution was lost.",
            "how_to_improve": "Factor before solving.",
        },
    ).json()

    assert body["feedback"]["what_went_well"] == "Clear first step."
    assert body["feedback"]["what_went_wrong"] == "One solution was lost."
    assert body["feedback"]["how_to_improve"] == "Factor before solving."


def test_feedback_edit_before_marking_returns_409():
    submission_id = _new_submission()
    response = client.put(
        f"/api/submissions/{submission_id}/feedback",
        json={
            "what_went_well": "",
            "what_went_wrong": "",
            "how_to_improve": "",
        },
    )
    assert response.status_code == 409


def _mark_a_tutorial(monkeypatch, channel: str = "tutorial") -> str:
    _stub_llm(monkeypatch)
    created = client.post(
        "/api/submissions", json={"question_id": "q2", "channel": channel}
    ).json()
    client.put(
        f"/api/submissions/{created['id']}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}, {"index": 2, "latex": "x = 5"}]},
    )
    client.post(f"/api/submissions/{created['id']}/mark")
    return created["id"]


def test_student_view_shows_final_numbers_and_feedback_without_instructor_internals(monkeypatch):
    submission_id = _mark_a_tutorial(monkeypatch)
    body = client.get(f"/api/submissions/{submission_id}/student-view").json()

    assert body["channel"] == "tutorial"
    assert body["total_max"] > 0
    assert body["feedback"]["what_went_well"] == "a"
    assert body["criteria"]
    # None of the instructor-only fields leak through.
    for criterion in body["criteria"]:
        assert set(criterion) == {"criterion_id", "proposed", "max", "justification"}


def test_student_view_before_marking_is_409():
    created = client.post("/api/submissions", json={"question_id": "q2"}).json()
    assert client.get(f"/api/submissions/{created['id']}/student-view").status_code == 409


def test_a_graded_test_script_is_hidden_until_the_instructor_publishes(monkeypatch):
    submission_id = _mark_a_tutorial(monkeypatch, channel="test")

    assert client.get(f"/api/submissions/{submission_id}/student-view").status_code == 403

    published = client.post(f"/api/submissions/{submission_id}/publish").json()
    assert published["published"] is True
    assert client.get(f"/api/submissions/{submission_id}/student-view").status_code == 200

    client.post(f"/api/submissions/{submission_id}/unpublish")
    assert client.get(f"/api/submissions/{submission_id}/student-view").status_code == 403


def test_publish_before_marking_is_409():
    created = client.post("/api/submissions", json={"question_id": "q2"}).json()
    assert client.post(f"/api/submissions/{created['id']}/publish").status_code == 409


def test_tutor_chat_is_grounded_and_returned(monkeypatch):
    submission_id = _mark_a_tutorial(monkeypatch)
    captured = {}

    def fake_answer(question, steps, marks, feedback, report, messages):
        captured["messages"] = messages
        captured["mark_total"] = marks.total_proposed
        return "Look again at step 2."

    monkeypatch.setattr(main, "tutor_answer", fake_answer)

    body = client.post(
        f"/api/submissions/{submission_id}/chat",
        json={"messages": [{"role": "user", "content": "Why did I lose a mark?"}]},
    ).json()

    assert body["answer"] == "Look again at step 2."
    assert captured["messages"][0]["content"] == "Why did I lose a mark?"


def test_tutor_chat_before_marking_is_409():
    created = client.post("/api/submissions", json={"question_id": "q2"}).json()
    response = client.post(
        f"/api/submissions/{created['id']}/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 409


def test_draft_email_returns_subject_and_body_and_sends_nothing(monkeypatch):
    submission_id = _mark_a_tutorial(monkeypatch)
    monkeypatch.setattr(
        main,
        "tutor_draft_email",
        lambda *args: {"subject": "Query about Q2", "body": "Dear instructor, ..."},
    )

    body = client.post(
        f"/api/submissions/{submission_id}/draft-email",
        json={"concern": "I think x = 0 should also count."},
    ).json()

    assert body["subject"] == "Query about Q2"
    assert body["body"].startswith("Dear instructor")


def test_offline_cache_miss_returns_503_with_a_helpful_hint(monkeypatch):
    from app.llm import OfflineCacheMiss

    def boom(image_b64, media_type):
        raise OfflineCacheMiss("no cached response for key abc")

    monkeypatch.setattr(main, "transcribe", boom)
    submission_id = _new_submission()

    response = client.post(
        f"/api/submissions/{submission_id}/transcribe",
        files={"file": ("scan.png", io.BytesIO(PNG_1X1), "image/png")},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "offline_cache_miss"
    assert "sample" in body["hint"].lower()


def test_transcribe_with_garbage_bytes_is_a_4xx_not_a_500(monkeypatch):
    def _must_not_be_called(**_):
        raise AssertionError("the LLM must never be called for unreadable bytes")

    monkeypatch.setattr(main, "transcribe", _must_not_be_called)

    submission_id = _new_submission()
    response = client.post(
        f"/api/submissions/{submission_id}/transcribe",
        files={"file": ("junk.png", io.BytesIO(b"not an image at all"), "image/png")},
    )
    assert 400 <= response.status_code < 500


def test_transcribe_with_empty_file_is_a_4xx(monkeypatch):
    submission_id = _new_submission()
    response = client.post(
        f"/api/submissions/{submission_id}/transcribe",
        files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
    )
    assert 400 <= response.status_code < 500


def test_exif_rotation_is_corrected_before_reaching_the_model(monkeypatch):
    from PIL import Image

    captured = {}

    def fake_transcribe(image_b64, media_type):
        captured["b64"] = image_b64
        captured["media_type"] = media_type
        return Transcription(steps=[], notes=""), IdentityExtraction()

    monkeypatch.setattr(main, "transcribe", fake_transcribe)

    img = Image.new("RGB", (40, 20), color=(255, 0, 0))
    buf = io.BytesIO()
    exif = img.getexif()
    exif[0x0112] = 6
    img.save(buf, format="JPEG", exif=exif)

    submission_id = _new_submission()
    response = client.post(
        f"/api/submissions/{submission_id}/transcribe",
        files={"file": ("scan.jpg", buf.getvalue(), "image/jpeg")},
    )

    assert response.status_code == 200
    import base64 as b64

    sent = Image.open(io.BytesIO(b64.b64decode(captured["b64"])))
    assert sent.size == (20, 40)
    assert captured["media_type"] == "image/png"


def test_transcribe_filename_traversal_is_neutralized(monkeypatch):
    monkeypatch.setattr(
        main,
        "transcribe",
        lambda image_b64, media_type: (Transcription(steps=[], notes=""), IdentityExtraction()),
    )
    submission_id = _new_submission()
    response = client.post(
        f"/api/submissions/{submission_id}/transcribe",
        files={"file": ("../../../evil.png", io.BytesIO(PNG_1X1), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["image_filename"] == f"{submission_id}.png"
    assert ".." not in body["image_filename"]
    written = list(main.IMAGES_DIR.iterdir())
    assert len(written) == 1
    assert written[0].name == f"{submission_id}.png"


def test_inspect_upload_reports_pdf_page_count():
    import fitz

    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    pdf_bytes = doc.tobytes()

    response = client.post(
        "/api/uploads/inspect",
        files={"file": ("scan.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_type"] == "pdf"
    assert body["page_count"] == 2


def test_inspect_upload_rejects_garbage():
    response = client.post(
        "/api/uploads/inspect",
        files={"file": ("junk.bin", io.BytesIO(b"garbage"), "application/octet-stream")},
    )
    assert 400 <= response.status_code < 500


def test_preview_upload_of_an_out_of_range_page_is_rejected():
    response = client.post(
        "/api/uploads/preview",
        files={"file": ("scan.png", io.BytesIO(PNG_1X1), "image/png")},
        data={"page": "2"},
    )
    assert 400 <= response.status_code < 500


def test_transcribe_a_specific_pdf_page(monkeypatch):
    import fitz

    monkeypatch.setattr(
        main,
        "transcribe",
        lambda image_b64, media_type: (
            Transcription(steps=[Step(index=1, latex="x = 1", confidence="high")], notes=""),
            IdentityExtraction(),
        ),
    )

    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    pdf_bytes = doc.tobytes()

    submission_id = _new_submission()
    response = client.post(
        f"/api/submissions/{submission_id}/transcribe",
        files={"file": ("scan.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"page": "2"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_page"] == 2
    assert body["source_page_count"] == 2


NEW_QUESTION = {
    "id": "authored1",
    "prompt": "Solve $x^2 - 7x + 12 = 0$.",
    "model_solution_steps": [
        "x^2 - 7x + 12 = 0",
        "(x - 3)(x - 4) = 0",
        "x = 3, x = 4",
    ],
    "variable": "x",
    "criteria": [{"id": "C1", "max": 2, "description": "Solved it"}],
}


SOUND_SOLUTION_STEPS = [
    Step(index=1, latex="x^2 - 7x + 12 = 0"),
    Step(index=2, latex="(x - 3)(x - 4) = 0"),
    Step(index=3, latex="x = 3, x = 4", confidence="low"),
]


def _stub_solution_transcription(monkeypatch, steps, notes=""):
    """The new call path needs its own mock target.

    Every existing transcription stub patches `main.transcribe` or
    `transcriber.complete_json`; neither intercepts a lecturer's solution photo.
    """
    monkeypatch.setattr(
        main,
        "transcribe_model_solution",
        lambda image_b64, media_type: Transcription(steps=steps, notes=notes),
    )


def test_solution_transcribe_returns_steps_and_stores_a_content_addressed_image(
    monkeypatch,
):
    _stub_solution_transcription(monkeypatch, SOUND_SOLUTION_STEPS, notes="clear hand")

    body = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("solution.png", io.BytesIO(PNG_1X1), "image/png")},
    ).json()

    assert re.fullmatch(r"solution-[0-9a-f]{12}\.png", body["image_filename"])
    assert (main.IMAGES_DIR / body["image_filename"]).is_file()
    assert body["transcription"]["steps"][0]["latex"] == "x^2 - 7x + 12 = 0"
    assert body["transcription"]["notes"] == "clear hand"
    assert body["page"] == 1 and body["page_count"] == 1


def test_solution_transcribe_is_idempotent_for_the_same_image(monkeypatch):
    _stub_solution_transcription(monkeypatch, SOUND_SOLUTION_STEPS)

    first = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("a.png", io.BytesIO(PNG_1X1), "image/png")},
    ).json()
    second = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("b.png", io.BytesIO(PNG_1X1), "image/png")},
    ).json()

    assert first["image_filename"] == second["image_filename"]
    assert len(list(main.IMAGES_DIR.iterdir())) == 1


def test_solution_transcribe_creates_no_submission(monkeypatch):
    """Pins the statelessness claim: the question does not exist yet."""
    _stub_solution_transcription(monkeypatch, SOUND_SOLUTION_STEPS)
    client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("solution.png", io.BytesIO(PNG_1X1), "image/png")},
    )
    assert list(store.SUBMISSIONS_DIR.iterdir()) == []


def test_solution_transcribe_with_empty_file_is_a_4xx():
    response = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
    )
    assert 400 <= response.status_code < 500


def test_solution_transcribe_with_garbage_never_reaches_the_model(monkeypatch):
    def _must_not_be_called(**_):
        raise AssertionError("the vision model must never see undecodable bytes")

    monkeypatch.setattr(main, "transcribe_model_solution", _must_not_be_called)

    response = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("junk.png", io.BytesIO(b"not an image"), "image/png")},
    )
    assert 400 <= response.status_code < 500


def test_solution_transcribe_out_of_range_page_is_a_4xx(monkeypatch):
    _stub_solution_transcription(monkeypatch, SOUND_SOLUTION_STEPS)
    response = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("solution.png", io.BytesIO(PNG_1X1), "image/png")},
        data={"page": "2"},
    )
    assert 400 <= response.status_code < 500


def test_solution_transcribe_honours_a_pdf_page(monkeypatch):
    import fitz

    _stub_solution_transcription(monkeypatch, SOUND_SOLUTION_STEPS)
    doc = fitz.open()
    doc.new_page()
    doc.new_page()

    body = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("solution.pdf", io.BytesIO(doc.tobytes()), "application/pdf")},
        data={"page": "2"},
    ).json()

    assert body["page"] == 2
    assert body["page_count"] == 2


def test_solution_transcribe_offline_cache_miss_is_a_503_with_a_hint(monkeypatch):
    from app.llm import OfflineCacheMiss

    def boom(image_b64, media_type):
        raise OfflineCacheMiss("no cached response for key abc")

    monkeypatch.setattr(main, "transcribe_model_solution", boom)

    response = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("solution.png", io.BytesIO(PNG_1X1), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["error"] == "offline_cache_miss"
    assert response.json()["hint"]


def test_a_photographed_model_solution_flows_end_to_end_into_a_question(monkeypatch):
    _stub_solution_transcription(monkeypatch, SOUND_SOLUTION_STEPS, notes="clear hand")
    transcribed = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("solution.png", io.BytesIO(PNG_1X1), "image/png")},
    ).json()

    created = client.post(
        "/api/questions",
        json={
            **NEW_QUESTION,
            "model_solution_steps": [
                s["latex"] for s in transcribed["transcription"]["steps"]
            ],
            "solution_image_filename": transcribed["image_filename"],
            "solution_source_page": transcribed["page"],
            "solution_transcription": transcribed["transcription"],
        },
    )
    assert created.status_code == 200

    fetched = client.get("/api/questions/authored1").json()
    assert fetched["solution_image_filename"] == transcribed["image_filename"]
    assert fetched["solution_source_page"] == 1
    assert fetched["solution_transcription"]["notes"] == "clear hand"


def test_a_photographed_model_solution_that_loses_a_root_is_refused_on_save(monkeypatch):
    """A photo is not an excuse: SymPy remains the arbiter."""
    _stub_solution_transcription(
        monkeypatch,
        [Step(index=1, latex="x^2 = 5x"), Step(index=2, latex="x = 5")],
    )
    transcribed = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("solution.png", io.BytesIO(PNG_1X1), "image/png")},
    ).json()

    response = client.post(
        "/api/questions",
        json={
            **NEW_QUESTION,
            "model_solution_steps": [
                s["latex"] for s in transcribed["transcription"]["steps"]
            ],
            "solution_image_filename": transcribed["image_filename"],
        },
    )
    assert response.status_code == 400
    assert any("step 2" in p for p in response.json()["detail"])
    assert client.get("/api/questions/authored1").status_code == 404


def test_editing_a_question_preserves_its_provenance(monkeypatch):
    """PUT replaces the whole question, so a client that omits provenance would
    null it out on an ordinary prompt edit."""
    _stub_solution_transcription(monkeypatch, SOUND_SOLUTION_STEPS)
    transcribed = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("solution.png", io.BytesIO(PNG_1X1), "image/png")},
    ).json()
    payload = {
        **NEW_QUESTION,
        "solution_image_filename": transcribed["image_filename"],
        "solution_source_page": 1,
        "solution_transcription": transcribed["transcription"],
    }
    client.post("/api/questions", json=payload)

    client.put(
        "/api/questions/authored1",
        json={**payload, "prompt": "Solve $x^2 - 7x + 12 = 0$ by any method."},
    )

    fetched = client.get("/api/questions/authored1").json()
    assert fetched["solution_image_filename"] == transcribed["image_filename"]
    assert fetched["solution_transcription"] is not None


def test_re_photographing_without_changing_the_maths_keeps_existing_marks(monkeypatch):
    """Re-photographing is a documentation change, not a mathematical one, so it
    must not discard a cohort's marks."""
    _stub_llm(monkeypatch)
    client.post("/api/questions", json=NEW_QUESTION)
    created = client.post("/api/submissions", json={"question_id": "authored1"}).json()
    client.post(f"/api/submissions/{created['id']}/mark")

    client.put(
        "/api/questions/authored1",
        json={**NEW_QUESTION, "solution_image_filename": "solution-abcdef123456.png"},
    )

    assert client.get(f"/api/submissions/{created['id']}").json()["marks"] is not None


def test_the_solution_image_can_be_fetched_back(monkeypatch):
    _stub_solution_transcription(monkeypatch, SOUND_SOLUTION_STEPS)
    transcribed = client.post(
        "/api/questions/solution-transcribe",
        files={"file": ("solution.png", io.BytesIO(PNG_1X1), "image/png")},
    ).json()
    client.post(
        "/api/questions",
        json={**NEW_QUESTION, "solution_image_filename": transcribed["image_filename"]},
    )

    response = client.get("/api/questions/authored1/solution-image")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content == (main.IMAGES_DIR / transcribed["image_filename"]).read_bytes()


def test_a_question_with_no_solution_image_returns_404():
    assert client.get("/api/questions/q1/solution-image").status_code == 404


def test_an_unknown_questions_solution_image_returns_404():
    assert client.get("/api/questions/nope/solution-image").status_code == 404


def test_a_hand_edited_traversal_filename_is_refused():
    """data/questions.json is hand-editable, so this is realistic input."""
    from app.models import Question

    store.save_question(
        Question(
            **{**NEW_QUESTION, "solution_image_filename": "../../../../.env"}
        )
    )
    assert client.get("/api/questions/authored1/solution-image").status_code == 404


def test_question_template_offers_a_method_agnostic_default_rubric():
    body = client.get("/api/question-template").json()
    assert body["criteria"]
    text = " ".join(c["description"].lower() for c in body["criteria"])
    assert "factoris" not in text


def test_a_lecturer_can_add_a_question_and_then_use_it():
    created = client.post("/api/questions", json=NEW_QUESTION)
    assert created.status_code == 200

    assert "authored1" in [q["id"] for q in client.get("/api/questions").json()]
    assert client.get("/api/questions/authored1").status_code == 200
    # And it is immediately usable - no restart, no cache staleness.
    assert (
        client.post("/api/submissions", json={"question_id": "authored1"}).status_code
        == 200
    )


def test_a_question_whose_model_solution_loses_a_root_is_refused():
    """The tool holds the lecturer to the standard it holds the student to."""
    bad = {**NEW_QUESTION, "model_solution_steps": ["x^2 = 5x", "x = 5"]}
    response = client.post("/api/questions", json=bad)
    assert response.status_code == 400
    assert any("step 2" in p for p in response.json()["detail"])
    # Nothing was saved.
    assert client.get("/api/questions/authored1").status_code == 404


def test_validate_reports_problems_without_saving_anything():
    bad = {**NEW_QUESTION, "model_solution_steps": ["x^2 = 5x", "x = 5"]}
    body = client.post("/api/questions/validate", json=bad).json()
    assert body["ok"] is False
    assert body["problems"]
    assert client.get("/api/questions/authored1").status_code == 404

    good = client.post("/api/questions/validate", json=NEW_QUESTION).json()
    assert good["ok"] is True
    assert good["problems"] == []


def test_adding_a_question_with_an_existing_id_is_rejected():
    assert client.post("/api/questions", json={**NEW_QUESTION, "id": "q1"}).status_code == 409


def test_editing_a_question_cannot_change_its_id():
    client.post("/api/questions", json=NEW_QUESTION)
    response = client.put(
        "/api/questions/authored1", json={**NEW_QUESTION, "id": "renamed"}
    )
    assert response.status_code == 400


def test_editing_a_model_solution_invalidates_marks_made_against_the_old_one(
    monkeypatch,
):
    """A mark computed against a different model solution no longer describes
    this question, and a stale mark is worse than no mark."""
    _stub_llm(monkeypatch)
    client.post("/api/questions", json=NEW_QUESTION)
    created = client.post(
        "/api/submissions", json={"question_id": "authored1"}
    ).json()
    client.put(
        f"/api/submissions/{created['id']}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 - 7x + 12 = 0"}]},
    )
    marked = client.post(f"/api/submissions/{created['id']}/mark").json()
    assert marked["marks"] is not None

    client.put(
        "/api/questions/authored1",
        json={
            **NEW_QUESTION,
            "model_solution_steps": [
                "x^2 - 7x + 12 = 0",
                "(x - 3)(x - 4) = 0",
                "x = 4, x = 3",
            ],
            "criteria": [{"id": "C1", "max": 5, "description": "Rewritten"}],
        },
    )

    after = client.get(f"/api/submissions/{created['id']}").json()
    assert after["marks"] is None
    assert after["verification"] is None


def test_editing_only_the_prompt_leaves_existing_marks_alone(monkeypatch):
    _stub_llm(monkeypatch)
    client.post("/api/questions", json=NEW_QUESTION)
    created = client.post("/api/submissions", json={"question_id": "authored1"}).json()
    client.post(f"/api/submissions/{created['id']}/mark")

    client.put(
        "/api/questions/authored1",
        json={**NEW_QUESTION, "prompt": "Solve $x^2 - 7x + 12 = 0$ by any method."},
    )

    after = client.get(f"/api/submissions/{created['id']}").json()
    assert after["marks"] is not None


def test_a_lecturer_can_delete_their_own_question():
    client.post("/api/questions", json=NEW_QUESTION)
    assert client.delete("/api/questions/authored1").status_code == 200
    assert client.get("/api/questions/authored1").status_code == 404


def test_deleting_a_seeded_question_hides_it_without_touching_the_seed_file():
    assert client.delete("/api/questions/q3").status_code == 200
    assert client.get("/api/questions/q3").status_code == 404
    # The shipped seed file is unchanged: a fresh overlay restores it.
    seeded = json.loads(
        (store.SEEDS_DIR / "questions.json").read_text(encoding="utf-8")
    )
    assert "q3" in [item["id"] for item in seeded]


def test_a_question_with_submissions_cannot_be_deleted(monkeypatch):
    _stub_llm(monkeypatch)
    client.post("/api/questions", json=NEW_QUESTION)
    client.post("/api/submissions", json={"question_id": "authored1"})

    response = client.delete("/api/questions/authored1")
    assert response.status_code == 409
    assert "unmarkable" in response.json()["detail"]
    assert client.get("/api/questions/authored1").status_code == 200


def test_deleting_an_unknown_question_is_a_404():
    assert client.delete("/api/questions/nope").status_code == 404


def test_regenerate_practice_as_scenario_questions(monkeypatch):
    _stub_llm(monkeypatch)
    submission_id = _new_submission()
    client.put(
        f"/api/submissions/{submission_id}/steps",
        json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
    )
    marked = client.post(f"/api/submissions/{submission_id}/mark").json()
    assert all(p["question_type"] == "bare" for p in marked["practice"])

    body = client.post(
        f"/api/submissions/{submission_id}/practice",
        json={"question_type": "scenario"},
    ).json()

    assert len(body["practice"]) == 3
    # Deliberately not asserting that a scenario *appears*. The practice seed
    # derives from the random submission id, and quad_zero_root's word problem
    # honestly declines when it drew a = 1 (the prose would call a square a
    # rectangle), so an all-bare result is a legitimate outcome roughly one run
    # in sixty. What must always hold is that every question is one of the two
    # known framings, and that any scenario carries its admissible roots and an
    # explanation. tests/test_practice.py pins the appears-at-all case with a
    # fixed seed.
    assert all(p["question_type"] in {"bare", "scenario"} for p in body["practice"])
    for scenario in [p for p in body["practice"] if p["question_type"] == "scenario"]:
        assert scenario["admissible_roots"]
        assert scenario["rejected_note"]
    # Regenerating phrasing must not disturb any verified result.
    assert body["marks"] is not None
    assert body["verification"] is not None


def test_regenerate_practice_before_marking_returns_409():
    submission_id = _new_submission()
    response = client.post(
        f"/api/submissions/{submission_id}/practice",
        json={"question_type": "scenario"},
    )
    assert response.status_code == 409


def test_regenerate_practice_with_an_unknown_type_is_rejected(monkeypatch):
    _stub_llm(monkeypatch)
    submission_id = _new_submission()
    client.post(f"/api/submissions/{submission_id}/mark")

    response = client.post(
        f"/api/submissions/{submission_id}/practice",
        json={"question_type": "interpretive_dance"},
    )
    assert response.status_code == 400


def test_class_summary_is_available():
    response = client.get("/api/class/summary")
    assert response.status_code == 200
    body = response.json()
    assert "misconception_counts" in body
    assert "students" in body
    assert "recommendation" in body


def test_class_summary_falls_back_to_labelled_sample_when_nothing_is_marked():
    """The isolate_disk_writes fixture gives every test an empty directory."""
    body = client.get("/api/class/summary").json()
    assert body["source"] == "sample"
    assert "sample" in body["source_note"].lower()
    # The seeded fixture must itself satisfy the consistency invariant.
    assert len(body["students"]) == body["marked"]


def test_class_summary_computes_from_real_submissions(monkeypatch):
    _stub_llm(monkeypatch)
    for pseudonym in ("Ann", "Ben"):
        created = client.post(
            "/api/submissions",
            json={"question_id": "q2", "student_pseudonym": pseudonym},
        ).json()
        client.put(
            f"/api/submissions/{created['id']}/steps",
            json={"steps": [{"index": 1, "latex": "x^2 = 5x"}]},
        )
        client.post(f"/api/submissions/{created['id']}/mark")

    body = client.get("/api/class/summary").json()

    assert body["source"] == "computed"
    assert body["cohort_size"] == 2
    assert body["marked"] == 2
    assert sorted(row["pseudonym"] for row in body["students"]) == ["Ann", "Ben"]
    assert body["misconception_counts"][0]["count"] == 2
    assert "2 of 2" in body["recommendation"]


def test_class_summary_can_force_the_demo_cohort_when_real_submissions_exist(monkeypatch):
    _stub_llm(monkeypatch)
    created = client.post(
        "/api/submissions", json={"question_id": "q2", "student_pseudonym": "Live student"}
    ).json()
    client.post(f"/api/submissions/{created['id']}/mark")

    body = client.get("/api/class/summary?sample=true").json()

    assert body["source"] == "sample"
    assert body["cohort_size"] == 6
    assert all(row["pseudonym"] != "Live student" for row in body["students"])


def test_class_summary_skips_a_corrupt_submission_file(monkeypatch):
    _stub_llm(monkeypatch)
    created = client.post("/api/submissions", json={"question_id": "q2"}).json()
    client.post(f"/api/submissions/{created['id']}/mark")

    (store.SUBMISSIONS_DIR / "half-written.json").write_text("{not json", encoding="utf-8")

    body = client.get("/api/class/summary").json()
    # The good submission still counts; the broken file is skipped, not fatal.
    assert body["source"] == "computed"
    assert body["cohort_size"] == 1


def test_static_index_is_served_at_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "AIMS" in response.text
