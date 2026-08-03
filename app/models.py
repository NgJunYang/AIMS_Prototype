from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

Confidence = Literal["high", "low"]

Divergence = Literal[
    "lost_roots",        # solution set shrank: an answer was discarded
    "gained_roots",      # solution set grew: a spurious answer appeared
    "different_roots",   # neither subset nor superset: an algebra error
    "unparseable",       # this line could not be turned into mathematics
]


# ---------- Assignment definition (seed data) ----------


class Criterion(BaseModel):
    id: str
    max: int = Field(ge=0)
    description: str


class Question(BaseModel):
    id: str
    prompt: str
    model_solution_steps: list[str]
    variable: str = "x"
    topic_tag: str = "quadratics"
    criteria: list[Criterion]


# ---------- Transcription ----------


class Step(BaseModel):
    index: int = Field(ge=1)
    latex: str
    confidence: Confidence = "high"
    edited_by_human: bool = False


class Transcription(BaseModel):
    steps: list[Step]
    notes: str = ""


# ---------- Verification (SymPy, ground truth) ----------


class StepVerification(BaseModel):
    index: int
    parsed: bool
    solutions: list[str] = Field(default_factory=list)
    equivalent_to_previous: bool | None = None
    divergence: Divergence | None = None
    lost_roots: list[str] = Field(default_factory=list)
    gained_roots: list[str] = Field(default_factory=list)
    note: str = ""


class VerificationReport(BaseModel):
    steps: list[StepVerification]
    final_answer_correct: bool
    # False when the answer was never established: the student's last line did
    # not parse (or was an identity), or the model solution itself did not
    # parse. Distinguishes 'the answer is wrong' from 'we cannot say'.
    final_answer_verified: bool = True
    model_solutions: list[str] = Field(default_factory=list)
    candidate_misconceptions: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def first_divergence_index(self) -> int | None:
        for step in self.steps:
            if step.equivalent_to_previous is False:
                return step.index
        return None

    @computed_field
    @property
    def all_steps_parsed(self) -> bool:
        return all(step.parsed for step in self.steps)


# ---------- Marking ----------


class CriterionMark(BaseModel):
    criterion_id: str
    proposed: int = Field(ge=0)
    max: int = Field(ge=0)
    justification: str
    evidence_step: int | None = None
    overridden: bool = False

    @model_validator(mode="after")
    def proposed_within_max(self) -> "CriterionMark":
        if self.proposed > self.max:
            raise ValueError(
                f"proposed {self.proposed} exceeds max {self.max} for {self.criterion_id}"
            )
        return self


class MarkProposal(BaseModel):
    criteria: list[CriterionMark]
    misconceptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def total_proposed(self) -> int:
        return sum(c.proposed for c in self.criteria)

    @computed_field
    @property
    def total_max(self) -> int:
        return sum(c.max for c in self.criteria)


# ---------- Feedback and practice ----------


class Feedback(BaseModel):
    what_went_well: str
    what_went_wrong: str
    how_to_improve: str
    references: list[str] = Field(default_factory=list)


class PracticeQuestion(BaseModel):
    prompt_latex: str
    answer_latex: str
    misconception_tag: str
    template_id: str


# ---------- The persisted submission ----------


class Submission(BaseModel):
    id: str
    question_id: str
    image_filename: str | None = None
    transcription: Transcription | None = None
    confirmed_steps: list[Step] | None = None
    verification: VerificationReport | None = None
    marks: MarkProposal | None = None
    feedback: Feedback | None = None
    practice: list[PracticeQuestion] = Field(default_factory=list)
    student_pseudonym: str = "Student A"
