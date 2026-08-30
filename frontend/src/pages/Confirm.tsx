import { useEffect, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  ChevronRight,
  FileSearch,
  Plus,
  RefreshCw,
  Save,
  ScanLine,
  Sparkles,
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
import type { CriterionMark, Feedback, StepVerification } from "../types";

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
  const marks = sub?.marks;
  const extractedIdentity = sub?.extracted_identity;
  const identityWasExtracted = !!(extractedIdentity && (extractedIdentity.name || extractedIdentity.student_id));
  const identityFoundNothing = !!extractedIdentity && !extractedIdentity.name && !extractedIdentity.student_id;
  const total = marks?.total_proposed ?? marks?.criteria.reduce((sum, c) => sum + c.proposed, 0) ?? 0;
  const totalMax = marks?.total_max ?? marks?.criteria.reduce((sum, c) => sum + c.max, 0) ?? 0;
  const verified = sub?.verification?.steps.filter((step) => step.parsed).length ?? 0;
  const savedLatex = (sub?.confirmed_steps || []).map((step) => step.latex);
  const localLatex = state.localSteps.map((step) => step.latex);
  const recordDirty = JSON.stringify(savedLatex) !== JSON.stringify(localLatex);

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
            <span className="font-mono text-[11px] text-text-muted">{state.currentQuestion?.id}</span>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {state.localName || sub?.student_pseudonym || "Unidentified student"}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {verified > 0 && <Badge tone="success">{verified} lines parsed</Badge>}
          {recordDirty ? (
            <Badge tone="warning">Unsaved record — refresh needed</Badge>
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
              <p className="text-[10px] uppercase tracking-wider text-text-muted">suggested total</p>
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

      <div className="grid gap-4 xl:grid-cols-[minmax(250px,0.84fr)_minmax(360px,1.08fr)_minmax(340px,1fr)]">
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
              {state.confirmBusy && (
                <div className="mb-3 flex items-center gap-2 text-xs text-text-muted">
                  <RefreshCw className="animate-spin" size={13} /> {state.confirmBusyMessage}
                </div>
              )}
              <Button
                onClick={() => wb.confirmAndMark()}
                disabled={state.confirmBusy || !state.localSteps.some((step) => step.latex.trim())}
                className="w-full py-3"
              >
                <RefreshCw size={15} /> Save edits &amp; refresh suggestions
              </Button>
              <p className="mt-2 text-center text-[11px] leading-relaxed text-text-muted">
                One recalculation runs after you save—not while you type.
              </p>
            </div>
          }
        >
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
              {recordDirty && (
                <div className="mb-3 flex gap-2 rounded-xl border border-warning/30 bg-warning-soft p-3 text-xs leading-relaxed text-warning">
                  <AlertTriangle className="mt-0.5 shrink-0" size={14} />
                  These suggestions describe the last saved record. Save your transcription edits to refresh them.
                </div>
              )}
              <div className="mb-3 flex items-center justify-between gap-2">
                <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">Rubric suggestions</p>
                <Badge tone="warning">Lecturer review required</Badge>
              </div>
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

              <div className="my-5 h-px bg-border" />
              <FeedbackEditor submissionId={state.submissionId!} feedback={sub?.feedback ?? null} onUpdated={wb.setSubmission} />

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
      </div>
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

function FeedbackEditor({ submissionId, feedback, onUpdated }: {
  submissionId: string;
  feedback: Feedback | null;
  onUpdated: (submission: any) => void;
}) {
  const toast = useToast();
  const [draft, setDraft] = useState({ what_went_well: "", what_went_wrong: "", how_to_improve: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft({
      what_went_well: feedback?.what_went_well || "",
      what_went_wrong: feedback?.what_went_wrong || "",
      how_to_improve: feedback?.how_to_improve || "",
    });
  }, [feedback]);

  const dirty = !!feedback &&
    (draft.what_went_well !== feedback.what_went_well ||
      draft.what_went_wrong !== feedback.what_went_wrong ||
      draft.how_to_improve !== feedback.how_to_improve);

  async function save() {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      onUpdated(await api.updateFeedback(submissionId, draft));
      toast.success("Feedback edits saved.");
    } catch (error) {
      toast.error(error instanceof ApiError ? String(error.body?.detail || error.message) : "Could not save feedback.");
    } finally {
      setSaving(false);
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
        <FeedbackField id="feedback-well" label="What went well" value={draft.what_went_well} onChange={(value) => setDraft((current) => ({ ...current, what_went_well: value }))} />
        <FeedbackField id="feedback-attention" label="What needs attention" value={draft.what_went_wrong} onChange={(value) => setDraft((current) => ({ ...current, what_went_wrong: value }))} />
        <FeedbackField id="feedback-improve" label="How to improve" value={draft.how_to_improve} onChange={(value) => setDraft((current) => ({ ...current, how_to_improve: value }))} />
      </div>
      <Button variant="secondary" className="mt-3 w-full" disabled={!dirty || saving} onClick={save}>
        {saving ? <RefreshCw className="animate-spin" size={14} /> : <Save size={14} />}
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
