// Mechanical port of static/app.js's `apiUrl`/`apiFetch`/`api` — same
// endpoints, same signatures. Fidelity matters more than idiomatic-ness here.

export function apiUrl(path: string): string {
  const base = String((window as any).AIMS_API_BASE || "")
    .trim()
    .replace(/\/+$/, "");
  return `${base}${path}`;
}

export class ApiError extends Error {
  status: number;
  body: any;
  constructor(message: string, status: number, body: any) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export async function apiFetch<T = any>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), options);
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    // no/invalid JSON body — leave body null
  }
  if (!res.ok) {
    const message = (body && (body.detail || body.error)) || `Request failed (${res.status})`;
    throw new ApiError(message, res.status, body || {});
  }
  return body as T;
}

export const api = {
  listQuestions: () => apiFetch("/api/questions"),
  getQuestion: (id: string) => apiFetch(`/api/questions/${encodeURIComponent(id)}`),
  createSubmission: (questionId: string, studentPseudonym: string) =>
    apiFetch("/api/submissions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: questionId, student_pseudonym: studentPseudonym }),
    }),
  transcribe: (submissionId: string, file: File, page = 1) => {
    const form = new FormData();
    form.append("file", file);
    form.append("page", String(page));
    return apiFetch(`/api/submissions/${submissionId}/transcribe`, { method: "POST", body: form });
  },
  inspectUpload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiFetch("/api/uploads/inspect", { method: "POST", body: form });
  },
  previewUpload: (file: File, page: number) => {
    const form = new FormData();
    form.append("file", file);
    form.append("page", String(page));
    return apiFetch("/api/uploads/preview", { method: "POST", body: form });
  },
  updateSteps: (submissionId: string, steps: any[]) =>
    apiFetch(`/api/submissions/${submissionId}/steps`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps }),
    }),
  updateIdentity: (submissionId: string, name: string | null, studentId: string | null) =>
    apiFetch(`/api/submissions/${submissionId}/identity`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, student_id: studentId }),
    }),
  mark: (submissionId: string) => apiFetch(`/api/submissions/${submissionId}/mark`, { method: "POST" }),
  regeneratePractice: (submissionId: string, questionType: string) =>
    apiFetch(`/api/submissions/${submissionId}/practice`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_type: questionType }),
    }),
  override: (submissionId: string, criterionId: string, proposed: number) =>
    apiFetch(`/api/submissions/${submissionId}/override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ criterion_id: criterionId, proposed }),
    }),
  classSummary: () => apiFetch("/api/class/summary"),
  questionTemplate: () => apiFetch("/api/question-template"),
  validateQuestion: (question: any) =>
    apiFetch("/api/questions/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(question),
    }),
  createQuestion: (question: any) =>
    apiFetch("/api/questions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(question),
    }),
  updateQuestion: (id: string, question: any) =>
    apiFetch(`/api/questions/${encodeURIComponent(id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(question),
    }),
  deleteQuestion: (id: string) => apiFetch(`/api/questions/${encodeURIComponent(id)}`, { method: "DELETE" }),
  transcribeSolution: (file: File, page = 1) => {
    const form = new FormData();
    form.append("file", file);
    form.append("page", String(page));
    return apiFetch("/api/questions/solution-transcribe", { method: "POST", body: form });
  },
};
