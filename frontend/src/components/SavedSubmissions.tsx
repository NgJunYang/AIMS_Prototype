import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useWorkbench } from "../state/WorkbenchContext";
import type { SubmissionSummary } from "../types";
import { Card } from "./ui/Card";
import { Button } from "./ui/Button";
import { Input, Label } from "./ui/Field";

export function SavedSubmissions({ onOpened }: { onOpened: () => void }) {
  const wb = useWorkbench();
  const [rows, setRows] = useState<SubmissionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [opening, setOpening] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api.listSubmissions().then((data) => { if (active) setRows(data); })
      .catch(() => { if (active) setError("Could not load saved submissions. Try refreshing the list."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);

  async function open(id: string) {
    setOpening(id);
    setError("");
    try { if (await wb.resumeSubmission(id)) onOpened(); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not open this submission."); }
    finally { setOpening(null); }
  }

  const filtered = rows.filter((s) => `${s.student_pseudonym} ${s.student_id || ""} ${s.question_id} ${s.assignment_id || ""}`.toLowerCase().includes(search.toLowerCase()));
  return (
    <Card className="mt-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Resume saved marking</h2>
        <Button variant="secondary" disabled={loading || !!opening} onClick={() => setRevision((r) => r + 1)}>Refresh list</Button>
      </div>
      <p className="mb-3 text-xs text-text-muted">Reopen the last saved version, including marks and feedback. Unsaved edits and untranscribed PDF files cannot be recovered after a reload.</p>
      <Label htmlFor="saved-search">Find a submission</Label>
      <Input id="saved-search" placeholder="Name, student ID, question or assignment" value={search} onChange={(e) => setSearch(e.target.value)} />
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
      {loading ? <p className="mt-3 text-sm text-text-muted">Loading saved submissions…</p> : (
        <ul className="mt-3 max-h-96 overflow-y-auto divide-y divide-border">
          {filtered.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="min-w-0 break-words">
                <p className="font-medium">{s.student_pseudonym}</p>
                <p className="text-xs text-text-muted">{s.student_id || "No student ID"} · {s.question_id} · {s.assignment_id || "No assignment"}</p>
                <p className="text-xs text-text-muted">{s.marked ? `${s.total_proposed}/${s.total_max} · ${s.channel === "tutorial" ? "Tutorial" : s.published ? "Published" : "Not published"}` : "Awaiting marking"}</p>
              </div>
              <Button variant="secondary" disabled={!!opening || wb.state.confirmBusy || wb.state.autoRefreshing || wb.state.reviewBusy} onClick={() => open(s.id)} aria-label={`Resume ${s.student_pseudonym} (${s.id})`}>
                {opening === s.id ? "Opening…" : "Resume marking"}
              </Button>
            </li>
          ))}
          {!filtered.length && <li className="py-3 text-sm text-text-muted">{rows.length ? "No matching submissions." : "No saved submissions yet."}</li>}
        </ul>
      )}
    </Card>
  );
}
