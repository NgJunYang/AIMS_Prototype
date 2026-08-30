import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { Upload, Keyboard, Sparkles, Pencil, Trash2, Plus } from "lucide-react";
import { useWorkbench } from "../state/WorkbenchContext";
import { useToast } from "../components/ui/Toast";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Input, Label } from "../components/ui/Field";
import { Mixed, Katex } from "../components/Math";
import { QuestionEditor } from "../components/QuestionEditor";
import type { Question } from "../types";

export default function Setup({ onSubmissionCreated }: { onSubmissionCreated: () => void }) {
  const wb = useWorkbench();
  const toast = useToast();
  const { state } = wb;
  const [studentName, setStudentName] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorQuestion, setEditorQuestion] = useState<Question | null | undefined>(undefined);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    wb.loadQuestions().then((questions) => {
      if (questions.length) wb.selectQuestion(questions[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const q = state.currentQuestion;

  async function handleFile(file: File) {
    if (!state.currentQuestion) return;
    try {
      await wb.beginWithUpload(file, studentName, onSubmissionCreated);
    } catch (err) {
      toast.error(wb.problemsFrom(err).join(" "));
    }
  }

  async function handleTypeIn() {
    if (!state.currentQuestion) return;
    try {
      await wb.beginManualEntry([], studentName, onSubmissionCreated);
    } catch (err) {
      toast.error(wb.problemsFrom(err).join(" "));
    }
  }

  async function handleSampleScript() {
    const q2 = state.questions.find((qq) => qq.id === "q2");
    if (!q2) return;
    if (state.currentQuestion?.id !== "q2") {
      wb.selectQuestion("q2");
      setNotice("Switched to Q2 for the flagship sample script.");
    } else {
      setNotice(null);
    }
    try {
      await wb.beginManualEntry(
        [
          { latex: "x^2 = 5x", confidence: "high" },
          { latex: "x = 5", confidence: "high" },
        ],
        studentName,
        onSubmissionCreated,
        q2
      );
    } catch (err) {
      toast.error(wb.problemsFrom(err).join(" "));
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-wide text-text-muted">Setup</p>
          <h1 className="text-2xl font-semibold">Pick a question, then start marking</h1>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label>Student (optional)</Label>
            <Input
              value={studentName}
              onChange={(e) => setStudentName(e.target.value)}
              placeholder="e.g. Student A"
              className="w-full sm:w-44"
            />
          </div>
          <select
            className="h-[38px] w-full rounded-lg border border-border bg-surface-2 px-3 text-sm text-text outline-none focus:border-accent sm:w-auto"
            value={q?.id || ""}
            onChange={(e) => e.target.value && wb.selectQuestion(e.target.value)}
          >
            <option value="">Choose a question…</option>
            {state.questions.map((qq) => (
              <option key={qq.id} value={qq.id}>
                {qq.id} — {qq.prompt.replace(/\$/g, "")}
              </option>
            ))}
          </select>
          <Button
            variant="secondary"
            onClick={() => {
              setEditorQuestion(null);
              setEditorOpen(true);
            }}
          >
            <Plus size={14} /> New question
          </Button>
        </div>
      </div>

      {notice && (
        <div className="mb-6 rounded-lg border border-accent/30 bg-accent-soft px-4 py-2 text-sm text-accent-hover">
          {notice}
        </div>
      )}

      {q && (
        <motion.div
          key={q.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="grid gap-6 lg:grid-cols-[1.3fr_1fr]"
        >
          <Card>
            <div className="mb-4 flex items-start justify-between gap-3">
              <p className="font-mono text-xs uppercase tracking-wide text-text-muted">Prompt</p>
              <div className="flex gap-1">
                <button
                  onClick={() => {
                    setEditorQuestion(q);
                    setEditorOpen(true);
                  }}
                  title="Edit this question"
                  className="rounded p-1.5 text-text-muted hover:bg-surface-2 hover:text-text"
                >
                  <Pencil size={14} />
                </button>
                <button
                  onClick={async () => {
                    if (!window.confirm(`Delete question ${q.id}?`)) return;
                    try {
                      await wb.reloadQuestions(null);
                      toast.success(`Deleted ${q.id}.`);
                    } catch (err) {
                      toast.error(wb.problemsFrom(err).join(" "));
                    }
                  }}
                  title="Delete this question"
                  className="rounded p-1.5 text-text-muted hover:bg-danger-soft hover:text-danger"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
            <Mixed text={q.prompt} className="text-lg" />

            <p className="mb-2 mt-6 font-mono text-xs uppercase tracking-wide text-text-muted">Model solution</p>
            <ol className="flex flex-col gap-1.5">
              {q.model_solution_steps.map((step, i) => (
                <li key={i} className="rounded-md bg-surface-2 px-3 py-1.5 text-sm">
                  <Katex latex={step} />
                </li>
              ))}
            </ol>

            <p className="mb-2 mt-6 font-mono text-xs uppercase tracking-wide text-text-muted">Rubric</p>
            <table className="w-full text-sm">
              <tbody>
                {q.criteria.map((c) => (
                  <tr key={c.id} className="border-b border-border last:border-0">
                    <td className="py-2 pr-2 align-top font-mono text-xs text-text-muted">{c.id}</td>
                    <td className="py-2 pr-2 align-top">{c.description}</td>
                    <td className="py-2 pl-2 text-right align-top font-mono tabular-nums">{c.max}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card className="flex flex-col gap-3">
            <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Start marking</p>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,application/pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
                e.target.value = "";
              }}
            />
            <Button variant="secondary" onClick={() => fileInputRef.current?.click()} className="justify-start">
              <Upload size={16} /> Upload photo or PDF of working
            </Button>
            <Button variant="secondary" onClick={handleTypeIn} className="justify-start">
              <Keyboard size={16} /> Type it in
            </Button>
            <Button variant="secondary" onClick={handleSampleScript} className="justify-start">
              <Sparkles size={16} /> Use a sample script
            </Button>
          </Card>
        </motion.div>
      )}

      {editorOpen && (
        <QuestionEditor
          question={editorQuestion || null}
          onClose={() => setEditorOpen(false)}
          onSaved={async (id) => {
            setEditorOpen(false);
            await wb.reloadQuestions(id);
            setNotice(`Saved ${id}.`);
          }}
        />
      )}
    </div>
  );
}
