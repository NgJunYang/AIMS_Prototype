import io

import pytest
from fastapi.testclient import TestClient

from app import main, store
from app.main import app
from app.models import Feedback, MarkProposal, CriterionMark, Step, Transcription

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

PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d4944415478da63f8cf00000301010018dd8db000"
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
        lambda image_b64, media_type: Transcription(
            steps=[Step(index=1, latex="x^2 = 5x", confidence="low")], notes="faint"
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


def test_class_summary_is_available():
    response = client.get("/api/class/summary")
    assert response.status_code == 200
    body = response.json()
    assert "misconception_counts" in body
    assert "students" in body
    assert "recommendation" in body


def test_static_index_is_served_at_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "AIMS" in response.text
