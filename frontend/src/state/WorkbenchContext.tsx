import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "../lib/api";
import type { Question, Step, Submission } from "../types";

/** Ported from static/app.js's `state` object — the fields shared between
 * Setup and Confirm (question authoring's `qe*` fields live in
 * QuestionEditor's own local state instead, since they're scoped to that
 * dialog only). */
interface WorkbenchState {
  questions: Question[];
  currentQuestion: Question | null;
  submissionId: string | null;
  submission: Submission | null;
  uploadedImageUrl: string | null;
  localSteps: Step[];
  pendingUploadFile: File | null;
  uploadSourceType: "image" | "pdf" | null;
  uploadPageCount: number;
  uploadSelectedPage: number;
  uploadPreviewB64: string | null;
  uploadPreviewBusy: boolean;
  confirmBusy: boolean;
  confirmBusyMessage: string;
  confirmError: string | null;
  /** Editable identity fields shown on Confirm — pre-filled from whatever the
   * vision model read off the photo (if any), same trust boundary as
   * localSteps: nothing is authoritative until Confirm & Mark saves it. */
  localName: string;
  localStudentId: string;
}

const initialState: WorkbenchState = {
  questions: [],
  currentQuestion: null,
  submissionId: null,
  submission: null,
  uploadedImageUrl: null,
  localSteps: [],
  pendingUploadFile: null,
  uploadSourceType: null,
  uploadPageCount: 1,
  uploadSelectedPage: 1,
  uploadPreviewB64: null,
  uploadPreviewBusy: false,
  confirmBusy: false,
  confirmBusyMessage: "",
  confirmError: null,
  localName: "",
  localStudentId: "",
};

function problemsFrom(err: unknown): string[] {
  if (err instanceof ApiError) {
    const detail = err.body && err.body.detail;
    if (Array.isArray(detail)) return detail;
    return [detail || err.message || "Something went wrong."];
  }
  return [err instanceof Error ? err.message : "Something went wrong."];
}

function confirmErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const hint = err.body && err.body.hint;
    const detail = err.body && err.body.detail;
    if (hint) return `⚠ ${hint}` + (detail ? ` — ${detail}` : "");
    if (detail) return Array.isArray(detail) ? detail.join(" ") : String(detail);
  }
  return err instanceof Error ? err.message : "Something went wrong.";
}

function useWorkbenchValue() {
  const [state, setState] = useState<WorkbenchState>(initialState);
  const sessionCount = useRef(0);

  const patch = useCallback((p: Partial<WorkbenchState>) => setState((s) => ({ ...s, ...p })), []);

  const loadQuestions = useCallback(async () => {
    const questions: Question[] = await api.listQuestions();
    setState((s) => ({ ...s, questions }));
    return questions;
  }, []);

  const selectQuestion = useCallback((id: string) => {
    setState((s) => {
      const question = s.questions.find((q) => q.id === id) || null;
      return { ...s, currentQuestion: question };
    });
  }, []);

  /** The typed student name, or an auto-incrementing fallback if left blank. */
  const nextStudentPseudonym = useCallback((typedName: string) => {
    sessionCount.current += 1;
    return typedName.trim() || `Student ${sessionCount.current}`;
  }, []);

  const beginWithUpload = useCallback(
    async (file: File, studentName: string, onNavigate: () => void) => {
      const question = state.currentQuestion;
      if (!question) return;

      const looksLikePdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name || "");
      const sub: Submission = await api.createSubmission(question.id, nextStudentPseudonym(studentName));

      if (!looksLikePdf) {
        const url = URL.createObjectURL(file);
        patch({
          submissionId: sub.id,
          submission: sub,
          localSteps: [],
          localName: sub.student_pseudonym || "",
          localStudentId: sub.student_id || "",
          uploadedImageUrl: url,
          pendingUploadFile: null,
          uploadSourceType: "image",
          uploadPageCount: 1,
          uploadSelectedPage: 1,
          uploadPreviewB64: null,
          confirmError: null,
        });
        onNavigate();
        // fire and forget-ish: transcribe immediately, mirroring the old flow
        setState((s) => ({ ...s, confirmBusy: true, confirmBusyMessage: "Transcribing the image…" }));
        try {
          const updated = await api.transcribe(sub.id, file, 1);
          setState((s) => ({
            ...s,
            submission: updated,
            localSteps: ((updated.transcription && updated.transcription.steps) || []).map((st: Step) => ({
              ...st,
            })),
            localName: updated.student_pseudonym || s.localName,
            localStudentId: updated.student_id || s.localStudentId,
          }));
          if ((updated.confirmed_steps || []).length) {
            patch({ confirmBusyMessage: "Generating draft score and feedback…" });
            const marked = await api.mark(sub.id);
            patch({ submission: marked });
          }
        } catch (err) {
          patch({ confirmError: confirmErrorMessage(err) });
        } finally {
          patch({ confirmBusy: false });
        }
        return;
      }

      patch({
        submissionId: sub.id,
        submission: sub,
        localSteps: [],
        localName: sub.student_pseudonym || "",
        localStudentId: sub.student_id || "",
        uploadedImageUrl: null,
        pendingUploadFile: file,
        uploadSourceType: "pdf",
        uploadPageCount: 1,
        uploadSelectedPage: 1,
        uploadPreviewB64: null,
        confirmError: null,
      });
      onNavigate();
      setState((s) => ({ ...s, confirmBusy: true, confirmBusyMessage: "Reading PDF…" }));
      try {
        const inspection = await api.inspectUpload(file);
        patch({ uploadPageCount: inspection.page_count });
        await loadPagePreviewInner(file, 1);
      } catch (err) {
        patch({ confirmError: confirmErrorMessage(err) });
      } finally {
        patch({ confirmBusy: false });
      }
    },
    [state.currentQuestion, patch, nextStudentPseudonym]
  );

  const loadPagePreviewInner = async (file: File, page: number) => {
    setState((s) => ({ ...s, uploadPreviewBusy: true }));
    try {
      const preview = await api.previewUpload(file, page);
      patch({
        uploadSelectedPage: preview.page,
        uploadPageCount: preview.page_count,
        uploadPreviewB64: preview.preview_b64,
      });
    } catch (err) {
      patch({ confirmError: confirmErrorMessage(err) });
    } finally {
      patch({ uploadPreviewBusy: false });
    }
  };

  const loadPagePreview = useCallback(
    async (page: number) => {
      if (!state.pendingUploadFile) return;
      await loadPagePreviewInner(state.pendingUploadFile, page);
    },
    [state.pendingUploadFile]
  );

  const transcribeStagedFile = useCallback(
    async (page: number) => {
      const file = state.pendingUploadFile;
      if (!file || !state.submissionId) return;
      patch({ confirmBusy: true, confirmBusyMessage: "Transcribing the image…", confirmError: null });
      try {
        const updated = await api.transcribe(state.submissionId, file, page);
        patch({
          submission: updated,
          localSteps: ((updated.transcription && updated.transcription.steps) || []).map((s: Step) => ({ ...s })),
          localName: updated.student_pseudonym || state.localName,
          localStudentId: updated.student_id || state.localStudentId,
        });
        if ((updated.confirmed_steps || []).length) {
          patch({ confirmBusyMessage: "Generating draft score and feedback…" });
          const marked = await api.mark(state.submissionId);
          patch({ submission: marked });
        }
      } catch (err) {
        patch({ confirmError: confirmErrorMessage(err) });
      } finally {
        patch({ confirmBusy: false });
      }
    },
    [state.pendingUploadFile, state.submissionId, state.localName, state.localStudentId, patch]
  );

  const beginManualEntry = useCallback(
    async (
      prefill: { latex: string; confidence?: "high" | "low" }[],
      studentName: string,
      onNavigate: () => void,
      questionOverride?: Question
    ) => {
      // The sample flow may switch the selected question and start immediately.
      // React state updates are asynchronous, so accept the already-resolved
      // question instead of accidentally creating a submission against the
      // previously selected one.
      const question = questionOverride || state.currentQuestion;
      if (!question) return;
      const sub: Submission = await api.createSubmission(question.id, nextStudentPseudonym(studentName));
      patch({
        submissionId: sub.id,
        submission: sub,
        uploadedImageUrl: null,
        pendingUploadFile: null,
        uploadSourceType: null,
        uploadPageCount: 1,
        uploadSelectedPage: 1,
        uploadPreviewB64: null,
        localSteps: prefill.length
          ? prefill.map((s, i) => ({ index: i + 1, latex: s.latex, confidence: s.confidence || "high" }))
          : [{ index: 1, latex: "", confidence: "high" }],
        localName: sub.student_pseudonym || "",
        localStudentId: sub.student_id || "",
        confirmError: null,
      });
      onNavigate();
      if (prefill.length) {
        patch({ confirmBusy: true, confirmBusyMessage: "Generating draft score and feedback…" });
        try {
          await api.updateSteps(
            sub.id,
            prefill.map((s, i) => ({ index: i + 1, latex: s.latex, confidence: s.confidence || "high" }))
          );
          const marked = await api.mark(sub.id);
          patch({ submission: marked });
        } catch (err) {
          patch({ confirmError: confirmErrorMessage(err) });
        } finally {
          patch({ confirmBusy: false });
        }
      }
    },
    [state.currentQuestion, patch, nextStudentPseudonym]
  );

  const setLocalName = useCallback((name: string) => setState((s) => ({ ...s, localName: name })), []);
  const setLocalStudentId = useCallback(
    (studentId: string) => setState((s) => ({ ...s, localStudentId: studentId })),
    []
  );

  const addStep = useCallback(() => {
    setState((s) => ({
      ...s,
      localSteps: [...s.localSteps, { index: s.localSteps.length + 1, latex: "", confidence: "high" }],
    }));
  }, []);

  const updateStepLatex = useCallback((idx: number, latex: string) => {
    setState((s) => {
      const localSteps = s.localSteps.slice();
      localSteps[idx] = { ...localSteps[idx], latex };
      return { ...s, localSteps };
    });
  }, []);

  const removeStep = useCallback((idx: number) => {
    setState((s) => ({ ...s, localSteps: s.localSteps.filter((_, i) => i !== idx) }));
  }, []);

  const confirmAndMark = useCallback(
    async (onDone?: () => void) => {
      if (!state.submissionId) return;
      patch({
        confirmError: null,
        confirmBusy: true,
        confirmBusyMessage: "Saving confirmed steps…",
        submission: state.submission
          ? { ...state.submission, verification: null, marks: null, feedback: null, practice: [] }
          : null,
      });
      const payload = state.localSteps.map((s, i) => ({ index: i + 1, latex: s.latex, confidence: s.confidence || "high" }));
      try {
        const saved = await api.updateSteps(state.submissionId, payload);
        patch({ submission: saved });
        await api.updateIdentity(state.submissionId, state.localName.trim() || null, state.localStudentId.trim() || null);
        patch({ confirmBusyMessage: "Refreshing draft score and feedback…" });
        const marked = await api.mark(state.submissionId);
        patch({ submission: marked });
        onDone?.();
      } catch (err) {
        patch({ confirmError: confirmErrorMessage(err) });
      } finally {
        patch({ confirmBusy: false });
      }
    },
    [state.submissionId, state.localSteps, state.localName, state.localStudentId, patch]
  );

  const reloadQuestions = useCallback(
    async (preferredId: string | null) => {
      const questions = await loadQuestions();
      const target = preferredId && questions.some((q) => q.id === preferredId) ? preferredId : questions[0]?.id || null;
      if (target) {
        const question = questions.find((q) => q.id === target) || null;
        patch({ currentQuestion: question });
      } else {
        patch({ currentQuestion: null });
      }
    },
    [loadQuestions, patch]
  );

  const setSubmission = useCallback((submission: WorkbenchState["submission"]) => patch({ submission }), [patch]);

  return {
    state,
    loadQuestions,
    selectQuestion,
    beginWithUpload,
    beginManualEntry,
    loadPagePreview,
    transcribeStagedFile,
    setSubmission,
    setLocalName,
    setLocalStudentId,
    addStep,
    updateStepLatex,
    removeStep,
    confirmAndMark,
    reloadQuestions,
    problemsFrom,
  };
}

type WorkbenchValue = ReturnType<typeof useWorkbenchValue>;
const WorkbenchCtx = createContext<WorkbenchValue | null>(null);

export function WorkbenchProvider({ children }: { children: ReactNode }) {
  const value = useWorkbenchValue();
  return <WorkbenchCtx.Provider value={value}>{children}</WorkbenchCtx.Provider>;
}

export function useWorkbench() {
  const ctx = useContext(WorkbenchCtx);
  if (!ctx) throw new Error("useWorkbench must be used within WorkbenchProvider");
  return ctx;
}
