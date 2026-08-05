import base64
import json
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import uploads
from app.config import IMAGES_DIR, SEEDS_DIR, STATIC_DIR
from app.feedback import write as write_feedback
from app.llm import OfflineCacheMiss
from app.marker import mark as mark_submission
from app.models import Question, Step, Submission
from app.practice import generate_practice
from app.store import get_question, list_questions, load_submission, save_submission
from app.transcriber import transcribe
from app.verifier import verify

app = FastAPI(title="AIMS")


# ---------- request bodies ----------


class CreateSubmission(BaseModel):
    question_id: str
    student_pseudonym: str = "Student A"


class UpdateSteps(BaseModel):
    steps: list[Step]


class Override(BaseModel):
    criterion_id: str
    proposed: int


class UploadInspection(BaseModel):
    source_type: str
    page_count: int


class UploadPreview(BaseModel):
    page: int
    page_count: int
    preview_b64: str


# ---------- error handling ----------


@app.exception_handler(OfflineCacheMiss)
def offline_cache_miss(request: Request, exc: OfflineCacheMiss) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": "offline_cache_miss",
            "detail": str(exc),
            "hint": "This input has not been cached. Use one of the sample scripts, "
            "or restart with DEMO_MODE=live.",
        },
    )


# ---------- health ----------


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------- questions ----------


@app.get("/api/questions")
def api_list_questions() -> list[Question]:
    return list_questions()


@app.get("/api/questions/{question_id}")
def api_get_question(question_id: str) -> Question:
    return _question(question_id)


# ---------- submissions ----------


@app.post("/api/submissions")
def api_create_submission(body: CreateSubmission) -> Submission:
    _question(body.question_id)
    submission = Submission(
        id=uuid.uuid4().hex[:12],
        question_id=body.question_id,
        student_pseudonym=body.student_pseudonym,
    )
    save_submission(submission)
    return submission


@app.get("/api/submissions/{submission_id}")
def api_get_submission(submission_id: str) -> Submission:
    return _submission(submission_id)


@app.post("/api/submissions/{submission_id}/transcribe")
async def api_transcribe(
    submission_id: str, file: UploadFile = File(...), page: int = Form(1)
) -> Submission:
    submission = _submission(submission_id)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        info = uploads.inspect(raw)
        png = uploads.render_page(raw, page=page)
    except (uploads.UnsupportedUpload, uploads.PageOutOfRange) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # No client-supplied component in the filename at all: submission_id is
    # already server-generated and validated by _submission() above, so this
    # is safe on its own. The old f"{id}-{file.filename}" scheme joined an
    # unsanitized client filename into a disk path before writing it.
    filename = f"{submission_id}.png"
    (IMAGES_DIR / filename).write_bytes(png)
    transcription = transcribe(
        image_b64=base64.b64encode(png).decode(), media_type="image/png"
    )

    submission.image_filename = filename
    submission.source_page = page
    submission.source_page_count = info.page_count
    submission.transcription = transcription
    submission.confirmed_steps = list(transcription.steps)
    _invalidate_downstream(submission)
    save_submission(submission)
    return submission


@app.post("/api/uploads/inspect")
async def api_inspect_upload(file: UploadFile = File(...)) -> UploadInspection:
    """Report an upload's type and page count. Stateless: touches no submission."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        info = uploads.inspect(raw)
    except uploads.UnsupportedUpload as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return UploadInspection(source_type=info.source_type, page_count=info.page_count)


@app.post("/api/uploads/preview")
async def api_preview_upload(
    file: UploadFile = File(...), page: int = Form(1)
) -> UploadPreview:
    """Render one page as a preview image, at zero cost to any submission or LLM."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        info = uploads.inspect(raw)
        png = uploads.render_page(raw, page=page)
    except (uploads.UnsupportedUpload, uploads.PageOutOfRange) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return UploadPreview(
        page=page, page_count=info.page_count, preview_b64=base64.b64encode(png).decode()
    )


@app.put("/api/submissions/{submission_id}/steps")
def api_update_steps(submission_id: str, body: UpdateSteps) -> Submission:
    submission = _submission(submission_id)

    original = {
        s.index: s.latex
        for s in (submission.transcription.steps if submission.transcription else [])
    }
    submission.confirmed_steps = [
        Step(
            index=i,
            latex=step.latex,
            confidence=step.confidence,
            edited_by_human=original.get(i) != step.latex,
        )
        for i, step in enumerate(body.steps, start=1)
    ]
    _invalidate_downstream(submission)
    save_submission(submission)
    return submission


@app.post("/api/submissions/{submission_id}/verify")
def api_verify(submission_id: str) -> Submission:
    submission = _submission(submission_id)
    question = _question(submission.question_id)
    submission.verification = verify(
        submission.confirmed_steps or [], question.model_solution_steps, question.variable
    )
    save_submission(submission)
    return submission


@app.post("/api/submissions/{submission_id}/mark")
def api_mark(submission_id: str) -> Submission:
    submission = _submission(submission_id)
    question = _question(submission.question_id)
    steps = submission.confirmed_steps or []

    if submission.verification is None:
        submission.verification = verify(steps, question.model_solution_steps, question.variable)

    submission.marks = mark_submission(question, steps, submission.verification)
    submission.feedback = write_feedback(question, steps, submission.marks, submission.verification)
    submission.practice = generate_practice(
        submission.marks.misconceptions,
        count=3,
        seed=_seed_from_id(submission_id),
    )
    save_submission(submission)
    return submission


@app.post("/api/submissions/{submission_id}/override")
def api_override(submission_id: str, body: Override) -> Submission:
    submission = _submission(submission_id)
    if submission.marks is None:
        raise HTTPException(status_code=409, detail="nothing to override yet")

    for criterion in submission.marks.criteria:
        if criterion.criterion_id == body.criterion_id:
            if body.proposed > criterion.max or body.proposed < 0:
                raise HTTPException(
                    status_code=400, detail=f"{body.proposed} is outside 0..{criterion.max}"
                )
            criterion.proposed = body.proposed
            criterion.overridden = True
            save_submission(submission)
            return submission

    raise HTTPException(status_code=404, detail=f"unknown criterion: {body.criterion_id}")


# ---------- class view ----------


@app.get("/api/class/summary")
def api_class_summary() -> dict:
    return json.loads((SEEDS_DIR / "class_summary.json").read_text(encoding="utf-8"))


# ---------- helpers ----------


def _question(question_id: str) -> Question:
    try:
        return get_question(question_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown question: {question_id}")


def _submission(submission_id: str) -> Submission:
    try:
        return load_submission(submission_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown submission: {submission_id}")


def _seed_from_id(submission_id: str) -> int:
    """Deterministic seed for practice generation, robust to non-hex ids."""
    try:
        return int(submission_id, 16) % 10_000
    except ValueError:
        return int.from_bytes(submission_id.encode(), "little", signed=False) % 10_000


def _invalidate_downstream(submission: Submission) -> None:
    """Confirmed steps changed, so anything derived from them is stale.

    A mark attached to working the lecturer has since edited would be worse
    than no mark at all.
    """
    submission.verification = None
    submission.marks = None
    submission.feedback = None
    submission.practice = []


# Must stay last: the static mount is a catch-all and would otherwise
# swallow every /api/... route above.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
