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
  justification: string;
  evidence_step?: number | null;
  overridden?: number | null;
}

export interface Marks {
  criteria: CriterionMark[];
  total_awarded?: number;
  total_max?: number;
  [key: string]: unknown;
}

export interface Submission {
  id: string;
  question_id: string;
  student_pseudonym?: string;
  image_filename?: string | null;
  source_page?: number | null;
  source_page_count?: number | null;
  transcription?: { steps: Step[]; notes?: string | null } | null;
  confirmed_steps?: Step[] | null;
  verification?: Verification | null;
  marks?: Marks | null;
  feedback?: string | null;
  misconceptions?: string[] | null;
  practice?: unknown;
  [key: string]: unknown;
}

export interface ApiErrorLike {
  message: string;
  status?: number;
  body?: { detail?: string | string[]; hint?: string; error?: string };
}
