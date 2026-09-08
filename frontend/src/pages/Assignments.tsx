import { useEffect, useRef, useState } from "react";
import { Plus, Trash2, Upload, Users } from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Input, Label } from "../components/ui/Field";
import { useToast } from "../components/ui/Toast";
import { api, ApiError } from "../lib/api";
import type { Question } from "../types";

interface Roster {
  name: string;
  student_id: string;
}
interface Assignment {
  id: string;
  title: string;
  kind: "tutorial" | "ca" | "exam";
  question_ids: string[];
  roster: Roster[];
  created_at: string;
}

const KIND_LABEL: Record<Assignment["kind"], string> = {
  tutorial: "Tutorial",
  ca: "Graded CA",
  exam: "Final exam",
};

function err(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.body?.detail;
    return Array.isArray(d) ? d.join(" ") : String(d || e.message);
  }
  return e instanceof Error ? e.message : "Something went wrong.";
}

export default function Assignments() {
  const toast = useToast();
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [creating, setCreating] = useState(false);

  async function reload() {
    try {
      setAssignments(await api.listAssignments());
    } catch (e) {
      toast.error(err(e));
    }
  }

  useEffect(() => {
    reload();
    api.listQuestions().then(setQuestions).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Assignments</p>
          <h1 className="text-2xl font-semibold">Activities &amp; rosters</h1>
        </div>
        <Button onClick={() => setCreating((v) => !v)}>
          <Plus size={14} /> New assignment
        </Button>
      </div>

      {creating && (
        <CreateForm
          questions={questions}
          onCancel={() => setCreating(false)}
          onCreated={async () => {
            setCreating(false);
            await reload();
          }}
        />
      )}

      {assignments.length === 0 && !creating ? (
        <p className="rounded-lg border border-dashed border-border p-8 text-center text-text-muted">
          No assignments yet. Create one to group questions and attach a class roster.
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          {assignments.map((a) => (
            <AssignmentCard key={a.id} assignment={a} onChanged={reload} />
          ))}
        </div>
      )}
    </div>
  );
}

function CreateForm({
  questions,
  onCancel,
  onCreated,
}: {
  questions: Question[];
  onCancel: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [id, setId] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<Assignment["kind"]>("tutorial");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  function toggle(qid: string) {
    setPicked((cur) => {
      const next = new Set(cur);
      if (next.has(qid)) next.delete(qid);
      else next.add(qid);
      return next;
    });
  }

  async function submit() {
    if (busy) return;
    if (!id.trim() || !title.trim()) return toast.error("An id and a title are required.");
    setBusy(true);
    try {
      await api.createAssignment({
        id: id.trim(),
        title: title.trim(),
        kind,
        question_ids: [...picked],
      });
      toast.success("Assignment created.");
      onCreated();
    } catch (e) {
      toast.error(err(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-6 flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <Label htmlFor="a-id">Short id</Label>
          <Input id="a-id" value={id} onChange={(e) => setId(e.target.value)} placeholder="week5" />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="a-title">Title</Label>
          <Input id="a-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Week 5 Tutorial" />
        </div>
      </div>
      <div>
        <Label>Type</Label>
        <div className="flex flex-wrap gap-2">
          {(["tutorial", "ca", "exam"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={`rounded-md border px-3 py-1.5 text-sm font-medium ${
                kind === k ? "border-accent bg-accent text-white" : "border-border text-text-muted hover:text-text"
              }`}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>
      </div>
      <div>
        <Label>Questions</Label>
        <div className="flex max-h-48 flex-col gap-1 overflow-y-auto rounded-lg border border-border p-2">
          {questions.map((q) => (
            <label key={q.id} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-surface-2">
              <input type="checkbox" checked={picked.has(q.id)} onChange={() => toggle(q.id)} />
              <span className="font-mono text-xs text-text-muted">{q.id}</span>
              <span className="truncate">{q.prompt.replace(/\$/g, "")}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="flex gap-2">
        <Button onClick={submit} disabled={busy}>
          Create
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </Card>
  );
}

function AssignmentCard({ assignment, onChanged }: { assignment: Assignment; onChanged: () => void }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [roster, setRoster] = useState<Roster[]>(assignment.roster);
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    try {
      const updated = await api.uploadRoster(assignment.id, file);
      setRoster(updated.roster);
      toast.success(`Roster: ${updated.roster.length} students.`);
    } catch (e) {
      toast.error(err(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete assignment ${assignment.id}?`)) return;
    try {
      await api.deleteAssignment(assignment.id);
      toast.success("Deleted.");
      onChanged();
    } catch (e) {
      toast.error(err(e));
    }
  }

  return (
    <Card>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-semibold">{assignment.title}</h2>
            <Badge tone={assignment.kind === "tutorial" ? "success" : "accent"}>{KIND_LABEL[assignment.kind]}</Badge>
          </div>
          <p className="mt-0.5 font-mono text-xs text-text-muted">
            {assignment.id} · {assignment.question_ids.join(", ") || "no questions"}
          </p>
        </div>
        <button onClick={remove} className="rounded p-1.5 text-text-muted hover:bg-danger-soft hover:text-danger">
          <Trash2 size={14} />
        </button>
      </div>

      <p className="mb-3 text-xs text-text-muted">CSV format: name,student_id headers in either order (Student Name and Student ID also work). Without headers, put names first and IDs second. Uploading replaces the current roster; invalid files leave it unchanged.</p>
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
            e.target.value = "";
          }}
        />
        <Button variant="secondary" className="px-3 py-1.5 text-xs" disabled={busy} onClick={() => fileRef.current?.click()}>
          <Upload size={13} /> Upload roster (CSV)
        </Button>
        <button
          className="inline-flex cursor-not-allowed items-center gap-1 rounded-md border border-dashed border-border px-3 py-1.5 text-xs text-text-muted"
          title="xSiTe sync is not available in this prototype"
          disabled
        >
          Sync from xSiTe (coming soon)
        </button>
        {roster.length > 0 && (
          <span className="inline-flex items-center gap-1 text-xs text-text-muted">
            <Users size={13} /> {roster.length} students
          </span>
        )}
      </div>

      {roster.length > 0 && (
        <table className="mt-3 w-full text-sm">
          <tbody>
            {roster.map((r, i) => (
              <tr key={i} className="border-b border-border last:border-0">
                <td className="py-1.5 pr-2">{r.name}</td>
                <td className="py-1.5 font-mono text-xs text-text-muted">{r.student_id || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
