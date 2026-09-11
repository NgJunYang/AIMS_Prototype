"""Instructor import API: review drafts first, then create existing domain objects."""
import hashlib
import uuid
from collections import Counter

from anthropic import AnthropicError
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app import store, tutorial_ingestion as ingestion, uploads
from app.assignment_review import student_key
from app.authoring import validate_question
from app.ingestion_models import ConfirmAnswers, ConfirmQuestions, ConfirmSolutions, QuestionDraft, TutorialImport
from app.llm import OfflineCacheMiss
from app.models import Assignment, Question, Step, Submission, Transcription


def _assignment(assignment_id: str) -> Assignment:
    try:
        assignment = store.load_assignment(assignment_id)
    except KeyError:
        raise HTTPException(404, "Unknown assignment.")
    if assignment.kind != "tutorial":
        raise HTTPException(409, "Whole-PDF ingestion currently supports tutorial assignments.")
    return assignment


def _draft(import_id: str, stage: str | None = None, revision: int | None = None) -> TutorialImport:
    try:
        draft = store.load_import(import_id)
    except KeyError:
        raise HTTPException(404, "Unknown tutorial import.")
    _assignment(draft.assignment_id)
    if stage and draft.stage != stage:
        raise HTTPException(409, f"This import is at stage {draft.stage}; reload it before continuing.")
    if revision is not None and draft.revision != revision:
        raise HTTPException(409, "This draft changed in another session. Reload before confirming.")
    return draft


def _questions(assignment: Assignment) -> list[Question]:
    if not assignment.question_ids:
        raise HTTPException(409, "Confirm questions, solutions and rubrics before importing student work.")
    try:
        questions = [store.get_question(qid) for qid in assignment.question_ids]
    except KeyError:
        raise HTTPException(409, "The assignment contains a missing question. Repair its setup first.")
    for question in questions:
        problems = validate_question(question)
        if problems:
            raise HTTPException(409, [f"{question.label or question.id}: {p}" for p in problems])
    return questions


async def _pdf(file: UploadFile) -> tuple[list[bytes], str]:
    raw = await file.read(uploads.MAX_DOCUMENT_BYTES + 1)
    try:
        pages = await run_in_threadpool(uploads.render_document, raw)
    except uploads.UnsupportedUpload as exc:
        raise HTTPException(400, str(exc))
    return pages, hashlib.sha256(raw).hexdigest()


async def _extract(function, *args):
    try:
        return await run_in_threadpool(function, *args)
    except OfflineCacheMiss:
        raise  # existing offline/cache handler remains authoritative
    except AnthropicError:
        raise HTTPException(502, "Document extraction service failed. Retry the upload; no questions or submissions were changed.")
    except (ValueError, RuntimeError):
        raise HTTPException(502, "Document extraction returned invalid or incomplete structured output. Retry with a smaller PDF or correct the source.")


def _pages(pages: list[int], count: int) -> None:
    if any(p < 1 or p > count for p in pages):
        raise HTTPException(400, f"Source pages must be between 1 and {count}.")


def _labels(questions: list[QuestionDraft]) -> None:
    labels = [ingestion.normalize_label(q.label).casefold() for q in questions]
    if any(not label for label in labels) or len(set(labels)) != len(labels):
        raise HTTPException(400, "Every question needs a unique label. Correct missing or duplicate labels.")
    if any(not q.prompt.strip() for q in questions):
        raise HTTPException(400, "Every question needs non-empty question text.")


def _confirmed_mappings(items, question_ids: list[str], page_count: int) -> None:
    if Counter(item.question_id for item in items) != Counter(question_ids):
        raise HTTPException(409, "Map exactly one block to every question. Correct unmatched/duplicate blocks, or add missing answers.")
    if any(not item.confirmed for item in items):
        raise HTTPException(409, "Confirm each mapping and transcription, including missing answers, before continuing.")
    for item in items:
        _pages(item.source_pages, page_count)
        if item.status == "not_detected" and item.steps:
            raise HTTPException(400, "A missing answer cannot contain working. Correct its status or clear the working.")
        if any(not step.latex.strip() for step in item.steps):
            raise HTTPException(400, "Remove empty working lines; use no lines for an unanswered question.")


def create_router(mark_submission) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["tutorial ingestion"])

    @router.get("/assignments/{assignment_id}/imports")
    @store.submission_transaction
    def list_imports(assignment_id: str) -> list[TutorialImport]:
        _assignment(assignment_id)
        return store.list_imports(assignment_id)

    @router.get("/tutorial-imports/{import_id}")
    @store.submission_transaction
    def get_import(import_id: str) -> TutorialImport:
        return _draft(import_id)

    @router.get("/tutorial-imports/{import_id}/pages/{page}")
    def source_page(import_id: str, page: int, solution: bool = False) -> FileResponse:
        try:
            return FileResponse(store.import_page_path(import_id, page, solution=solution), media_type="image/png")
        except KeyError:
            raise HTTPException(404, "Unknown source page.")

    @router.post("/assignments/{assignment_id}/imports/questions")
    async def question_pdf(assignment_id: str, file: UploadFile = File(...)) -> TutorialImport:
        assignment = _assignment(assignment_id)
        if assignment.question_ids:
            raise HTTPException(409, "Use an empty tutorial assignment for question-paper import; existing questions will not be overwritten.")
        pages, digest = await _pdf(file)
        title, questions, warnings = await _extract(ingestion.extract_tutorial_questions, pages)
        with store.submission_lock:
            if _assignment(assignment_id).question_ids:
                raise HTTPException(409, "The assignment was populated while extraction ran. Nothing was overwritten.")
            draft = TutorialImport(id=uuid.uuid4().hex[:12], assignment_id=assignment_id,
                                   kind="setup", stage="questions", filename=file.filename or "questions.pdf",
                                   page_count=len(pages), document_hash=digest, title=title,
                                   questions=questions, warnings=warnings)
            store.save_import(draft, pages=pages)
            return draft

    @router.post("/tutorial-imports/{import_id}/confirm-questions")
    @store.submission_transaction
    def confirm_questions(import_id: str, body: ConfirmQuestions) -> TutorialImport:
        draft = _draft(import_id, "questions", body.revision)
        if _assignment(draft.assignment_id).question_ids:
            raise HTTPException(409, "This assignment already has questions. Use an empty assignment.")
        _labels(body.questions)
        for question in body.questions:
            _pages(question.source_pages, draft.page_count)
            question.label = ingestion.normalize_label(question.label)
            # Bank IDs are globally unique; labels remain human-facing and editable.
            question.question_id = f"{draft.assignment_id}-{uuid.uuid4().hex[:8]}"
            question.model_solution_steps = []
            question.criteria = []
            question.solution_transcription = None
            question.solution_source_pages = []
            question.problems = []
        draft.questions = body.questions
        draft.stage = "solutions"
        draft.revision += 1
        store.save_import(draft)
        return draft

    @router.post("/tutorial-imports/{import_id}/solutions")
    async def solution_pdf(import_id: str, revision: int = Form(...), file: UploadFile = File(...)) -> TutorialImport:
        draft = _draft(import_id, "solutions", revision)
        pages, digest = await _pdf(file)
        solutions, warnings = await _extract(ingestion.extract_model_solutions, pages, draft.questions)
        with store.submission_lock:
            draft = _draft(import_id, "solutions", revision)
            draft.solutions = solutions
            draft.solution_page_count = len(pages)
            draft.solution_document_hash = digest
            draft.warnings = warnings
            for question in draft.questions:
                matches = [s for s in solutions if s.question_id == question.question_id]
                question.problems = ingestion.solution_problems(question, matches[0]) if len(matches) == 1 else ["Solution mapping needs correction."]
            draft.revision += 1
            store.save_import(draft, solution_pages=pages)
            return draft

    @router.post("/tutorial-imports/{import_id}/confirm-solutions")
    @store.submission_transaction
    def confirm_solutions(import_id: str, body: ConfirmSolutions) -> TutorialImport:
        draft = _draft(import_id, "solutions", body.revision)
        assignment = _assignment(draft.assignment_id)
        if assignment.question_ids:
            raise HTTPException(409, "This assignment already has questions. Nothing was overwritten.")
        expected = [q.question_id for q in draft.questions]
        if Counter(q.question_id for q in body.questions) != Counter(expected):
            raise HTTPException(409, "Keep the confirmed question set when matching solutions.")
        _labels(body.questions)
        _confirmed_mappings(body.solutions, expected, draft.solution_page_count)
        questions = []
        problems = []
        for question in body.questions:
            _pages(question.source_pages, draft.page_count)
            solution = next(s for s in body.solutions if s.question_id == question.question_id)
            candidate = Question(id=question.question_id, label=ingestion.normalize_label(question.label),
                                 prompt=question.prompt.strip(), variable=question.variable, topic_tag=question.topic_tag,
                                 model_solution_steps=[s.latex for s in solution.steps], criteria=solution.criteria,
                                 source_import_id=draft.id, source_pages=question.source_pages,
                                 solution_source_pages=solution.source_pages,
                                 solution_source_page=next(iter(solution.source_pages), None),
                                 solution_transcription=Transcription(steps=next((s.steps for s in draft.solutions if s.block_id == solution.block_id), []), notes=solution.notes))
            problems.extend(f"{candidate.label}: {p}" for p in validate_question(candidate))
            questions.append(candidate)
        if problems:
            raise HTTPException(409, problems)
        if any(q.id in {existing.id for existing in store.list_questions()} for q in questions):
            raise HTTPException(409, "An imported question ID already exists. Nothing was overwritten.")
        assignment.question_ids = [q.id for q in questions]
        draft.questions, draft.solutions = body.questions, body.solutions
        draft.stage = "complete"
        draft.revision += 1
        store.commit_tutorial_questions(draft, questions, assignment)
        return draft

    @router.post("/assignments/{assignment_id}/imports/student")
    async def student_pdf(assignment_id: str, file: UploadFile = File(...)) -> TutorialImport:
        with store.submission_lock:
            questions = _questions(_assignment(assignment_id))
        fingerprint = ingestion.question_fingerprint(questions)
        pages, digest = await _pdf(file)
        identity, answers, warnings = await _extract(ingestion.segment_student_tutorial, pages, questions)
        with store.submission_lock:
            if ingestion.question_fingerprint(_questions(_assignment(assignment_id))) != fingerprint:
                raise HTTPException(409, "Assignment questions changed during extraction. Please retry with the updated setup.")
            draft = TutorialImport(id=uuid.uuid4().hex[:12], assignment_id=assignment_id, kind="student", stage="answers",
                                   filename=file.filename or "student.pdf", page_count=len(pages), document_hash=digest,
                                   identity=identity, answers=answers, warnings=warnings, question_fingerprint=fingerprint,
                                   questions=[QuestionDraft(question_id=q.id, label=q.label or q.id, prompt=q.prompt) for q in questions])
            store.save_import(draft, pages=pages)
            return draft

    @router.post("/tutorial-imports/{import_id}/confirm-answers")
    @store.submission_transaction
    def confirm_answers(import_id: str, body: ConfirmAnswers) -> TutorialImport:
        draft = _draft(import_id, "answers", body.revision)
        questions = _questions(_assignment(draft.assignment_id))
        if ingestion.question_fingerprint(questions) != draft.question_fingerprint:
            raise HTTPException(409, "Assignment questions changed after extraction. Re-import against the current setup.")
        _confirmed_mappings(body.answers, [q.id for q in questions], draft.page_count)
        name = (body.identity.name or "").strip()
        student_id = (body.identity.student_id or "").strip() or None
        if not name:
            raise HTTPException(400, "Confirm the student name before creating submissions.")
        anchor = Submission(id="check", question_id=questions[0].id, assignment_id=draft.assignment_id,
                            student_pseudonym=name, student_id=student_id)
        existing = [s for s in store.list_submissions() if s.assignment_id == draft.assignment_id and s.question_id in {q.id for q in questions}]
        # Also flag a missing-ID namesake: don't silently make another set when
        # the old upload simply lacked the ID now supplied by the instructor.
        conflicts = [s for s in existing if student_key(s) == student_key(anchor) or
                     ((not s.student_id or not student_id) and " ".join(s.student_pseudonym.split()).casefold() == " ".join(name.split()).casefold())]
        if conflicts:
            raise HTTPException(409, "Submissions already exist for this assignment/student: " + ", ".join(s.question_id for s in conflicts) + ". Resume existing work; this import will not replace reviewed or published results.")
        submissions = []
        for question in questions:
            answer = next(a for a in body.answers if a.question_id == question.id)
            raw = next((a for a in draft.answers if a.block_id and a.block_id == answer.block_id), None)
            steps = [Step(index=i, latex=s.latex, confidence=s.confidence,
                          edited_by_human=raw is None or i > len(raw.steps) or raw.steps[i - 1].latex != s.latex)
                     for i, s in enumerate(answer.steps, start=1)]
            submissions.append(Submission(id=uuid.uuid4().hex[:12], question_id=question.id,
                assignment_id=draft.assignment_id, channel="tutorial", student_pseudonym=name, student_id=student_id,
                extracted_identity=draft.identity, transcription=Transcription(steps=raw.steps if raw else [], notes=answer.notes),
                confirmed_steps=steps, source_import_id=draft.id, source_pages=answer.source_pages,
                source_page=next(iter(answer.source_pages), None), source_page_count=draft.page_count))
        draft.answers = body.answers
        # Keep extracted identity as the audit record; authoritative identity is on each Submission.
        draft.submission_ids = [s.id for s in submissions]
        draft.stage = "complete"
        draft.revision += 1
        store.commit_tutorial_submissions(draft, submissions)
        return draft

    @router.post("/tutorial-imports/{import_id}/mark")
    @store.submission_transaction
    def mark_import(import_id: str) -> dict:
        draft = _draft(import_id, "complete")
        if draft.kind != "student" or not draft.submission_ids:
            raise HTTPException(409, "Confirm student segmentation before starting marking.")
        results = []
        for sid in draft.submission_ids:
            submission = store.load_submission(sid)
            if submission.marks is not None and submission.feedback is not None:
                results.append({"submission_id": sid, "question_id": submission.question_id, "marked": True, "error": None})
                continue
            try:
                mark_submission(sid)  # exactly the same existing verify/mark/feedback pipeline
                results.append({"submission_id": sid, "question_id": submission.question_id, "marked": True, "error": None})
            except (OfflineCacheMiss, AnthropicError, ValueError, RuntimeError, HTTPException) as exc:
                message = "No cached marking is available. Enable live mode or use cached input." if isinstance(exc, OfflineCacheMiss) else "Marking failed. Retry this question from Workbench or retry incomplete marking."
                results.append({"submission_id": sid, "question_id": submission.question_id, "marked": False, "error": message})
        return {"results": results, "complete": all(r["marked"] for r in results)}

    return router
