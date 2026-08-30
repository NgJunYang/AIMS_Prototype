import { useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useWorkbench } from "../state/WorkbenchContext";
import { useToast } from "../components/ui/Toast";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Tabs, TabPanel } from "../components/ui/Tabs";
import { Katex, Mixed } from "../components/Math";
import { api, ApiError } from "../lib/api";
import { divergenceMessage, formatRootList, humanizeTag } from "../lib/katex";
import type { StepVerification, Step, Marks, CriterionMark } from "../types";

function verdictTone(v: StepVerification): "success" | "danger" | "neutral" {
  if (!v.parsed) return "neutral";
  if (v.equivalent_to_previous === false) return "danger";
  if (v.equivalent_to_previous === true) return "success";
  return "neutral";
}
function verdictLabel(v: StepVerification): string {
  if (!v.parsed) return "Not symbolically verified";
  if (v.equivalent_to_previous === false) return "Diverged from previous step";
  if (v.equivalent_to_previous === true) return "Verified";
  return "No verdict — nothing to compare";
}
function verdictDetail(v: StepVerification): string | null {
  if (!v.parsed) return null;
  if (v.equivalent_to_previous === false) return divergenceMessage(v);
  if (v.equivalent_to_previous === true) return "Verified equivalent to the previous step.";
  if (v.solutions && v.solutions.length) return `Solutions so far: ${formatRootList(v.solutions)}`;
  return null;
}

const toneBorder: Record<string, string> = {
  success: "border-success/40 bg-success-soft/40",
  danger: "border-danger/40 bg-danger-soft/40",
  neutral: "border-border bg-surface-2",
};

export default function Review() {
  const { state } = useWorkbench();
  const toast = useToast();
  const [tab, setTab] = useState("feedback");
  const stepRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const [highlighted, setHighlighted] = useState<number | null>(null);

  const sub = state.submission;
  if (!sub || !sub.marks) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-10">
        <p className="rounded-lg border border-dashed border-border p-8 text-center text-text-muted">
          Nothing marked yet — confirm a submission first.
        </p>
      </div>
    );
  }

  const marks = sub.marks as Marks & { warnings?: string[]; misconceptions?: string[] };
  const verification = sub.verification;
  const confirmedSteps = sub.confirmed_steps || [];
  const stepsByIndex: Record<number, Step> = {};
  confirmedSteps.forEach((s) => (stepsByIndex[s.index] = s));

  function scrollToStep(index: number) {
    stepRefs.current[index]?.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlighted(index);
    setTimeout(() => setHighlighted(null), 1200);
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Review</p>
          <h1 className="text-2xl font-semibold">
            {state.currentQuestion?.id} — {sub.student_pseudonym || "Student"}
          </h1>
        </div>
        <div className="rounded-2xl border border-border bg-surface px-5 py-3 text-center">
          <p className="font-mono text-2xl font-semibold tabular-nums">
            {marks.total_proposed} / {marks.total_max}
          </p>
          <p className="text-xs text-text-muted">total</p>
        </div>
      </div>

      {!!marks.warnings?.length && (
        <div className="mb-6 flex flex-col gap-2">
          {marks.warnings.map((w, i) => (
            <div key={i} className="flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-soft px-3 py-2 text-sm text-warning">
              <AlertTriangle size={14} /> {w}
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <p className="mb-3 font-mono text-xs uppercase tracking-wide text-text-muted">Verified steps</p>
          {!verification || !verification.steps?.length ? (
            <p className="text-sm text-text-muted">No symbolic verification available for this submission.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {verification.steps.map((v) => {
                const tone = verdictTone(v);
                return (
                  <div
                    key={v.index}
                    ref={(el) => {
                      stepRefs.current[v.index] = el;
                    }}
                    className={`rounded-lg border p-3 transition-shadow ${toneBorder[tone]} ${
                      highlighted === v.index ? "ring-2 ring-accent" : ""
                    }`}
                  >
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="font-mono text-xs text-text-muted">Step {v.index}</span>
                      <Badge tone={tone}>{verdictLabel(v)}</Badge>
                    </div>
                    <div className="mb-2 rounded-md bg-surface px-2 py-1.5 text-sm">
                      <Katex latex={stepsByIndex[v.index]?.latex || ""} display />
                    </div>
                    {verdictDetail(v) && <p className="text-sm">{verdictDetail(v)}</p>}
                  </div>
                );
              })}
              <div className={`rounded-lg border p-3 ${toneBorder[!verification.final_answer_verified ? "neutral" : verification.final_answer_correct ? "success" : "danger"]}`}>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-text-muted">Overall</span>
                  <Badge tone={!verification.final_answer_verified ? "neutral" : verification.final_answer_correct ? "success" : "danger"}>
                    Final answer
                  </Badge>
                </div>
                <p className="text-sm">
                  {!verification.final_answer_verified
                    ? "Not established — the final line could not be symbolically verified. This does not mean it is wrong; judge it from the written evidence."
                    : verification.final_answer_correct
                      ? `Correct. Expected: ${formatRootList(verification.model_solutions)}`
                      : `Incorrect. Expected: ${formatRootList(verification.model_solutions)}`}
                </p>
              </div>
            </div>
          )}
        </Card>

        <Card>
          <p className="mb-3 font-mono text-xs uppercase tracking-wide text-text-muted">Rubric marks</p>
          <div className="flex flex-col gap-3">
            {marks.criteria.map((c) => (
              <CriterionCard key={c.criterion_id} c={c} submissionId={state.submissionId!} onScrollTo={scrollToStep} onError={(m) => toast.error(m)} />
            ))}
          </div>
        </Card>
      </div>

      <Card className="mt-6">
        <Tabs
          value={tab}
          onValueChange={setTab}
          tabs={[
            { value: "feedback", label: "Feedback" },
            { value: "misconceptions", label: "Misconceptions" },
            { value: "practice", label: "Practice" },
          ]}
        >
          <TabPanel value="feedback">
            <FeedbackTab feedback={sub.feedback as any} />
          </TabPanel>
          <TabPanel value="misconceptions">
            <MisconceptionsTab misconceptions={marks.misconceptions || []} />
          </TabPanel>
          <TabPanel value="practice">
            <PracticeTab />
          </TabPanel>
        </Tabs>
      </Card>
    </div>
  );
}

function CriterionCard({
  c,
  submissionId,
  onScrollTo,
  onError,
}: {
  c: CriterionMark & { max?: number };
  submissionId: string;
  onScrollTo: (i: number) => void;
  onError: (m: string) => void;
}) {
  const wb = useWorkbench();
  const criterion = (wb.state.currentQuestion?.criteria || []).find((cc) => cc.id === c.criterion_id);
  const max = criterion?.max ?? 0;
  const [value, setValue] = useState(String(c.proposed));

  async function commit() {
    const num = Number(value);
    if (!Number.isFinite(num) || num < 0 || num > max || !Number.isInteger(num)) {
      setValue(String(c.proposed));
      return;
    }
    try {
      const updated = await api.override(submissionId, c.criterion_id, num);
      wb.setSubmission(updated);
    } catch (err) {
      setValue(String(c.proposed));
      onError(err instanceof ApiError ? err.body?.detail?.toString() || err.message : "Something went wrong.");
    }
  }

  return (
    <div className={`rounded-lg border border-border p-3 ${c.overridden ? "bg-accent-soft/30" : ""}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-text-muted">
          {c.criterion_id}
          {c.overridden ? " · overridden" : ""}
        </span>
        <div className="flex items-center gap-1">
          <input
            type="number"
            min={0}
            max={max}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onBlur={commit}
            className="w-16 rounded-md border border-border bg-surface-2 px-2 py-1 text-right text-sm tabular-nums outline-none focus:border-accent"
          />
          <span className="text-sm text-text-muted">/ {max}</span>
        </div>
      </div>
      <p className="mt-2 text-sm">{c.justification || ""}</p>
      {c.evidence_step !== null && c.evidence_step !== undefined ? (
        <button onClick={() => onScrollTo(c.evidence_step!)} className="mt-1 text-xs text-accent-hover underline underline-offset-2">
          see step {c.evidence_step}
        </button>
      ) : (
        <span className="mt-1 block text-xs text-text-muted">no step cited</span>
      )}
    </div>
  );
}

function FeedbackTab({ feedback }: { feedback: { what_went_well?: string; what_went_wrong?: string; how_to_improve?: string; references?: string[] } | null }) {
  if (!feedback) return <p className="text-sm text-text-muted">No feedback generated.</p>;
  const Section = ({ title, text }: { title: string; text?: string }) => (
    <div className="mb-4">
      <h3 className="mb-1 font-mono text-xs font-semibold uppercase tracking-wide text-text-muted">{title}</h3>
      <p className="text-sm">{text || "—"}</p>
    </div>
  );
  return (
    <div>
      <Section title="What went well" text={feedback.what_went_well} />
      <Section title="What went wrong" text={feedback.what_went_wrong} />
      <Section title="How to improve" text={feedback.how_to_improve} />
      {!!feedback.references?.length && (
        <div>
          <h3 className="mb-1 font-mono text-xs font-semibold uppercase tracking-wide text-text-muted">References</h3>
          <ul className="list-inside list-disc text-sm">
            {feedback.references.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MisconceptionsTab({ misconceptions }: { misconceptions: string[] }) {
  if (!misconceptions.length) return <p className="text-sm text-text-muted">No misconceptions were identified.</p>;
  return (
    <ul className="flex flex-col gap-2">
      {misconceptions.map((tag, i) => (
        <li key={i} className="rounded-lg border border-border px-3 py-2 text-sm">
          {humanizeTag(tag)}
        </li>
      ))}
    </ul>
  );
}

function PracticeTab() {
  const { state } = useWorkbench();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [type, setType] = useState<"bare" | "scenario">("bare");
  const [practice, setPractice] = useState<any[]>((state.submission?.practice as any[]) || []);
  const [shown, setShown] = useState<Record<number, boolean>>({});

  async function regenerate(questionType: "bare" | "scenario") {
    if (!state.submissionId || busy) return;
    setBusy(true);
    setType(questionType);
    try {
      const updated = await api.regeneratePractice(state.submissionId, questionType);
      setPractice(updated.practice || []);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.body?.detail?.toString() || err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-text-muted">Question style</span>
        {[
          { value: "bare" as const, label: "Standard" },
          { value: "scenario" as const, label: "Word problem" },
        ].map((opt) => (
          <Button key={opt.value} variant="secondary" className="px-3 py-1 text-xs" disabled={busy || type === opt.value} onClick={() => regenerate(opt.value)}>
            {opt.label}
          </Button>
        ))}
        {busy && <span className="text-xs text-text-muted">Regenerating…</span>}
      </div>

      {!practice.length ? (
        <p className="text-sm text-text-muted">No practice questions generated.</p>
      ) : (
        practice.map((p, i) => (
          <div key={i} className="mb-3 rounded-lg border border-border p-3">
            <div className="flex flex-wrap items-center gap-1">
              <Badge tone="accent">{humanizeTag(p.misconception_tag)}</Badge>
              {p.question_type === "scenario" && <Badge tone="success">Word problem</Badge>}
            </div>
            <div className="mt-2 text-sm">
              <Mixed text={p.prompt_latex} />
            </div>
            {shown[i] && (
              <div className="mt-2">
                <div className="rounded-md bg-surface-2 px-2 py-1.5 text-sm">
                  <Katex latex={p.answer_latex} />
                </div>
                {p.rejected_note && <p className="mt-1 text-xs italic text-text-muted">{p.rejected_note}</p>}
              </div>
            )}
            <Button variant="secondary" className="mt-2 px-3 py-1 text-xs" onClick={() => setShown((s) => ({ ...s, [i]: !s[i] }))}>
              {shown[i] ? "Hide answer" : "Show answer"}
            </Button>
          </div>
        ))
      )}
    </div>
  );
}
