import { useEffect, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  ChevronRight,
  FileSearch,
  Plus,
  Pencil,
  RefreshCw,
  RotateCcw,
  Save,
  ScanLine,
  Send,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useWorkbench } from "../state/WorkbenchContext";
import { useToast } from "../components/ui/Toast";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Input, Label, Textarea } from "../components/ui/Field";
import { StepList } from "../components/StepList";
import { Katex, Mixed } from "../components/Math";
import { api, ApiError } from "../lib/api";
import { divergenceMessage, formatRootList, humanizeTag } from "../lib/katex";
import type { Criterion, CriterionMark, Question, StepVerification } from "../types";
import { StudentResultLink } from "../components/StudentResultLink";

type PanelTone = "scan" | "record" | "assess";

const panelTone: Record<PanelTone, { bar: string; number: string; icon: string }> = {
  scan: { bar: "bg-warning", number: "text-warning", icon: "bg-warning-soft text-warning" },
  record: { bar: "bg-accent", number: "text-accent-hover", icon: "bg-accent-soft text-accent-hover" },
  assess: { bar: "bg-danger", number: "text-danger", icon: "bg-danger-soft text-danger" },
};

export default function Confirm() {
  const wb = useWorkbench();
  const { state } = wb;
  const [focusedStep, setFocusedStep] = useState<number | null>(null);
  const [editingRubric, setEditingRubric] = useState(false);

  if (!state.submissionId) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-10">
        <p className="rounded-lg border border-dashed border-border p-8 text-center text-text-muted">
          Nothing to assess yet — start from Setup.
        </p>
      </div>
    );
  }

  const sub = state.submission;
  // Setup selects a question for the NEXT submission. This desk belongs only
  // to the question recorded on the active submission.
  const submissionQuestion = state.questions.find((q) => q.id === sub?.question_id) || null;
  const marks = sub?.marks;
  const extractedIdentity = sub?.extracted_identity;
  const identityWasExtracted = !!(extractedIdentity && (extractedIdentity.name || extractedIdentity.student_id));
  const identityFoundNothing = !!extractedIdentity && !extractedIdentity.name && !extractedIdentity.student_id;
  const total = marks?.total_proposed ?? marks?.criteria.reduce((sum, c) => sum + c.proposed, 0) ?? 0;
  const totalMax = marks?.total_max ?? marks?.criteria.reduce((sum, c) => sum + c.max, 0) ?? 0;
  const hasOverrides = !!marks?.criteria.some((criterion) => criterion.overridden);
  const verified = sub?.verification?.steps.filter((step) => step.parsed).length ?? 0;
  const savedLatex = (sub?.confirmed_steps || []).map((step) => step.latex);
  const localLatex = state.localSteps.map((step) => step.latex);
  const recordDirty = JSON.stringify(savedLatex) !== JSON.stringify(localLatex);
  // Suggestions are catching up to an edit: either the debounced auto-run is
  // mid-flight, or the record diverges and the run is about to fire.
  const suggestionsStale = state.autoRefreshing || (recordDirty && !!marks);

  function focusEvidence(index: number) {
    setFocusedStep(index);
    window.setTimeout(() => setFocusedStep(null), 1800);
  }

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-5 sm:px-6">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-4">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
              Assessment desk
            </span>
            <span className="h-px w-10 bg-border" />
            <span className="font-mono text-[11px] text-text-muted">{sub?.question_id}</span>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {state.localName || sub?.student_pseudonym || "Unidentified student"}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {verified > 0 && <Badge tone="success">{verified} lines parsed</Badge>}
          {suggestionsStale ? (
            <Badge tone="warning">Updating suggestions…</Badge>
          ) : marks ? (
            <Badge tone="accent">Draft suggestions ready</Badge>
          ) : (
            <Badge tone="neutral">Awaiting suggestions</Badge>
          )}
          {marks && (
            <div className="ml-1 rounded-xl border border-border bg-surface px-4 py-2 text-right shadow-sm">
              <p className="font-mono text-xl font-semibold tabular-nums">
                {total} <span className="text-sm font-normal text-text-muted">/ {totalMax}</span>
              </p>
              <p className="text-[10px] uppercase tracking-wider text-text-muted">{hasOverrides ? "manually adjusted total" : "suggested total"}</p>
            </div>
          )}
        </div>
      </div>

      {state.confirmError && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
          <AlertTriangle className="mt-0.5 shrink-0" size={15} />
          <span>{state.confirmError}</span>
        </div>
      )}

      <fieldset disabled={state.reviewBusy} className="grid min-w-0 gap-4 xl:grid-cols-[minmax(250px,0.84fr)_minmax(360px,1.08fr)_minmax(340px,1fr)]">
        <PanelFrame index="01" title="Source scan" subtitle="The original evidence" tone="scan" icon={<ScanLine size={17} />}>
          <ImagePane
            uploadSourceType={state.uploadSourceType}
            hasTranscription={!!sub?.transcription}
            uploadedImageUrl={state.uploadedImageUrl}
            uploadPreviewB64={state.uploadPreviewB64}
            uploadPreviewBusy={state.uploadPreviewBusy}
            uploadPageCount={state.uploadPageCount}
            uploadSelectedPage={state.uploadSelectedPage}
            sourcePageCount={sub?.source_page_count ?? undefined}
            sourcePage={sub?.source_page ?? undefined}
            onPrev={() => wb.loadPagePreview(state.uploadSelectedPage - 1)}
            onNext={() => wb.loadPagePreview(state.uploadSelectedPage + 1)}
            onCommit={() => wb.transcribeStagedFile(state.uploadSelectedPage)}
          />

          <div className="mt-5 border-t border-border pt-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">Script identity</p>
              {identityWasExtracted && (
                <Badge tone={extractedIdentity?.confidence === "low" ? "warning" : "success"}>
                  {extractedIdentity?.confidence === "low" ? "check OCR" : "read from scan"}
                </Badge>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
              <div>
                <Label htmlFor="script-student-name">Name</Label>
                <Input id="script-student-name" value={state.localName} onChange={(e) => wb.setLocalName(e.target.value)} placeholder="Student name" />
              </div>
              <div>
                <Label htmlFor="script-student-id">Student ID</Label>
                <Input id="script-student-id" value={state.localStudentId} onChange={(e) => wb.setLocalStudentId(e.target.value)} placeholder="A1234567" />
              </div>
            </div>
            {identityFoundNothing && <p className="mt-2 text-xs text-text-muted">No readable identity was found. Assign it manually.</p>}
            <IdentitySaveControl />
          </div>
        </PanelFrame>

        <PanelFrame
          index="02"
          title="Digital record"
          subtitle="Rendered LaTeX, kept editable"
          tone="record"
          icon={<FileSearch size={17} />}
          footer={
            <div>
              {(state.confirmBusy || state.autoRefreshing) && (
                <div className="mb-3 flex items-center gap-2 text-xs text-text-muted">
                  <RefreshCw className="animate-spin" size={13} />{" "}
                  {state.confirmBusy ? state.confirmBusyMessage : "Refreshing score and feedback…"}
                </div>
              )}
              <Button
                onClick={() => wb.confirmAndMark()}
                disabled={state.confirmBusy || state.autoRefreshing || !state.localSteps.some((step) => step.latex.trim())}
                className="w-full py-3"
              >
                <RefreshCw size={15} /> Refresh suggestions now
              </Button>
              <p className="mt-2 text-center text-[11px] leading-relaxed text-text-muted">
                Score and feedback refresh on their own a moment after you stop editing.
              </p>
            </div>
          }
        >
          <QuestionReference question={submissionQuestion} />
          <div className="mb-4 rounded-xl border border-accent/25 bg-accent-soft/45 p-3 text-xs leading-relaxed text-accent-hover">
            Compare every line with the scan. Scores and feedback are drafts based on this editable record.
          </div>
          <div className="mb-3 flex items-center justify-between">
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">Transcribed lines</p>
            <Button variant="secondary" className="px-2.5 py-1 text-xs" onClick={wb.addStep}>
              <Plus size={12} /> Add line
            </Button>
          </div>
          <StepList steps={state.localSteps} onChange={wb.updateStepLatex} onRemove={wb.removeStep} />
          {sub?.transcription?.notes && (
            <div className="mt-4 rounded-lg border border-warning/25 bg-warning-soft/60 p-3 text-xs text-warning">
              <span className="font-semibold">Scanner note:</span> {sub.transcription.notes}
            </div>
          )}
          {sub?.verification && (
            <VerificationSummary
              verification={sub.verification.steps}
              finalCorrect={sub.verification.final_answer_correct}
              finalVerified={sub.verification.final_answer_verified}
              modelSolutions={sub.verification.model_solutions}
              steps={state.localSteps}
              focusedStep={focusedStep}
            />
          )}
        </PanelFrame>

        <PanelFrame index="03" title="Assessment draft" subtitle="Rubric decisions and feedback" tone="assess" icon={<Sparkles size={17} />}>
          {!marks ? (
            <EmptyAssessment busy={state.confirmBusy} />
          ) : (
            <>
              {suggestionsStale && (
                <div className="mb-3 flex gap-2 rounded-xl border border-warning/30 bg-warning-soft p-3 text-xs leading-relaxed text-warning">
                  <RefreshCw className="mt-0.5 shrink-0 animate-spin" size={14} />
                  Catching up to your latest edit — these will refresh in a moment.
                </div>
              )}
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">Rubric suggestions</p>
                <div className="flex flex-wrap items-center gap-2">
                  {hasOverrides && <Badge tone="accent">manual edits</Badge>}
                  {!editingRubric && submissionQuestion && (
                    <button
                      onClick={() => setEditingRubric(true)}
                      className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium text-text-muted hover:bg-surface-2 hover:text-text"
                      title="Edit the rubric"
                    >
                      <Pencil size={11} /> Edit rubric
                    </button>
                  )}
                  <Badge tone="warning">Lecturer review required</Badge>
                </div>
              </div>

              {editingRubric && submissionQuestion ? (
                <RubricEditor
                  key={submissionQuestion.id}
                  question={submissionQuestion}
                  onClose={() => setEditingRubric(false)}
                />
              ) : (
                <>
                  {hasOverrides && (
                    <ResetRubricButton submissionId={state.submissionId!} onUpdated={wb.setSubmission} />
                  )}
                  {!!marks.warnings?.length && (
                    <div className="mb-3 flex flex-col gap-2">
                      {marks.warnings.map((warning, index) => (
                        <div key={index} className="flex gap-2 rounded-lg bg-warning-soft p-2.5 text-xs text-warning">
                          <AlertTriangle className="mt-0.5 shrink-0" size={13} /> {warning}
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="flex flex-col gap-2.5">
                    {marks.criteria.map((criterion) => (
                      <RubricCriterion
                        key={criterion.criterion_id}
                        criterion={criterion}
                        submissionId={state.submissionId!}
                        onUpdated={wb.setSubmission}
                        onEvidence={focusEvidence}
                      />
                    ))}
                  </div>
                </>
              )}

              <div className="my-5 h-px bg-border" />
              <FeedbackEditor />

              {!editingRubric && (
                <PublishControl
                  submissionId={state.submissionId!}
                  channel={sub?.channel ?? "test"}
                  published={!!sub?.published}
                  disabled={suggestionsStale || state.confirmBusy}
                  onUpdated={wb.setSubmission}
                />
              )}

              {!!marks.misconceptions?.length && (
                <div className="mt-5 border-t border-border pt-4">
                  <p className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">Learning gaps</p>
                  <div className="flex flex-wrap gap-1.5">
                    {marks.misconceptions.map((tag) => (
                      <Badge key={tag} tone="danger">{humanizeTag(tag)}</Badge>
                    ))}
                  </div>
                </div>
              )}

              <PracticeSection />
            </>
          )}
        </PanelFrame>
      </fieldset>
    </div>
  );
}

function PanelFrame({ index, title, subtitle, tone, icon, children, footer }: {
  index: string;
  title: string;
  subtitle: string;
  tone: PanelTone;
  icon: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const colors = panelTone[tone];
  return (
    <Card className="relative flex min-h-[34rem] flex-col overflow-hidden p-0 shadow-[0_14px_40px_rgba(67,54,38,0.07)] xl:h-[calc(100vh-9rem)]">
      <div className={`h-1 w-full shrink-0 ${colors.bar}`} />
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-surface/95 px-4 py-3 backdrop-blur">
        <span className={`font-mono text-xs font-semibold ${colors.number}`}>{index}</span>
        <span className={`grid h-8 w-8 place-items-center rounded-lg ${colors.icon}`}>{icon}</span>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{title}</h2>
          <p className="truncate text-[11px] text-text-muted">{subtitle}</p>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      {footer && <div className="shrink-0 border-t border-border bg-surface px-4 py-3">{footer}</div>}
    </Card>
  );
}

function EmptyAssessment({ busy }: { busy: boolean }) {
  return (
    <div className="grid min-h-[24rem] place-items-center text-center">
      <div className="max-w-xs">
        <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl border border-dashed border-border bg-surface-2 text-text-muted">
          {busy ? <RefreshCw className="animate-spin" size={23} /> : <Sparkles size={23} />}
        </div>
        <h3 className="font-semibold">{busy ? "Building the assessment draft" : "No suggestions yet"}</h3>
        <p className="mt-2 text-sm leading-relaxed text-text-muted">
          {busy
            ? "The verified record is being mapped to the rubric and personalised feedback."
            : "Add or transcribe the student’s work, then save it to generate reviewable suggestions."}
        </p>
      </div>
    </div>
  );
}

function RubricCriterion({ criterion, submissionId, onUpdated, onEvidence }: {
  criterion: CriterionMark;
  submissionId: string;
  onUpdated: (submission: any) => void;
  onEvidence: (step: number) => void;
}) {
  const toast = useToast();
  const [value, setValue] = useState(String(criterion.proposed));

  useEffect(() => setValue(String(criterion.proposed)), [criterion.proposed]);

  async function commit() {
    const proposed = Number(value);
    if (!Number.isInteger(proposed) || proposed < 0 || proposed > criterion.max) {
      setValue(String(criterion.proposed));
      toast.error(`Enter a whole-number score from 0 to ${criterion.max}.`);
      return;
    }
    if (proposed === criterion.proposed) return;
    try {
      onUpdated(await api.override(submissionId, criterion.criterion_id, proposed));
      toast.success(`${criterion.criterion_id} updated.`);
    } catch (error) {
      setValue(String(criterion.proposed));
      toast.error(error instanceof ApiError ? String(error.body?.detail || error.message) : "Could not update the score.");
    }
  }

  return (
    <div className={`rounded-xl border p-3 ${criterion.overridden ? "border-accent/40 bg-accent-soft/35" : "border-border bg-surface-2/55"}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold">{criterion.criterion_id}</span>
          {criterion.overridden && <Badge tone="accent">edited</Badge>}
        </div>
        <label className="flex items-center gap-1.5">
          <span className="sr-only">Suggested score for {criterion.criterion_id}</span>
          <input
            type="number"
            min={0}
            max={criterion.max}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onBlur={commit}
            onKeyDown={(event) => event.key === "Enter" && event.currentTarget.blur()}
            className="w-14 rounded-md border border-border bg-surface px-2 py-1 text-right font-mono text-sm font-semibold tabular-nums outline-none focus:border-accent"
          />
          <span className="font-mono text-xs text-text-muted">/ {criterion.max}</span>
        </label>
      </div>
      <p className="mt-2 text-xs leading-relaxed">{criterion.justification}</p>
      {criterion.evidence_step != null && (
        <button onClick={() => onEvidence(criterion.evidence_step!)} className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-accent-hover underline decoration-accent/40 underline-offset-2">
          <FileSearch size={11} /> Inspect evidence at line {criterion.evidence_step}
        </button>
      )}
    </div>
  );
}

function ResetRubricButton({ submissionId, onUpdated }: {
  submissionId: string;
  onUpdated: (submission: any) => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function reset() {
    if (busy) return;
    setBusy(true);
    try {
      onUpdated(await api.resetOverrides(submissionId));
      toast.success("Rubric edits reset to the latest suggestions.");
    } catch (error) {
      toast.error(error instanceof ApiError ? String(error.body?.detail || error.message) : "Could not reset rubric edits.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button variant="secondary" className="mb-3 w-full" disabled={busy} onClick={reset}>
      {busy ? <RefreshCw className="animate-spin" size={14} /> : <RotateCcw size={14} />}
      Reset rubric edits to AI suggestions
    </Button>
  );
}

function IdentitySaveControl() {
  const wb = useWorkbench();
  const { state } = wb;
  const toast = useToast();
  const dirty = state.localName.trim() !== (state.submission?.student_pseudonym || "") ||
    state.localStudentId.trim() !== (state.submission?.student_id || "");

  async function save() {
    try {
      if (await wb.saveReview("identity")) toast.success("Student identity saved.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save student identity.");
    }
  }

  return (
    <div className="mt-3">
      <p className="mb-2 text-[11px] text-text-muted" role="status">
        {dirty ? "Unsaved identity changes — save now or publish to save them." : "Student identity saved."}
      </p>
      <Button variant="secondary" className="w-full" disabled={!dirty || state.reviewBusy || state.confirmBusy || state.autoRefreshing} onClick={save}>
        <Save size={14} /> Save identity
      </Button>
    </div>
  );
}

function FeedbackEditor() {
  const wb = useWorkbench();
  const { state } = wb;
  const feedback = state.submission?.feedback;
  const toast = useToast();
  const draft = state.feedbackDraft || feedback || { what_went_well: "", what_went_wrong: "", how_to_improve: "" };

  const dirty = !!feedback &&
    (draft.what_went_well !== feedback.what_went_well ||
      draft.what_went_wrong !== feedback.what_went_wrong ||
      draft.how_to_improve !== feedback.how_to_improve);

  async function save() {
    if (!dirty || state.reviewBusy) return;
    try {
      if (await wb.saveReview("feedback")) toast.success("Feedback edits saved.");
    } catch (error) {
      toast.error(error instanceof ApiError ? String(error.body?.detail || error.message) : "Could not save feedback.");
    }
  }

  if (!feedback) return null;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">Feedback draft</p>
          <p className="mt-0.5 text-[11px] text-text-muted">Edit the suggestion before it reaches the learner.</p>
        </div>
        {dirty && <Badge tone="warning">unsaved</Badge>}
      </div>
      <div className="flex flex-col gap-3">
        <FeedbackField id="feedback-well" label="What went well" value={draft.what_went_well} onChange={(value) => wb.setFeedbackDraft({ ...draft, what_went_well: value })} />
        <FeedbackField id="feedback-attention" label="What needs attention" value={draft.what_went_wrong} onChange={(value) => wb.setFeedbackDraft({ ...draft, what_went_wrong: value })} />
        <FeedbackField id="feedback-improve" label="How to improve" value={draft.how_to_improve} onChange={(value) => wb.setFeedbackDraft({ ...draft, how_to_improve: value })} />
      </div>
      <Button variant="secondary" className="mt-3 w-full" disabled={!dirty || state.reviewBusy || state.confirmBusy || state.autoRefreshing} onClick={save}>
        <Save size={14} />
        Save feedback edits
      </Button>
    </div>
  );
}

function FeedbackField({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <Textarea id={id} rows={3} value={value} onChange={(event) => onChange(event.target.value)} className="resize-y leading-relaxed" />
    </div>
  );
}

function VerificationSummary({ verification, finalCorrect, finalVerified, modelSolutions, steps, focusedStep }: {
  verification: StepVerification[];
  finalCorrect: boolean;
  finalVerified: boolean;
  modelSolutions: string[];
  steps: { latex: string }[];
  focusedStep: number | null;
}) {
  return (
    <div className="mt-5 border-t border-border pt-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">Symbolic check</p>
        <Badge tone={!finalVerified ? "neutral" : finalCorrect ? "success" : "danger"}>
          {!finalVerified ? "answer unverified" : finalCorrect ? "final answer correct" : "final answer differs"}
        </Badge>
      </div>
      <div className="flex flex-col gap-2">
        {verification.map((result) => {
          const failed = result.equivalent_to_previous === false;
          const passed = result.parsed && result.equivalent_to_previous !== false;
          return (
            <div key={result.index} className={`rounded-lg border p-2.5 transition-all ${focusedStep === result.index ? "border-accent bg-accent-soft ring-2 ring-accent/20" : failed ? "border-danger/30 bg-danger-soft/45" : "border-border bg-surface-2/50"}`}>
              <div className="flex items-start gap-2">
                <span className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full ${passed ? "bg-success-soft text-success" : failed ? "bg-danger-soft text-danger" : "bg-surface text-text-muted"}`}>
                  {passed ? <Check size={11} /> : <span className="font-mono text-[9px]">{result.index}</span>}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="overflow-x-auto text-xs"><Katex latex={steps[result.index - 1]?.latex || ""} /></div>
                  {failed && <p className="mt-1 text-[11px] leading-relaxed text-danger">{divergenceMessage(result)}</p>}
                  {!result.parsed && <p className="mt-1 text-[11px] text-text-muted">Could not verify this line symbolically.</p>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {finalVerified && <p className="mt-2 text-[11px] text-text-muted">Expected solution set: {formatRootList(modelSolutions)}</p>}
    </div>
  );
}

function PracticeSection() {
  const { state } = useWorkbench();
  const toast = useToast();
  const [practice, setPractice] = useState<any[]>((state.submission?.practice as any[]) || []);
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState<Record<number, boolean>>({});

  useEffect(() => setPractice((state.submission?.practice as any[]) || []), [state.submission?.practice]);

  async function regenerate(questionType: "bare" | "scenario") {
    if (!state.submissionId || busy) return;
    setBusy(true);
    try {
      const updated = await api.regeneratePractice(state.submissionId, questionType);
      setPractice(updated.practice || []);
    } catch (error) {
      toast.error(error instanceof ApiError ? String(error.body?.detail || error.message) : "Could not regenerate practice.");
    } finally {
      setBusy(false);
    }
  }

  if (!practice.length) return null;

  return (
    <details className="mt-5 border-t border-border pt-4">
      <summary className="cursor-pointer list-none text-xs font-semibold text-text-muted hover:text-text">
        <span className="inline-flex items-center gap-2"><Sparkles size={13} /> Targeted practice ({practice.length})</span>
      </summary>
      <div className="mt-3">
        <div className="mb-3 flex flex-wrap gap-2">
          <Button variant="secondary" className="px-2.5 py-1 text-xs" disabled={busy} onClick={() => regenerate("bare")}>Standard</Button>
          <Button variant="secondary" className="px-2.5 py-1 text-xs" disabled={busy} onClick={() => regenerate("scenario")}>Word problems</Button>
        </div>
        {practice.map((item, index) => (
          <div key={index} className="mb-2 rounded-lg border border-border bg-surface-2/55 p-3 text-xs">
            <Badge tone="accent">{humanizeTag(item.misconception_tag)}</Badge>
            <div className="mt-2"><Mixed text={item.prompt_latex} /></div>
            {shown[index] && <div className="mt-2 rounded-md bg-surface p-2"><Katex latex={item.answer_latex} /></div>}
            <button className="mt-2 text-[11px] font-medium text-accent-hover underline underline-offset-2" onClick={() => setShown((current) => ({ ...current, [index]: !current[index] }))}>
              {shown[index] ? "Hide answer" : "Show answer"}
            </button>
          </div>
        ))}
      </div>
    </details>
  );
}

function ImagePane({ uploadSourceType, hasTranscription, uploadedImageUrl, uploadPreviewB64, uploadPreviewBusy, uploadPageCount, uploadSelectedPage, sourcePageCount, sourcePage, onPrev, onNext, onCommit }: {
  uploadSourceType: "image" | "pdf" | null;
  hasTranscription: boolean;
  uploadedImageUrl: string | null;
  uploadPreviewB64: string | null;
  uploadPreviewBusy: boolean;
  uploadPageCount: number;
  uploadSelectedPage: number;
  sourcePageCount?: number;
  sourcePage?: number;
  onPrev: () => void;
  onNext: () => void;
  onCommit: () => void;
}) {
  if (uploadSourceType === "pdf" && !hasTranscription) {
    if (!uploadPreviewB64) {
      return <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-text-muted">Loading page preview…</div>;
    }
    return (
      <div>
        <img src={`data:image/png;base64,${uploadPreviewB64}`} alt="PDF page preview" className="w-full rounded-xl border border-border bg-white" />
        {uploadPageCount > 1 && (
          <div className="mt-3 flex items-center justify-between gap-2">
            <Button variant="secondary" className="px-2.5 py-1 text-xs" disabled={uploadPreviewBusy || uploadSelectedPage <= 1} onClick={onPrev}><ChevronLeft size={13} /> Prev</Button>
            <span className="font-mono text-[11px] text-text-muted">{uploadSelectedPage} / {uploadPageCount}</span>
            <Button variant="secondary" className="px-2.5 py-1 text-xs" disabled={uploadPreviewBusy || uploadSelectedPage >= uploadPageCount} onClick={onNext}>Next <ChevronRight size={13} /></Button>
          </div>
        )}
        <Button className="mt-3 w-full" disabled={uploadPreviewBusy} onClick={onCommit}>Transcribe this page</Button>
      </div>
    );
  }

  const imageSource = uploadedImageUrl || (uploadSourceType === "pdf" && hasTranscription ? `data:image/png;base64,${uploadPreviewB64 || ""}` : "");
  if (imageSource) {
    return (
      <figure>
        <div className="overflow-hidden rounded-xl border border-border bg-white shadow-inner"><img src={imageSource} alt="Uploaded student working" className="w-full" /></div>
        {uploadSourceType === "pdf" && sourcePageCount && sourcePageCount > 1 && (
          <figcaption className="mt-2 text-center font-mono text-[11px] text-text-muted">Source page {sourcePage} of {sourcePageCount}</figcaption>
        )}
      </figure>
    );
  }

  return (
    <div className="grid min-h-56 place-items-center rounded-xl border border-dashed border-border bg-surface-2/40 p-6 text-center">
      <div>
        <ScanLine className="mx-auto mb-3 text-text-muted" size={25} />
        <p className="text-sm font-medium">Manual entry</p>
        <p className="mt-1 text-xs text-text-muted">No source image was uploaded for this submission.</p>
      </div>
    </div>
  );
}

function PublishControl({
  submissionId,
  channel,
  published,
  disabled,
  onUpdated,
}: {
  submissionId: string;
  channel: "tutorial" | "test";
  published: boolean;
  disabled: boolean;
  onUpdated: (submission: any) => void;
}) {
  const wb = useWorkbench();
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function toggle(next: boolean) {
    if (busy) return;
    setBusy(true);
    try {
      if (next) {
        if (!await wb.saveReview("publish")) return;
      } else {
        onUpdated(await api.unpublish(submissionId));
      }
      toast.success(next ? "Published — the student can now see this." : "Unpublished.");
    } catch (error) {
      toast.error(error instanceof ApiError ? String(error.body?.detail || error.message) : error instanceof Error ? error.message : "Could not update.");
    } finally {
      setBusy(false);
    }
  }

  if (channel === "tutorial") {
    return (
      <div className="mt-5 rounded-lg border border-border bg-surface-2/50 p-3 text-xs text-text-muted">
        <Check size={14} className="shrink-0 text-success" />
        Tutorial submission — visible to the student as soon as it's marked. No publishing step.
        <StudentResultLink id={submissionId} />
      </div>
    );
  }

  return (
    <div className="mt-5 rounded-lg border border-border bg-surface-2/50 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">Release to student</p>
        {published && <Badge tone="success">published</Badge>}
      </div>
      <p className="mb-3 text-xs leading-relaxed text-text-muted">
        A graded-test script stays hidden from the student until you publish it. Publish once you're happy with the
        score and feedback. Publishing also saves your pending feedback and student identity changes.
      </p>
      <Button
        variant={published ? "secondary" : "primary"}
        className="w-full"
        disabled={busy || disabled}
        onClick={() => toggle(!published)}
      >
        {busy ? <RefreshCw className="animate-spin" size={14} /> : <Send size={14} />}
        {published ? "Unpublish" : "Publish to student"}
      </Button>
      {published && <StudentResultLink id={submissionId} />}
    </div>
  );
}

function QuestionReference({ question }: { question: Question | null }) {
  if (!question) return null;
  return (
    <details className="mb-4 rounded-xl border border-border bg-surface-2/50 p-3 text-xs">
      <summary className="cursor-pointer list-none font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted hover:text-text">
        <span className="inline-flex items-center gap-2">
          <FileSearch size={12} /> Question &amp; model solution
        </span>
      </summary>
      <div className="mt-3 flex flex-col gap-3">
        <div>
          <p className="mb-1 font-semibold text-text-muted">Prompt</p>
          <Mixed text={question.prompt} className="text-sm" />
        </div>
        <div>
          <p className="mb-1 font-semibold text-text-muted">Model solution</p>
          <ol className="flex flex-col gap-1">
            {question.model_solution_steps.map((step, i) => (
              <li key={i} className="rounded-md bg-surface px-2 py-1">
                <Katex latex={step} />
              </li>
            ))}
          </ol>
        </div>
        <div>
          <p className="mb-1 font-semibold text-text-muted">Rubric</p>
          <table className="w-full">
            <tbody>
              {question.criteria.map((c) => (
                <tr key={c.id} className="border-b border-border last:border-0">
                  <td className="py-1 pr-2 align-top font-mono text-[10px] text-text-muted">{c.id}</td>
                  <td className="py-1 pr-2 align-top">{c.description}</td>
                  <td className="py-1 pl-2 text-right align-top font-mono tabular-nums">{c.max}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </details>
  );
}

function nextCriterionId(existing: string[]): string {
  let highest = 0;
  for (const id of existing) {
    const match = /^C(\d+)$/.exec(id);
    if (match) highest = Math.max(highest, Number(match[1]));
  }
  return `C${highest + 1}`;
}

function RubricEditor({ question, onClose }: { question: Question; onClose: () => void }) {
  const wb = useWorkbench();
  const toast = useToast();
  const [rows, setRows] = useState<Criterion[]>(question.criteria.map((c) => ({ ...c })));
  const [busy, setBusy] = useState(false);

  function update(index: number, patch: Partial<Criterion>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }
  function remove(index: number) {
    setRows((current) => current.filter((_, i) => i !== index));
  }
  function add() {
    setRows((current) => [
      ...current,
      { id: nextCriterionId(current.map((r) => r.id)), description: "", max: 1 },
    ]);
  }

  async function save() {
    if (busy) return;
    const cleaned = rows.map((r) => ({
      id: r.id.trim(),
      description: r.description.trim(),
      max: Math.trunc(Number(r.max)),
    }));
    if (!cleaned.length) return toast.error("A rubric needs at least one criterion.");
    if (cleaned.some((r) => !r.description)) return toast.error("Every criterion needs a description.");
    if (cleaned.some((r) => !Number.isFinite(r.max) || r.max < 0)) {
      return toast.error("Each criterion's marks must be a whole number of 0 or more.");
    }
    if (cleaned.reduce((sum, r) => sum + r.max, 0) < 1) {
      return toast.error("The rubric must be worth at least one mark in total.");
    }
    if (new Set(cleaned.map((r) => r.id)).size !== cleaned.length) {
      return toast.error("Criterion ids must be unique.");
    }

    setBusy(true);
    try {
      const updated: Question = { ...question, criteria: cleaned };
      await api.updateQuestion(question.id, updated);
      await wb.reloadQuestions(question.id);
      // The rubric changed, so the server cleared this submission's marks;
      // regenerate them against the new rubric.
      await wb.confirmAndMark();
      toast.success("Rubric updated — every submission on this question was re-scored.");
      onClose();
    } catch (error) {
      const detail = error instanceof ApiError ? error.body?.detail : null;
      toast.error(Array.isArray(detail) ? detail.join(" ") : String(detail || "Could not update the rubric."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-accent/40 bg-accent-soft/25 p-3">
      <p className="mb-2 text-[11px] leading-relaxed text-text-muted">
        Editing the rubric re-scores every submission on <span className="font-mono">{question.id}</span>.
      </p>
      <div className="flex flex-col gap-2">
        {rows.map((row, index) => (
          <div key={index} className="rounded-lg border border-border bg-surface p-2.5">
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="font-mono text-[10px] text-text-muted">{row.id}</span>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  min={0}
                  value={String(row.max)}
                  onChange={(e) => update(index, { max: Number(e.target.value) })}
                  className="w-14 rounded-md border border-border bg-surface-2 px-2 py-1 text-right font-mono text-sm tabular-nums outline-none focus:border-accent"
                />
                <span className="font-mono text-[10px] text-text-muted">marks</span>
                <button
                  onClick={() => remove(index)}
                  className="rounded p-1 text-text-muted hover:bg-danger-soft hover:text-danger"
                  title="Remove criterion"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
            <Textarea
              rows={2}
              value={row.description}
              onChange={(e) => update(index, { description: e.target.value })}
              placeholder="What this criterion rewards"
              className="text-xs leading-relaxed"
            />
          </div>
        ))}
      </div>
      <Button variant="secondary" className="mt-2 w-full px-2.5 py-1 text-xs" onClick={add} disabled={busy}>
        <Plus size={12} /> Add criterion
      </Button>
      <div className="mt-3 flex gap-2">
        <Button className="flex-1" disabled={busy} onClick={save}>
          {busy ? <RefreshCw className="animate-spin" size={14} /> : <Save size={14} />} Save rubric
        </Button>
        <Button variant="secondary" disabled={busy} onClick={onClose}>
          <X size={14} /> Cancel
        </Button>
      </div>
    </div>
  );
}
