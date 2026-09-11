import { apiFetch, apiUrl } from "./api";
import type { TutorialImport } from "../types";

function upload(path: string, file: File, revision?: number) {
  const form = new FormData();
  form.append("file", file);
  if (revision !== undefined) form.append("revision", String(revision));
  return apiFetch<TutorialImport>(path, { method: "POST", body: form });
}

function confirm(draft: TutorialImport, phase: string, body: object) {
  return apiFetch<TutorialImport>(`/api/tutorial-imports/${draft.id}/confirm-${phase}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revision: draft.revision, ...body }),
  });
}

export const ingestionApi = {
  list: (assignmentId: string) => apiFetch<TutorialImport[]>(`/api/assignments/${encodeURIComponent(assignmentId)}/imports`),
  get: (id: string) => apiFetch<TutorialImport>(`/api/tutorial-imports/${id}`),
  questions: (assignmentId: string, file: File) => upload(`/api/assignments/${encodeURIComponent(assignmentId)}/imports/questions`, file),
  solutions: (draft: TutorialImport, file: File) => upload(`/api/tutorial-imports/${draft.id}/solutions`, file, draft.revision),
  student: (assignmentId: string, file: File) => upload(`/api/assignments/${encodeURIComponent(assignmentId)}/imports/student`, file),
  confirmQuestions: (draft: TutorialImport) => confirm(draft, "questions", { questions: draft.questions }),
  confirmSolutions: (draft: TutorialImport) => confirm(draft, "solutions", { questions: draft.questions, solutions: draft.solutions }),
  confirmAnswers: (draft: TutorialImport) => confirm(draft, "answers", { identity: draft.identity, answers: draft.answers }),
  mark: (id: string) => apiFetch<{ complete: boolean; results: { submission_id: string; question_id: string; marked: boolean; error: string | null }[] }>(`/api/tutorial-imports/${id}/mark`, { method: "POST" }),
  page: (id: string, page: number, solution = false) => apiUrl(`/api/tutorial-imports/${id}/pages/${page}?solution=${solution}`),
};
