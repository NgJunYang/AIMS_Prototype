import base64
import hashlib
import json
import re
import uuid
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import uploads
from app.authoring import default_criteria, validate_question
from app.cohort import summarise
from app.config import ALLOWED_ORIGINS, IMAGES_DIR, SEEDS_DIR, STATIC_DIR
from app.feedback import write as write_feedback
from app.llm import OfflineCacheMiss
from app.marker import mark as mark_submission
from app.models import (
    ClassSummary,
    Feedback,
    IdentityExtraction,
    Question,
    Step,
    Submission,
    Transcription,
)
from app.practice import QUESTION_TYPES, generate_practice
from app.store import (
    delete_question,
    get_question,
    list_questions,
    list_submissions,
    load_submission,
    save_question,
    save_submission,
)
from app.transcriber import transcribe, transcribe_model_solution
from app.tutor import answer as tutor_answer
from app.tutor import draft_email as tutor_draft_email
from app.verifier import verify

app = FastAPI(title="AIMS")

# Only needed when the frontend is served from a different origin than this
# API - e.g. a static build on GitHub Pages calling a backend deployed
# elsewhere. Same-origin deployment (this app serving static/ itself, the
# default) never hits CORS at all. No cookies or credentials are used, so a
# permissive default is a data-shape risk, not an auth one; see ALLOWED_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Server-derived names only. Also the fence for the solution-image route: this
# filename round-trips through the hand-editable data/questions.json overlay.
_SOLUTION_IMAGE_PATTERN = re.compile(r"^solution-[0-9a-f]{12}\.png$")


# ---------- request bodies ----------


class CreateSubmission(BaseModel):
    question_id: str
    student_pseudonym: str = "Student A"
    channel: Literal["tutorial", "test"] = "tutorial"


class UpdateSteps(BaseModel):
    steps: list[Step]


class UpdateIdentity(BaseModel):
    name: str | None = None
    student_id: str | None = None


class Override(BaseModel):
    criterion_id: str
    proposed: int


class UpdateFeedback(BaseModel):
    what_went_well: str = Field(max_length=4000)
    what_went_wrong: str = Field(max_length=4000)
    how_to_improve: str = Field(max_length=4000)


class QuestionCheck(BaseModel):
    ok: bool
    problems: list[str] = Field(default_factory=list)


class SolutionTranscription(BaseModel):
    """A transcribed model solution, attached to no question.

    The question does not exist yet when its solution is photographed, so this
    is keyed by nothing and creates nothing but the stored image.
    """

    transcription: Transcription
    page: int
    page_count: int
    image_filename: str


class RegeneratePractice(BaseModel):
    question_type: str = "bare"
    count: int = Field(default=3, ge=1, le=10)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class ChatReply(BaseModel):
    answer: str


class DraftEmailRequest(BaseModel):
    concern: str = Field(max_length=2000)


class EmailDraft(BaseModel):
    subject: str
    body: str


class StudentCriterion(BaseModel):
    criterion_id: str
    proposed: int
    max: int
    justification: str


class StudentView(BaseModel):
    """What a student is allowed to see about their own marked script.

    Deliberately omits the instructor-only internals - the AI's original
    suggestion, which criteria were manually adjusted, the raw transcription.
    The student sees the final numbers and the feedback, nothing about how the
    sausage was made.
    """

    question_id: str
    question_prompt: str
    student_pseudonym: str
    channel: Literal["tutorial", "test"]
    total_proposed: int
    total_max: int
    criteria: list[StudentCriterion]
    feedback: Feedback | None
    practice: list = Field(default_factory=list)
    final_answer_correct: bool = False
    final_answer_verified: bool = False


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


@app.get("/api/question-template")
def api_question_template() -> dict:
    """A starting point for a new question: a method-agnostic default rubric.

    Method-agnostic on purpose - a rubric naming factorisation would penalise
    a student who correctly completed the square instead.
    """
    return {
        "variable": "x",
        "criteria": [c.model_dump() for c in default_criteria()],
    }


@app.post("/api/questions/solution-transcribe")
async def api_transcribe_solution(
    file: UploadFile = File(...), page: int = Form(1)
) -> SolutionTranscription:
    """Transcribe a photograph of the lecturer's own handwritten worked solution.

    Stateless: no question exists yet at this point, so nothing is created but
    the stored image. The transcription is returned for the lecturer to correct,
    and only becomes a model solution once they save the question - at which
    point validate_question puts it through the same SymPy verification a
    student's working gets.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        info = uploads.inspect(raw)
        png = uploads.render_page(raw, page=page)
    except (uploads.UnsupportedUpload, uploads.PageOutOfRange) as exc:
        # Deliberately before the vision call: garbage never reaches the model.
        raise HTTPException(status_code=400, detail=str(exc))

    # Content-addressed on the *rendered* PNG, so the same photo submitted as a
    # JPEG and as a one-page PDF dedupes to one file. The "solution-" prefix is
    # load-bearing, not cosmetic: submission scans are f"{submission_id}.png"
    # where submission_id is uuid4().hex[:12] - also twelve hex characters - so
    # a bare digest would share their exact namespace shape.
    #
    # Content-addressing buys idempotence, not orphan-freedom: a lecturer who
    # transcribes and then cancels leaves this file behind. Images here are
    # write-once and never deleted, including on DELETE /api/questions/{id},
    # since two questions may legitimately reference the same bytes.
    filename = f"solution-{hashlib.sha256(png).hexdigest()[:12]}.png"
    path = IMAGES_DIR / filename
    if not path.exists():
        path.write_bytes(png)

    transcription = transcribe_model_solution(
        image_b64=base64.b64encode(png).decode(), media_type="image/png"
    )
    return SolutionTranscription(
        transcription=transcription,
        page=page,
        page_count=info.page_count,
        image_filename=filename,
    )


@app.post("/api/questions/validate")
def api_validate_question(question: Question) -> QuestionCheck:
    """Dry-run the same checks saving would apply, without saving.

    Lets the lecturer see their own model solution verified before committing
    to it, which is the point: the tool holds the author to the standard it
    holds the student to.
    """
    return QuestionCheck(
        ok=not validate_question(question), problems=validate_question(question)
    )


@app.post("/api/questions")
def api_create_question(question: Question) -> Question:
    if question.id in {q.id for q in list_questions()}:
        raise HTTPException(
            status_code=409, detail=f"a question with id {question.id!r} already exists"
        )
    problems = validate_question(question)
    if problems:
        raise HTTPException(status_code=400, detail=problems)
    save_question(question)
    return question


@app.put("/api/questions/{question_id}")
def api_update_question(question_id: str, question: Question) -> Question:
    existing = _question(question_id)
    if question.id != question_id:
        raise HTTPException(
            status_code=400, detail="a question's id cannot be changed"
        )
    problems = validate_question(question)
    if problems:
        raise HTTPException(status_code=400, detail=problems)

    save_question(question)

    # A submission was verified and marked against the *old* model solution and
    # rubric. If either changed, those results no longer describe this question,
    # and a stale mark is worse than no mark - so clear them and require a
    # re-mark, exactly as editing the transcribed steps does.
    if (
        question.model_solution_steps != existing.model_solution_steps
        or question.criteria != existing.criteria
        or question.variable != existing.variable
    ):
        for submission in list_submissions():
            if submission.question_id != question_id or submission.marks is None:
                continue
            _invalidate_downstream(submission)
            save_submission(submission)

    return question


@app.get("/api/questions/{question_id}/solution-image")
def api_question_solution_image(question_id: str) -> FileResponse:
    """The photograph a question's model solution was transcribed from.

    Served per-question rather than by mounting StaticFiles on IMAGES_DIR,
    which would expose every student submission scan to anyone who guessed a
    twelve-hex id. This route only ever returns bytes a question references.
    """
    question = _question(question_id)
    name = question.solution_image_filename
    if not name or not _SOLUTION_IMAGE_PATTERN.match(name):
        raise HTTPException(status_code=404, detail="no solution image for this question")

    # Two independent guards. The filename is server-derived today, but it
    # round-trips through data/questions.json, which store._questions() will
    # happily validate after a hand edit - so "../../../.env" is realistic
    # input, not a theoretical one.
    path = (IMAGES_DIR / name).resolve()
    if not path.is_relative_to(IMAGES_DIR.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="no solution image for this question")
    return FileResponse(path, media_type="image/png")


@app.delete("/api/questions/{question_id}")
def api_delete_question(question_id: str) -> dict[str, str]:
    _question(question_id)  # 404 if it does not exist

    dependents = [s for s in list_submissions() if s.question_id == question_id]
    if dependents:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(dependents)} submission(s) were marked against this "
                f"question. Deleting it would leave them unmarkable."
            ),
        )

    delete_question(question_id)
    return {"deleted": question_id}


# ---------- submissions ----------


@app.post("/api/submissions")
def api_create_submission(body: CreateSubmission) -> Submission:
    _question(body.question_id)
    submission = Submission(
        id=uuid.uuid4().hex[:12],
        question_id=body.question_id,
        student_pseudonym=body.student_pseudonym,
        channel=body.channel,
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
    transcription, identity = transcribe(
        image_b64=base64.b64encode(png).decode(), media_type="image/png"
    )

    submission.image_filename = filename
    submission.source_page = page
    submission.source_page_count = info.page_count
    submission.transcription = transcription
    submission.confirmed_steps = list(transcription.steps)
    submission.extracted_identity = identity
    # Pre-fill the same way transcribed steps pre-fill confirmed_steps: the
    # lecturer sees it immediately and can edit or overwrite it before
    # Confirm & Mark writes anything final. Never overwrite with a null - an
    # illegible/absent name should leave whatever was there (typed, or the
    # "Student N" fallback) rather than blank the field.
    if identity.name:
        submission.student_pseudonym = identity.name
    if identity.student_id:
        submission.student_id = identity.student_id
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


@app.put("/api/submissions/{submission_id}/identity")
def api_update_identity(submission_id: str, body: UpdateIdentity) -> Submission:
    """Confirm (or overwrite) the student's name/id after Confirm-screen review.

    Purely metadata about who the work belongs to - unlike /steps, this never
    invalidates verification/marks/feedback, since editing a name doesn't
    change whether the maths was correct.
    """
    submission = _submission(submission_id)
    submission.student_pseudonym = body.name or submission.student_pseudonym
    submission.student_id = body.student_id
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

    # Carry the lecturer's manual score edits across an automatic re-mark. When
    # the transcription is amended the suggestions should refresh, but an
    # explicit override is a decision, not a suggestion - keep its value and
    # just update what the model now suggests alongside it. "Reset rubric edits
    # to AI suggestions" (api_reset_overrides) is the one path that discards it.
    prior_overrides = {
        c.criterion_id: c.proposed
        for c in (submission.marks.criteria if submission.marks else [])
        if c.overridden
    }

    submission.marks = mark_submission(question, steps, submission.verification)
    for criterion in submission.marks.criteria:
        if criterion.suggested is None:
            criterion.suggested = criterion.proposed
        if criterion.criterion_id in prior_overrides:
            kept = min(prior_overrides[criterion.criterion_id], criterion.max)
            criterion.proposed = kept
            criterion.overridden = True
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


@app.post("/api/submissions/{submission_id}/reset-overrides")
def api_reset_overrides(submission_id: str) -> Submission:
    submission = _submission(submission_id)
    if submission.marks is None:
        raise HTTPException(status_code=409, detail="nothing to reset yet")

    for criterion in submission.marks.criteria:
        if criterion.suggested is not None:
            criterion.proposed = criterion.suggested
            criterion.overridden = False
    save_submission(submission)
    return submission


@app.put("/api/submissions/{submission_id}/feedback")
def api_update_feedback(submission_id: str, body: UpdateFeedback) -> Submission:
    """Persist the lecturer's edits to the generated feedback draft.

    References remain machine-generated provenance and are intentionally kept
    separate from the editable prose. A submission must have been marked first:
    otherwise there is no draft for the lecturer to review or amend.
    """
    submission = _submission(submission_id)
    if submission.feedback is None:
        raise HTTPException(status_code=409, detail="no feedback draft to edit yet")

    submission.feedback = Feedback(
        what_went_well=body.what_went_well,
        what_went_wrong=body.what_went_wrong,
        how_to_improve=body.how_to_improve,
        references=submission.feedback.references,
    )
    save_submission(submission)
    return submission


@app.post("/api/submissions/{submission_id}/practice")
def api_regenerate_practice(submission_id: str, body: RegeneratePractice) -> Submission:
    """Regenerate practice in a chosen framing, without re-marking.

    Separated from /mark deliberately: changing how a question is phrased is
    presentation, and should not cost another marking call or disturb any
    verified result.
    """
    submission = _submission(submission_id)
    if submission.marks is None:
        raise HTTPException(
            status_code=409, detail="mark this submission before generating practice"
        )
    if body.question_type not in QUESTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown question type: {body.question_type}",
        )

    submission.practice = generate_practice(
        submission.marks.misconceptions,
        count=body.count,
        seed=_seed_from_id(submission_id),
        question_type=body.question_type,
    )
    save_submission(submission)
    return submission


# ---------- student-facing view ----------


def _marked_submission(submission_id: str) -> Submission:
    submission = _submission(submission_id)
    if submission.marks is None or submission.feedback is None:
        raise HTTPException(
            status_code=409, detail="this submission has not been marked yet"
        )
    return submission


@app.post("/api/submissions/{submission_id}/publish")
def api_publish(submission_id: str) -> Submission:
    """Release a graded-test script to the student. Tutorial scripts are visible
    without this; a test script is not, until the instructor has vetted it."""
    submission = _marked_submission(submission_id)
    submission.published = True
    save_submission(submission)
    return submission


@app.post("/api/submissions/{submission_id}/unpublish")
def api_unpublish(submission_id: str) -> Submission:
    submission = _submission(submission_id)
    submission.published = False
    save_submission(submission)
    return submission


@app.get("/api/submissions/{submission_id}/student-view")
def api_student_view(submission_id: str) -> StudentView:
    submission = _marked_submission(submission_id)
    if submission.channel == "test" and not submission.published:
        raise HTTPException(
            status_code=403,
            detail="These results have not been published by your instructor yet.",
        )
    question = _question(submission.question_id)
    report = submission.verification
    return StudentView(
        question_id=question.id,
        question_prompt=question.prompt,
        student_pseudonym=submission.student_pseudonym,
        channel=submission.channel,
        total_proposed=submission.marks.total_proposed,
        total_max=submission.marks.total_max,
        criteria=[
            StudentCriterion(
                criterion_id=c.criterion_id,
                proposed=c.proposed,
                max=c.max,
                justification=c.justification,
            )
            for c in submission.marks.criteria
        ],
        feedback=submission.feedback,
        practice=[p.model_dump() for p in submission.practice],
        final_answer_correct=bool(report and report.final_answer_correct),
        final_answer_verified=bool(report and report.final_answer_verified),
    )


@app.post("/api/submissions/{submission_id}/chat")
def api_chat(submission_id: str, body: ChatRequest) -> ChatReply:
    """A grounded tutor: answers the student's question about their own marked
    work, constrained to the marks and checks already settled."""
    submission = _marked_submission(submission_id)
    question = _question(submission.question_id)
    report = submission.verification or verify(
        submission.confirmed_steps or [],
        question.model_solution_steps,
        question.variable,
    )
    reply = tutor_answer(
        question,
        submission.confirmed_steps or [],
        submission.marks,
        submission.feedback,
        report,
        [m.model_dump() for m in body.messages],
    )
    return ChatReply(answer=reply)


@app.post("/api/submissions/{submission_id}/draft-email")
def api_draft_email(submission_id: str, body: DraftEmailRequest) -> EmailDraft:
    """Draft an email from the student to their instructor about this question.

    Returns text only. Nothing is sent - the student reviews, edits and sends
    it from their own mail client.
    """
    submission = _marked_submission(submission_id)
    question = _question(submission.question_id)
    report = submission.verification or verify(
        submission.confirmed_steps or [],
        question.model_solution_steps,
        question.variable,
    )
    draft = tutor_draft_email(
        question,
        submission.confirmed_steps or [],
        submission.marks,
        submission.feedback,
        report,
        submission.student_pseudonym,
        body.concern,
    )
    return EmailDraft(**draft)


# ---------- class view ----------


@app.get("/api/class/summary")
def api_class_summary(sample: bool = False) -> ClassSummary:
    """The cohort view, computed from real submissions whenever any exist.

    Falls back to the seeded fixture only on a genuinely empty machine (a
    fresh clone has no submissions - data/submissions/ is gitignored), and
    labels it as sample data when it does. "Computed from 4 real submissions"
    is worth far more than an unlabelled illustrative 31. ``sample=true`` is
    the explicit pitch-safe preview: it keeps the six-student demonstration
    available even after the live workflow has marked a single script.
    """
    submissions = list_submissions()
    if submissions and not sample:
        return summarise(submissions)

    seeded = json.loads((SEEDS_DIR / "class_summary.json").read_text(encoding="utf-8"))
    seeded["source"] = "sample"
    seeded["source_note"] = (
        "Illustrative sample cohort - no submissions have been marked on this "
        "machine yet. Mark one and this view recomputes from real data."
    )
    return ClassSummary.model_validate(seeded)


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
