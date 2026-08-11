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


# ---------- Transcription ----------
# Declared before Question because Question carries a Transcription as the
# audit record of a photographed model solution.


class Step(BaseModel):
    index: int = Field(ge=1)
    latex: str
    confidence: Confidence = "high"
    edited_by_human: bool = False


class Transcription(BaseModel):
    steps: list[Step]
    notes: str = ""


class IdentityExtraction(BaseModel):
    """A name/student id read off a student's photographed page, if any.

    Raw audit record only - never authoritative on its own. Mirrors the
    transcription/confirmed_steps split: `Submission.student_pseudonym` and
    `Submission.student_id` are what's actually used, and start out equal to
    this extraction but remain lecturer-editable right up to confirmation,
    the same trust boundary already applied to transcribed steps.
    """

    name: str | None = None
    student_id: str | None = None
    confidence: Confidence = "high"


class Question(BaseModel):
    id: str
    prompt: str
    model_solution_steps: list[str]
    variable: str = "x"
    topic_tag: str = "quadratics"
    criteria: list[Criterion]

    # Provenance: a question's model solution originates from a photograph of
    # the lecturer's own handwritten working. All optional with defaults, so the
    # seeded questions and any existing data/questions.json overlay still
    # validate with no migration.
    solution_image_filename: str | None = None
    solution_source_page: int | None = None
    # The RAW transcription, before the lecturer corrected it. An audit record,
    # never a source of truth: marking reads model_solution_steps and nothing
    # else. Its value is the diff - comparing these steps against
    # model_solution_steps shows exactly which lines a human changed, which is
    # the only real evidence of review. solution_image_filename alone proves
    # nothing, since a photograph of a napkin would satisfy the editor's gate.
    solution_transcription: Transcription | None = None


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
    # Optional with defaults so submissions saved before framings existed
    # still validate - no migration needed.
    question_type: str = "bare"
    framing_id: str = "bare"
    # The roots valid in this framing's context. A word problem may legitimately
    # exclude one (a length cannot be negative); rejected_note says why.
    admissible_roots: list[str] = Field(default_factory=list)
    rejected_note: str = ""


# ---------- Cohort view ----------


class ClassMisconceptionCount(BaseModel):
    tag: str
    name: str
    count: int = Field(ge=1)


class ClassStudentRow(BaseModel):
    pseudonym: str
    question_id: str
    mark: int = Field(ge=0)
    max: int = Field(ge=0)
    top_misconception: str | None = None


class ClassSummary(BaseModel):
    """The cohort view, computed from real submissions wherever possible.

    `source` distinguishes the two honestly: "computed" means these numbers
    were derived from submissions actually marked on this machine; "sample"
    means the seeded illustrative fixture, served only when no submissions
    exist at all (a fresh clone has none - data/submissions/ is gitignored).
    """

    source: Literal["computed", "sample"] = "computed"
    source_note: str = ""
    submission_count: int = Field(default=0, ge=0)
    cohort_size: int = Field(default=0, ge=0)
    marked: int = Field(default=0, ge=0)
    mean_percentage: int = Field(default=0, ge=0, le=100)
    misconception_counts: list[ClassMisconceptionCount] = Field(default_factory=list)
    students: list[ClassStudentRow] = Field(default_factory=list)
    recommendation: str = ""

    @model_validator(mode="after")
    def internally_consistent(self) -> "ClassSummary":
        """Make an inconsistent summary unrepresentable.

        The fixture this replaced claimed 31 students in a 6-row table, with a
        mean that followed from neither. Enforcing the arithmetic in the type
        means such a thing cannot be constructed, computed or deserialised.
        """
        if self.marked > self.cohort_size:
            raise ValueError(
                f"marked {self.marked} exceeds cohort_size {self.cohort_size}"
            )
        if len(self.students) != self.marked:
            raise ValueError(
                f"{len(self.students)} student rows but marked={self.marked}"
            )
        for row in self.students:
            if row.mark > row.max:
                raise ValueError(
                    f"{row.pseudonym}: mark {row.mark} exceeds max {row.max}"
                )
        return self


# ---------- The persisted submission ----------


class Submission(BaseModel):
    id: str
    question_id: str
    image_filename: str | None = None
    source_page: int | None = None
    source_page_count: int | None = None
    transcription: Transcription | None = None
    confirmed_steps: list[Step] | None = None
    verification: VerificationReport | None = None
    marks: MarkProposal | None = None
    feedback: Feedback | None = None
    practice: list[PracticeQuestion] = Field(default_factory=list)
    student_pseudonym: str = "Student A"
    student_id: str | None = None
    # Raw audit record of what the vision model read off the page, if a photo
    # was uploaded - see IdentityExtraction. None for manual entry (no photo)
    # and for submissions created before this field existed.
    extracted_identity: IdentityExtraction | None = None
