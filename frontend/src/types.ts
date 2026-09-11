export type Confidence = "high" | "low";

export interface Criterion {
  id: string;
  max: number;
  description: string;
}

export interface Step {
  index: number;
  latex: string;
  confidence: Confidence;
}

export interface SolutionTranscription {
  steps: { latex: string; confidence: Confidence }[];
  notes?: string | null;
}

export interface Question {
  id: string;
  label?: string | null;
  source_import_id?: string | null;
  source_pages?: number[];
  solution_source_pages?: number[];
  prompt: string;
  variable: string;
  topic_tag: string;
  model_solution_steps: string[];
  criteria: Criterion[];
  solution_image_filename?: string | null;
  solution_source_page?: number | null;
  solution_transcription?: SolutionTranscription | null;
}

export interface StepVerification {
  index: number;
  parsed: boolean;
  solutions: string[];
  equivalent_to_previous?: boolean | null;
  divergence?: string | null;
  lost_roots?: string[];
  gained_roots?: string[];
}

export interface Verification {
  steps: StepVerification[];
  final_answer_correct: boolean;
  final_answer_verified: boolean;
  model_solutions: string[];
  candidate_misconceptions: string[];
  [key: string]: unknown;
}

export interface CriterionMark {
  criterion_id: string;
  proposed: number;
  suggested?: number | null;
  max: number;
  justification: string;
  evidence_step?: number | null;
  overridden?: boolean;
}

export interface Marks {
  criteria: CriterionMark[];
  total_proposed?: number;
  total_max?: number;
  misconceptions?: string[];
  warnings?: string[];
  [key: string]: unknown;
}

export interface Feedback {
  what_went_well: string;
  what_went_wrong: string;
  how_to_improve: string;
  references: string[];
}

export interface IdentityExtraction {
  name: string | null;
  student_id: string | null;
  confidence: Confidence;
}

export interface Submission {
  id: string;
  source_import_id?: string | null;
  source_pages?: number[];
  question_id: string;
  assignment_id?: string | null;
  student_pseudonym?: string;
  student_id?: string | null;
  channel?: "tutorial" | "test";
  published?: boolean;
  reviewed?: boolean;
  review_invalidated?: boolean;
  /** Raw audit record of what the vision model read off the page, if a photo
   * was uploaded. Never authoritative on its own — see student_pseudonym/student_id. */
  extracted_identity?: IdentityExtraction | null;
  image_filename?: string | null;
  source_page?: number | null;
  source_page_count?: number | null;
  transcription?: { steps: Step[]; notes?: string | null } | null;
  confirmed_steps?: Step[] | null;
  verification?: Verification | null;
  marks?: Marks | null;
  feedback?: Feedback | null;
  misconceptions?: string[] | null;
  practice?: unknown;
  [key: string]: unknown;
}

export interface SubmissionSummary {
  id: string;
  question_id: string;
  student_pseudonym: string;
  student_id: string | null;
  assignment_id: string | null;
  channel: "test" | "tutorial";
  published: boolean;
  marked: boolean;
  total_proposed: number | null;
  total_max: number | null;
}

export type FeedbackDraft = Pick<Feedback, "what_went_well" | "what_went_wrong" | "how_to_improve">;

export interface PublishReview {
  identity: { name: string; student_id: string | null };
  feedback: FeedbackDraft;
}

export interface AssignmentReviewStatus {
  assignment_id: string;
  assignment_title: string;
  student_pseudonym: string;
  student_id: string | null;
  total_questions: number;
  reviewed_count: number;
  ready_to_publish: boolean;
  published: boolean;
  questions: {
    question_id: string;
    submission_id: string | null;
    marked: boolean;
    has_feedback: boolean;
    reviewed: boolean;
    published: boolean;
    problems: string[];
  }[];
}

export interface ApiErrorLike {
  message: string;
  status?: number;
  body?: { detail?: string | string[]; hint?: string; error?: string };
}

export interface ImportQuestion {
  question_id: string | null;
  label: string;
  prompt: string;
  variable: string;
  topic_tag: string;
  source_pages: number[];
  confidence: "high" | "low";
  notes: string;
  problems: string[];
}

export interface ImportWorking {
  block_id: string;
  question_id: string | null;
  label: string;
  source_pages: number[];
  confidence: "high" | "low";
  status: "detected" | "uncertain" | "not_detected";
  steps: Step[];
  criteria: Criterion[];
  notes: string;
  confirmed: boolean;
}

export interface TutorialImport {
  id: string;
  assignment_id: string;
  kind: "setup" | "student";
  stage: "questions" | "solutions" | "answers" | "complete";
  revision: number;
  filename: string;
  page_count: number;
  solution_page_count: number;
  title: string;
  questions: ImportQuestion[];
  solutions: ImportWorking[];
  answers: ImportWorking[];
  identity: IdentityExtraction;
  warnings: string[];
  submission_ids: string[];
}
