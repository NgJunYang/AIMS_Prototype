import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, apiUrl, ApiError } from "../lib/api";
import type { FeedbackDraft, Question, Step, Submission } from "../types";

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
  /** A quiet re-mark triggered automatically a beat after the lecturer stops
   * editing the transcription — distinct from confirmBusy, which is the loud
   * manual path that blanks the panel while it runs. */
  autoRefreshing: boolean;
  /** Assignment tutorials and graded tests require explicit publication. */
  channel: "tutorial" | "test";
  /** The assignment this marking session belongs to, if any. */
  assignmentId: string | null;
  /** Editable identity fields shown on Confirm — pre-filled from whatever the
   * vision model read off the photo (if any), same trust boundary as
   * localSteps: nothing is authoritative until Confirm & Mark saves it. */
  localName: string;
  localStudentId: string;
  feedbackDraft: FeedbackDraft | null;
  reviewBusy: boolean;
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
  autoRefreshing: false,
  channel: "test",
  assignmentId: null,
  localName: "",
  localStudentId: "",
  feedbackDraft: null,
  reviewBusy: false,
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
  const mutationBusy = useRef(false);

  const patch = useCallback((p: Partial<WorkbenchState>) => setState((s) => ({ ...s, ...p })), []);

  const loadQuestions = useCallback(async () => {
    const questions: Question[] = await api.listQuestions();
    setState((s) => ({
      ...s,
      questions,
      currentQuestion: questions.find((q) => q.id === s.currentQuestion?.id) || questions[0] || null,
    }));
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
      const sub: Submission = await api.createSubmission(
        question.id,
        nextStudentPseudonym(studentName),
        state.channel,
        state.assignmentId
      );

      if (!looksLikePdf) {
        const url = URL.createObjectURL(file);
        patch({
          submissionId: sub.id,
          submission: sub,
          feedbackDraft: null,
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
        feedbackDraft: null,
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
    [state.currentQuestion, state.channel, state.assignmentId, patch, nextStudentPseudonym]
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
      const sub: Submission = await api.createSubmission(
        question.id,
        nextStudentPseudonym(studentName),
        state.channel,
        state.assignmentId
      );
      patch({
        submissionId: sub.id,
        submission: sub,
        feedbackDraft: null,
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
    [state.currentQuestion, state.channel, state.assignmentId, patch, nextStudentPseudonym]
  );

  const setChannel = useCallback(
    (channel: "tutorial" | "test") => setState((s) => ({ ...s, channel })),
    []
  );
  const setAssignment = useCallback(
    (assignmentId: string | null, channel?: "tutorial" | "test") =>
      setState((s) => ({ ...s, assignmentId, channel: channel ?? s.channel })),
    []
  );
  const setLocalName = useCallback((name: string) => setState((s) => ({ ...s, localName: name })), []);
  const setLocalStudentId = useCallback(
    (studentId: string) => setState((s) => ({ ...s, localStudentId: studentId })),
    []
  );

  const setFeedbackDraft = useCallback((draft: FeedbackDraft | null) => patch({ feedbackDraft: draft }), [patch]);

  // Keep pending review edits separate from responses returned by score,
  // practice and publication operations. Those responses must not erase text.
  const saveReview = useCallback(async (action: "identity" | "feedback" | "publish" | "review") => {
    if (!state.submissionId || mutationBusy.current || state.confirmBusy || state.autoRefreshing) return false;
    if ((action === "review" || action === "publish") &&
      JSON.stringify(state.localSteps.map((s) => s.latex)) !== JSON.stringify((state.submission?.confirmed_steps || []).map((s) => s.latex))) {
      throw new Error("Wait for the changed working to be marked before completing review.");
    }
    const id = state.submissionId;
    const feedback = state.feedbackDraft || state.submission?.feedback;
    const name = state.localName.trim();
    if (action !== "feedback" && !name) throw new Error("Enter a student name before saving.");
    if (action !== "identity" && !feedback) throw new Error("Generate feedback before saving the review.");
    mutationBusy.current = true;
    patch({ reviewBusy: true });
    try {
      const updated: Submission = action === "publish" || action === "review"
        ? await api[action](id, {
            identity: { name, student_id: state.localStudentId.trim() || null },
            feedback: feedback!,
          })
        : action === "feedback"
          ? await api.updateFeedback(id, feedback!)
          : await api.updateIdentity(id, name, state.localStudentId.trim() || null);
      setState((s) => s.submissionId !== id ? s : {
        ...s,
        submission: updated,
        feedbackDraft: action !== "identity" && s.feedbackDraft === state.feedbackDraft ? null : s.feedbackDraft,
      });
      return true;
    } finally {
      mutationBusy.current = false;
      patch({ reviewBusy: false });
    }
  }, [state, patch]);

  // Score saves share the review lock: clicking Review immediately after a
  // score field loses focus must wait for that override to finish saving.
  const saveScore = useCallback(async (criterionId?: string, proposed?: number) => {
    if (!state.submissionId || mutationBusy.current || state.confirmBusy || state.autoRefreshing) {
      throw new Error("Wait for the current assessment save to finish.");
    }
    mutationBusy.current = true;
    patch({ reviewBusy: true });
    try {
      const updated: Submission = criterionId === undefined
        ? await api.resetOverrides(state.submissionId)
        : await api.override(state.submissionId, criterionId, proposed!);
      patch({ submission: updated });
    } finally {
      mutationBusy.current = false;
      patch({ reviewBusy: false });
    }
  }, [state.submissionId, state.confirmBusy, state.autoRefreshing, patch]);

  const regenerateFeedback = useCallback(async () => {
    if (!state.submissionId || mutationBusy.current || state.confirmBusy || state.autoRefreshing) return false;
    const feedback = state.submission?.feedback;
    if (state.feedbackDraft && (!feedback ||
      (["what_went_well", "what_went_wrong", "how_to_improve"] as const).some((key) => state.feedbackDraft![key] !== feedback[key]))) {
      throw new Error("Save or discard feedback edits before regenerating.");
    }
    if (JSON.stringify(state.localSteps.map((s) => s.latex)) !== JSON.stringify((state.submission?.confirmed_steps || []).map((s) => s.latex))) {
      throw new Error("Wait for the changed working to be marked before regenerating feedback.");
    }
    const id = state.submissionId;
    mutationBusy.current = true;
    patch({ reviewBusy: true });
    try {
      const updated = await api.regenerateFeedback(id);
      setState((s) => s.submissionId !== id ? s : { ...s, submission: updated, feedbackDraft: null });
      return true;
    } finally {
      mutationBusy.current = false;
      patch({ reviewBusy: false });
    }
  }, [state, patch]);

  const publishTutorial = useCallback(async (publish: boolean) => {
    if (!state.submissionId || mutationBusy.current || state.confirmBusy || state.autoRefreshing) return null;
    if (publish && (state.feedbackDraft !== null ||
      state.localName.trim() !== state.submission?.student_pseudonym ||
      state.localStudentId.trim() !== (state.submission?.student_id || "") ||
      JSON.stringify(state.localSteps.map((s) => s.latex)) !== JSON.stringify((state.submission?.confirmed_steps || []).map((s) => s.latex)))) {
      throw new Error("Save and review the pending changes before publishing tutorial results.");
    }
    mutationBusy.current = true;
    patch({ reviewBusy: true });
    try {
      const status = await (publish ? api.publishAssignment : api.unpublishAssignment)(state.submissionId);
      patch({ submission: await api.getSubmission(state.submissionId) });
      return status;
    } finally {
      mutationBusy.current = false;
      patch({ reviewBusy: false });
    }
  }, [state, patch]);

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
    async (onDone?: () => void, opts?: { silent?: boolean }) => {
      if (!state.submissionId || mutationBusy.current) return;
      mutationBusy.current = true;
      const silent = opts?.silent ?? false;
      // Silent (auto) runs leave the last suggestions on screen with a quiet
      // "updating" hint; the manual path blanks the panel and narrates.
      patch(
        silent
          ? { confirmError: null, autoRefreshing: true }
          : {
              confirmError: null,
              confirmBusy: true,
              confirmBusyMessage: "Saving confirmed steps…",
              submission: state.submission
                ? { ...state.submission, verification: null, marks: null, feedback: null, practice: [] }
                : null,
            }
      );
      const payload = state.localSteps.map((s, i) => ({ index: i + 1, latex: s.latex, confidence: s.confidence || "high" }));
      try {
        const saved = await api.updateSteps(state.submissionId, payload);
        if (!silent) patch({ submission: saved });
        await api.updateIdentity(state.submissionId, state.localName.trim() || null, state.localStudentId.trim() || null);
        if (!silent) patch({ confirmBusyMessage: "Refreshing draft score and feedback…" });
        const marked = await api.mark(state.submissionId);
        patch({ submission: marked });
        onDone?.();
      } catch (err) {
        patch({ confirmError: confirmErrorMessage(err) });
      } finally {
        mutationBusy.current = false;
        patch(silent ? { autoRefreshing: false } : { confirmBusy: false });
      }
    },
    [state.submissionId, state.localSteps, state.localName, state.localStudentId, state.submission, patch]
  );

  // Instant suggestions: a beat after the lecturer stops amending the digital
  // record, re-run verify → mark → feedback so the assessment draft always
  // describes what is currently on screen. The manual "Refresh suggestions"
  // button stays as an explicit fallback.
  const confirmRef = useRef(confirmAndMark);
  confirmRef.current = confirmAndMark;
  const autoTimer = useRef<number | null>(null);
  // The last record content an auto-run was fired for. Guards against a failed
  // silent run (e.g. an offline cache miss) re-triggering itself forever: we
  // only auto-attempt each distinct set of lines once, success or failure.
  const autoAttemptedSig = useRef<string | null>(null);
  const savedLatexSig = JSON.stringify((state.submission?.confirmed_steps || []).map((s) => s.latex));
  const localLatexSig = JSON.stringify(state.localSteps.map((s) => s.latex));

  useEffect(() => {
    if (!state.submissionId) return;
    if (savedLatexSig === localLatexSig) return; // record matches suggestions
    if (autoAttemptedSig.current === localLatexSig) return; // already tried these lines
    if (!state.localSteps.some((s) => s.latex.trim())) return; // nothing to mark
    if (state.confirmBusy || state.autoRefreshing || state.reviewBusy) return;
    if (autoTimer.current) window.clearTimeout(autoTimer.current);
    autoTimer.current = window.setTimeout(() => {
      autoAttemptedSig.current = localLatexSig;
      void confirmRef.current(undefined, { silent: true });
    }, 900);
    return () => {
      if (autoTimer.current) window.clearTimeout(autoTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedLatexSig, localLatexSig, state.submissionId, state.confirmBusy, state.autoRefreshing, state.reviewBusy]);

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

  const resumeSubmission = useCallback(async (id: string) => {
    if (mutationBusy.current || state.confirmBusy || state.autoRefreshing) {
      throw new Error("Wait for the current save or marking run to finish.");
    }
    if (id === state.submissionId) return true; // Keep this session's pending edits.
    const dirty = state.submissionId && (
      JSON.stringify(state.localSteps.map((s) => s.latex)) !== JSON.stringify((state.submission?.confirmed_steps || []).map((s) => s.latex)) ||
      state.localName.trim() !== state.submission?.student_pseudonym ||
      state.localStudentId.trim() !== (state.submission?.student_id || "") ||
      state.feedbackDraft !== null || state.pendingUploadFile !== null
    );
    if (dirty && !window.confirm("Open another submission and discard the current unsaved edits? Saved work will remain available.")) return false;
    mutationBusy.current = true;
    patch({ reviewBusy: true });
    try {
      const [sub, questions]: [Submission, Question[]] = await Promise.all([api.getSubmission(id), api.listQuestions()]);
      if (autoTimer.current) window.clearTimeout(autoTimer.current);
      autoAttemptedSig.current = null;
      setState({
        ...initialState, questions,
        currentQuestion: questions.find((q) => q.id === sub.question_id) || null,
        submissionId: sub.id, submission: sub,
        localName: sub.student_pseudonym || "", localStudentId: sub.student_id || "",
        localSteps: (sub.confirmed_steps ?? sub.transcription?.steps ?? []).map((s) => ({ ...s })),
        channel: sub.channel || "tutorial", assignmentId: sub.assignment_id || null,
        uploadedImageUrl: sub.image_filename ? apiUrl(`/api/submissions/${encodeURIComponent(sub.id)}/image`) : null,
        // Only the chosen rendered page is saved; the original PDF is not retained.
        uploadSourceType: sub.image_filename ? "image" : null,
        uploadSelectedPage: sub.source_page || 1,
      });
      return true;
    } finally {
      mutationBusy.current = false;
      patch({ reviewBusy: false });
    }
  }, [state, patch]);

  return {
    state,
    resumeSubmission,
    loadQuestions,
    selectQuestion,
    beginWithUpload,
    beginManualEntry,
    loadPagePreview,
    transcribeStagedFile,
    setSubmission,
    setChannel,
    setAssignment,
    setLocalName,
    setLocalStudentId,
    setFeedbackDraft,
    saveReview,
    saveScore,
    regenerateFeedback,
    publishTutorial,
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
