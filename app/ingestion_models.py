"""Import drafts are deliberately separate from validated, markable Questions."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models import Criterion, IdentityExtraction, Step, Transcription


class QuestionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(default="", max_length=100)
    prompt: str = Field(default="", max_length=12000)
    source_pages: list[int] = Field(default_factory=list, max_length=20)
    confidence: Literal["high", "low"] = "high"
    notes: str = ""
    question_id: str | None = None
    variable: str = "x"
    topic_tag: str = "quadratics"
    model_solution_steps: list[str] = Field(default_factory=list, max_length=200)
    criteria: list[Criterion] = Field(default_factory=list, max_length=30)
    solution_source_pages: list[int] = Field(default_factory=list, max_length=20)
    solution_transcription: Transcription | None = None
    problems: list[str] = Field(default_factory=list)


class MappedWorking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(default="", max_length=100)
    block_id: str = ""
    question_id: str | None = None
    source_pages: list[int] = Field(default_factory=list, max_length=20)
    confidence: Literal["high", "low"] = "high"
    status: Literal["detected", "uncertain", "not_detected"] = "detected"
    steps: list[Step] = Field(default_factory=list, max_length=200)
    criteria: list[Criterion] = Field(default_factory=list, max_length=30)
    notes: str = ""
    # The mapping and its transcription must be acknowledged independently of
    # final marking review, which remains Submission.reviewed.
    confirmed: bool = False


class QuestionDetection(BaseModel):
    title: str = ""
    questions: list[QuestionDraft] = Field(max_length=100)
    warnings: list[str] = Field(default_factory=list)


class SolutionDetection(BaseModel):
    solutions: list[MappedWorking] = Field(max_length=100)
    warnings: list[str] = Field(default_factory=list)


class AnswerDetection(BaseModel):
    identity: IdentityExtraction = Field(default_factory=IdentityExtraction)
    answers: list[MappedWorking] = Field(
        max_length=100,
        description=(
            "Required top-level array of student answer blocks. Return an empty array when no answer "
            "blocks are visible; never omit, rename, null, or wrap this array."
        ),
    )
    warnings: list[str] = Field(default_factory=list)


class TutorialImport(BaseModel):
    id: str
    assignment_id: str
    kind: Literal["setup", "student"]
    stage: Literal["questions", "solutions", "answers", "complete"]
    revision: int = 0
    filename: str
    page_count: int
    solution_page_count: int = 0
    document_hash: str
    solution_document_hash: str | None = None
    title: str = ""
    questions: list[QuestionDraft] = Field(default_factory=list)
    solutions: list[MappedWorking] = Field(default_factory=list)
    answers: list[MappedWorking] = Field(default_factory=list)
    identity: IdentityExtraction = Field(default_factory=IdentityExtraction)
    warnings: list[str] = Field(default_factory=list)
    submission_ids: list[str] = Field(default_factory=list)
    # Snapshot detects changed question context between extraction/confirmation.
    question_fingerprint: str = ""


class ConfirmQuestions(BaseModel):
    revision: int
    questions: list[QuestionDraft] = Field(min_length=1, max_length=100)


class ConfirmSolutions(BaseModel):
    revision: int
    questions: list[QuestionDraft] = Field(min_length=1, max_length=100)
    solutions: list[MappedWorking] = Field(min_length=1, max_length=100)


class ConfirmAnswers(BaseModel):
    revision: int
    identity: IdentityExtraction
    answers: list[MappedWorking] = Field(min_length=1, max_length=100)
