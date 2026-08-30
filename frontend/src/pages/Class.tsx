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
import { api } from "../lib/api";
import { humanizeTag } from "../lib/katex";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

interface ClassSummary {
  source_note?: string | null;
  source?: "computed" | "sample";
  cohort_size: number;
  marked: number;
  mean_percentage: number;
  recommendation?: string;
  misconception_counts?: { name: string; count: number }[];
  students?: { pseudonym: string; question_id: string; mark: number; max: number; top_misconception?: string | null }[];
}

export default function Class() {
  const [summary, setSummary] = useState<ClassSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .classSummary()
      .then(setSummary)
      .catch((err) => setError("Could not load class summary: " + (err instanceof Error ? err.message : String(err))));
  }, []);

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
        <p className="text-sm text-text-muted">Loading class summary…</p>
      </div>
    );
  }

  const counts = summary.misconception_counts || [];

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Class</p>
      <div className="mb-6 flex items-center gap-3">
        <h1 className="text-2xl font-semibold">Cohort overview</h1>
        {summary.source_note && (
          <Badge tone={summary.source === "computed" ? "success" : "warning"}>
            {summary.source === "computed" ? "Live data" : "Sample data"}
          </Badge>
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
          <p className="mb-3 font-mono text-xs uppercase tracking-wide text-text-muted">Misconceptions</p>
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
                plugins: {
                  legend: {
                    display: false,
                  },
                },
                scales: {
                  x: {
                    beginAtZero: true,
                    ticks: {
                      precision: 0,
                      color: "#71685b",
                    },
                    grid: {
                      color: "#d4c8b4",
                    },
                    border: {
                      color: "#d4c8b4",
                    },
                  },
                  y: {
                    ticks: {
                      color: "#71685b",
                    },
                    grid: {
                      display: false,
                    },
                    border: {
                      color: "#d4c8b4",
                    },
                  },
                },
              }}
            />
          </div>
        </Card>

        <Card>
          <p className="mb-3 font-mono text-xs uppercase tracking-wide text-text-muted">Students</p>
          <table className="w-full text-sm">
            <tbody>
              {(summary.students || []).map((s, i) => (
                <tr key={i} className="border-b border-border last:border-0">
                  <td className="py-2 pr-2">{s.pseudonym}</td>
                  <td className="py-2 pr-2 font-mono text-xs text-text-muted">{s.question_id}</td>
                  <td className="py-2 pr-2 text-right font-mono tabular-nums">
                    {s.mark} / {s.max}
                  </td>
                  <td className="py-2 pl-2 text-text-muted">{s.top_misconception ? humanizeTag(s.top_misconception) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
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
