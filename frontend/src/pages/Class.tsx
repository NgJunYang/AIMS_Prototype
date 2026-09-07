import { useEffect, useState } from "react";
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
} from "chart.js";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { api } from "../lib/api";
import { humanizeTag } from "../lib/katex";
import type { Submission } from "../types";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

interface CriterionStat {
  criterion_id: string;
  label: string;
  mean_percentage: number;
  n: number;
}
interface TopicStat {
  topic: string;
  mean_percentage: number;
  n: number;
}
interface StudentRow {
  pseudonym: string;
  question_id: string;
  mark: number;
  max: number;
  top_misconception?: string | null;
  submission_id?: string | null;
}
interface ClassSummary {
  source_note?: string | null;
  source?: "computed" | "sample";
  cohort_size: number;
  marked: number;
  mean_percentage: number;
  recommendation?: string;
  misconception_counts?: { name: string; count: number }[];
  criterion_performance?: CriterionStat[];
  topic_performance?: TopicStat[];
  students?: StudentRow[];
}

/** Warm-palette bands so a weak concept reads as weak at a glance. */
function bandBar(pct: number): string {
  if (pct < 50) return "bg-danger";
  if (pct < 70) return "bg-warning";
  return "bg-success";
}

export default function Class() {
  const [summary, setSummary] = useState<ClassSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSample, setShowSample] = useState(false);
  const [openStudent, setOpenStudent] = useState<StudentRow | null>(null);

  useEffect(() => {
    setSummary(null);
    setError(null);
    api
      .classSummary(showSample)
      .then(setSummary)
      .catch((err) => setError("Could not load class summary: " + (err instanceof Error ? err.message : String(err))));
  }, [showSample]);

  if (error) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-10">
        <p className="text-sm text-danger">{error}</p>
      </div>
    );
  }
  if (!summary) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-10">
        <p className="text-sm text-text-muted">Loading analytics…</p>
      </div>
    );
  }

  const counts = summary.misconception_counts || [];
  const concepts = summary.criterion_performance || [];
  const topics = summary.topic_performance || [];

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Analytics</p>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">Cohort overview</h1>
          {summary.source_note && (
            <Badge tone={summary.source === "computed" ? "success" : "warning"}>
              {summary.source === "computed" ? "Live data" : "Demo cohort"}
            </Badge>
          )}
        </div>
        {(summary.source === "computed" || showSample) && (
          <Button variant="secondary" className="px-3 py-1.5 text-xs" onClick={() => setShowSample((value) => !value)}>
            {showSample ? "Return to live data" : "View demo cohort"}
          </Button>
        )}
      </div>
      {summary.source_note && <p className="-mt-4 mb-6 text-sm text-text-muted">{summary.source_note}</p>}

      <div className="mb-6 grid grid-cols-3 gap-4">
        <Stat label="Cohort size" value={summary.cohort_size} />
        <Stat label="Marked" value={summary.marked} />
        <Stat label="Mean %" value={`${summary.mean_percentage}%`} />
      </div>

      {summary.recommendation && (
        <Card className="mb-6">
          <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Recommendation</p>
          <p className="text-sm">{summary.recommendation}</p>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Strengths &amp; weaknesses</p>
          <p className="mb-4 text-xs text-text-muted">Mean score on each rubric concept, weakest first.</p>
          {concepts.length === 0 ? (
            <p className="text-sm text-text-muted">No marked submissions yet.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {concepts.map((c) => (
                <div key={c.criterion_id}>
                  <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                    <span className="min-w-0">
                      <span className="font-mono text-xs text-text-muted">{c.criterion_id}</span> {c.label}
                    </span>
                    <span className="shrink-0 font-mono tabular-nums">{c.mean_percentage}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-surface-2">
                    <div className={`h-full rounded-full ${bandBar(c.mean_percentage)}`} style={{ width: `${c.mean_percentage}%` }} />
                  </div>
                  <p className="mt-0.5 text-[10px] text-text-muted">
                    across {c.n} submission{c.n === 1 ? "" : "s"}
                  </p>
                </div>
              ))}
            </div>
          )}

          {topics.length > 0 && (
            <div className="mt-6 border-t border-border pt-4">
              <p className="mb-3 font-mono text-xs uppercase tracking-wide text-text-muted">By topic</p>
              <div className="flex flex-col gap-2">
                {topics.map((t) => (
                  <div key={t.topic} className="flex items-center justify-between gap-3 text-sm">
                    <span className="capitalize">{t.topic}</span>
                    <span className="flex items-center gap-2">
                      <span className="h-2 w-24 overflow-hidden rounded-full bg-surface-2">
                        <span className={`block h-full ${bandBar(t.mean_percentage)}`} style={{ width: `${t.mean_percentage}%` }} />
                      </span>
                      <span className="font-mono tabular-nums">{t.mean_percentage}%</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card>
          <p className="mb-3 font-mono text-xs uppercase tracking-wide text-text-muted">Misconceptions</p>
          {counts.length === 0 ? (
            <p className="text-sm text-text-muted">None flagged.</p>
          ) : (
            <div style={{ height: Math.max(160, counts.length * 36) }}>
              <Bar
                data={{
                  labels: counts.map((c) => humanizeTag(c.name)),
                  datasets: [
                    {
                      label: "Students affected",
                      data: counts.map((c) => c.count),
                      backgroundColor: "#a34f43",
                      borderRadius: 4,
                    },
                  ],
                }}
                options={{
                  indexAxis: "y" as const,
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: { legend: { display: false } },
                  scales: {
                    x: {
                      beginAtZero: true,
                      ticks: { precision: 0, color: "#71685b" },
                      grid: { color: "#d4c8b4" },
                      border: { color: "#d4c8b4" },
                    },
                    y: {
                      ticks: { color: "#71685b" },
                      grid: { display: false },
                      border: { color: "#d4c8b4" },
                    },
                  },
                }}
              />
            </div>
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <p className="mb-3 font-mono text-xs uppercase tracking-wide text-text-muted">Students</p>
        <table className="w-full text-sm">
          <tbody>
            {(summary.students || []).map((s, i) => {
              const clickable = !!s.submission_id;
              return (
                <tr
                  key={i}
                  onClick={() => clickable && setOpenStudent(s)}
                  className={`border-b border-border last:border-0 ${clickable ? "cursor-pointer hover:bg-surface-2" : ""}`}
                >
                  <td className="py-2 pr-2">{s.pseudonym}</td>
                  <td className="py-2 pr-2 font-mono text-xs text-text-muted">{s.question_id}</td>
                  <td className="py-2 pr-2 text-right font-mono tabular-nums">
                    {s.mark} / {s.max}
                  </td>
                  <td className="py-2 pl-2 text-text-muted">
                    {s.top_misconception ? humanizeTag(s.top_misconception) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(summary.students || []).some((s) => s.submission_id) && (
          <p className="mt-3 text-xs text-text-muted">Select a student to see their per-concept breakdown and feedback.</p>
        )}
      </Card>

      <StudentDetail row={openStudent} onClose={() => setOpenStudent(null)} />
    </div>
  );
}

function StudentDetail({ row, onClose }: { row: StudentRow | null; onClose: () => void }) {
  const [sub, setSub] = useState<Submission | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!row?.submission_id) return;
    setSub(null);
    setErr(null);
    setLoading(true);
    api
      .getSubmission(row.submission_id)
      .then(setSub)
      .catch(() => setErr("Could not load this submission."))
      .finally(() => setLoading(false));
  }, [row?.submission_id]);

  const marks = sub?.marks;
  const feedback = sub?.feedback as
    | { what_went_well?: string; what_went_wrong?: string; how_to_improve?: string }
    | null
    | undefined;

  return (
    <Dialog open={!!row} onOpenChange={(v) => !v && onClose()} title={row ? `${row.pseudonym} — ${row.question_id}` : ""}>
      {loading && <p className="text-sm text-text-muted">Loading…</p>}
      {err && <p className="text-sm text-danger">{err}</p>}
      {marks && (
        <div className="max-h-[70vh] overflow-y-auto pr-1">
          <div className="mb-4 flex items-baseline gap-2">
            <span className="font-mono text-2xl font-semibold tabular-nums">
              {marks.total_proposed} / {marks.total_max}
            </span>
            <span className="text-xs text-text-muted">total</span>
          </div>

          <p className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wide text-text-muted">Per concept</p>
          <div className="mb-4 flex flex-col gap-2">
            {marks.criteria.map((c) => (
              <div key={c.criterion_id} className="rounded-lg border border-border p-2.5 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-text-muted">
                    {c.criterion_id}
                    {c.overridden ? " · adjusted" : ""}
                  </span>
                  <span className="font-mono tabular-nums">
                    {c.proposed} / {c.max}
                  </span>
                </div>
                {c.justification && <p className="mt-1 text-xs leading-relaxed">{c.justification}</p>}
              </div>
            ))}
          </div>

          {!!marks.misconceptions?.length && (
            <div className="mb-4">
              <p className="mb-1.5 font-mono text-[11px] font-semibold uppercase tracking-wide text-text-muted">Learning gaps</p>
              <div className="flex flex-wrap gap-1.5">
                {marks.misconceptions.map((tag) => (
                  <Badge key={tag} tone="danger">
                    {humanizeTag(tag)}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {feedback && (
            <div className="flex flex-col gap-2 border-t border-border pt-3 text-sm">
              <FeedbackLine label="What went well" text={feedback.what_went_well} />
              <FeedbackLine label="What went wrong" text={feedback.what_went_wrong} />
              <FeedbackLine label="How to improve" text={feedback.how_to_improve} />
            </div>
          )}
        </div>
      )}
    </Dialog>
  );
}

function FeedbackLine({ label, text }: { label: string; text?: string }) {
  if (!text) return null;
  return (
    <div>
      <p className="font-mono text-[11px] font-semibold uppercase tracking-wide text-text-muted">{label}</p>
      <p className="mt-0.5 leading-relaxed">{text}</p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Card className="text-center">
      <p className="font-mono text-3xl font-semibold tabular-nums">{value}</p>
      <p className="mt-1 text-xs uppercase tracking-wide text-text-muted">{label}</p>
    </Card>
  );
}
