import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { Dialog } from "./ui/Dialog";
import { Button } from "./ui/Button";
import { Input, Label } from "./ui/Field";
import { StepList } from "./StepList";
import { api, ApiError } from "../lib/api";
import type { Criterion, Question, SolutionTranscription } from "../types";

function problemsFrom(err: unknown): string[] {
  if (err instanceof ApiError) {
    const detail = err.body && err.body.detail;
    if (Array.isArray(detail)) return detail;
    return [detail || err.message];
  }
  return [err instanceof Error ? err.message : "Something went wrong."];
}

export function QuestionEditor({
  question,
  onClose,
  onSaved,
}: {
  question: Question | null;
  onClose: () => void;
  onSaved: (id: string) => void;
}) {
  const editingId = question?.id ?? null;

  const [id, setId] = useState(question?.id || "");
  const [variable, setVariable] = useState(question?.variable || "x");
  const [prompt, setPrompt] = useState(question?.prompt || "");
  const [steps, setSteps] = useState<string[]>(question?.model_solution_steps || []);
  const [criteria, setCriteria] = useState<Criterion[]>(question?.criteria.map((c) => ({ ...c })) || []);

  const [solutionFile, setSolutionFile] = useState<File | null>(null);
  const [solutionObjectUrl, setSolutionObjectUrl] = useState<string | null>(null);
  const [solutionPageCount, setSolutionPageCount] = useState(1);
  const [solutionPage, setSolutionPage] = useState(1);
  const [solutionBusy, setSolutionBusy] = useState(false);
  const [solutionImageFilename, setSolutionImageFilename] = useState<string | null>(
    question?.solution_image_filename || null
  );
  const [solutionSourcePage, setSolutionSourcePage] = useState<number | null>(question?.solution_source_page || null);
  const [solutionTranscription, setSolutionTranscription] = useState<SolutionTranscription | null>(
    question?.solution_transcription || null
  );
  const [solutionStatus, setSolutionStatus] = useState<{ ok: boolean | null; message: string } | null>(null);

  const [checkResult, setCheckResult] = useState<{ ok: boolean; problems: string[] } | null>(null);
  const [saveError, setSaveError] = useState<string[] | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!question) {
      api
        .questionTemplate()
        .then((t) => {
          setVariable(t.variable || "x");
          setCriteria(t.criteria.map((c: Criterion) => ({ ...c })));
        })
        .catch(() => {
          /* fall back to an empty rubric rather than blocking */
        });
    }
    return () => {
      if (solutionObjectUrl) URL.revokeObjectURL(solutionObjectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Steps become editable once a transcription exists, or when editing a
  // question that already has a model solution — a new question's model
  // solution originates from a photograph, not from typing.
  const stepsUnlocked = editingId !== null || solutionTranscription !== null;
  const lowConfidence = new Set(
    (solutionTranscription?.steps || []).filter((s) => s.confidence === "low").map((s) => s.latex)
  );

  async function stageSolutionFile(file: File) {
    if (stepsUnlocked && steps.length && !window.confirm("Replace the current model solution with the transcription of this photo?")) {
      return;
    }
    if (solutionObjectUrl) URL.revokeObjectURL(solutionObjectUrl);
    setSolutionFile(file);
    setSolutionObjectUrl(URL.createObjectURL(file));
    setSolutionTranscription(null);
    setSolutionImageFilename(null);
    setSolutionSourcePage(null);
    setSolutionStatus(null);

    try {
      const info = await api.inspectUpload(file);
      setSolutionPageCount(info.page_count);
      if (info.page_count > 1) return; // reveals the page picker; lecturer chooses, then commits
      await doTranscribeSolution(file, 1);
    } catch (err) {
      setSolutionStatus({ ok: false, message: problemsFrom(err).join(" ") });
    }
  }

  async function doTranscribeSolution(file: File, page: number) {
    setSolutionBusy(true);
    setSolutionStatus({ ok: null, message: "Transcribing your handwriting…" });
    try {
      const result = await api.transcribeSolution(file, page);
      setSolutionTranscription(result.transcription);
      setSolutionImageFilename(result.image_filename);
      setSolutionSourcePage(result.page);
      setSolutionPageCount(result.page_count);
      const newSteps = result.transcription.steps.map((s: { latex: string }) => s.latex);
      setSteps(newSteps);
      const notes = result.transcription.notes;
      setSolutionStatus({
        ok: true,
        message: `Transcribed ${newSteps.length} line(s) from page ${result.page}.` + (notes ? ` Note: ${notes}` : ""),
      });
      if (id.trim() && prompt.trim()) {
        await runCheck({
          id: id.trim(),
          prompt: prompt.trim(),
          variable: variable.trim() || "x",
          topic_tag: "quadratics",
          model_solution_steps: newSteps.map((s: string) => s.trim()).filter((s: string) => s.length > 0),
          criteria: criteria.map((c) => ({ id: c.id, max: Number(c.max) || 0, description: c.description })),
          solution_image_filename: result.image_filename,
          solution_source_page: result.page,
          solution_transcription: result.transcription,
        });
      }
    } catch (err) {
      const hint = err instanceof ApiError ? err.body?.hint : undefined;
      setSolutionStatus({
        ok: false,
        message: hint ? `${hint} ${(err as ApiError).body?.detail || ""}` : problemsFrom(err).join(" "),
      });
    } finally {
      setSolutionBusy(false);
    }
  }

  function questionFromEditor() {
    return {
      id: id.trim(),
      prompt: prompt.trim(),
      variable: variable.trim() || "x",
      topic_tag: "quadratics",
      model_solution_steps: steps.map((s) => s.trim()).filter((s) => s.length > 0),
      criteria: criteria.map((c) => ({ id: c.id, max: Number(c.max) || 0, description: c.description })),
      solution_image_filename: solutionImageFilename,
      solution_source_page: solutionSourcePage,
      solution_transcription: solutionTranscription,
    };
  }

  async function runCheck(override?: ReturnType<typeof questionFromEditor>) {
    try {
      const result = await api.validateQuestion(override || questionFromEditor());
      setCheckResult({ ok: result.ok, problems: result.problems || [] });
    } catch (err) {
      setCheckResult({ ok: false, problems: problemsFrom(err) });
    }
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    const q = questionFromEditor();
    try {
      if (editingId) {
        await api.updateQuestion(editingId, q);
      } else {
        await api.createQuestion(q);
      }
      onSaved(q.id);
    } catch (err) {
      setSaveError(problemsFrom(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()} title={editingId ? `Edit ${editingId}` : "New question"}>
      <p className="mb-4 max-w-2xl text-xs text-text-muted">
        Your model solution is checked with the same symbolic engine that marks the students. If it loses or gains a
        solution anywhere, it is refused — a model solution that is wrong would mark every student against it
        wrongly.
      </p>

      <div className="mb-4 flex flex-wrap gap-4">
        <div>
          <Label>Id</Label>
          <Input value={id} disabled={!!editingId} onChange={(e) => setId(e.target.value)} placeholder="q7" className="w-32" />
        </div>
        <div>
          <Label>Variable</Label>
          <Input value={variable} maxLength={1} onChange={(e) => setVariable(e.target.value)} className="w-16" />
        </div>
        <div className="min-w-64 flex-1">
          <Label>
            Prompt <span className="normal-case font-normal text-text-muted">(use $…$ for maths)</span>
          </Label>
          <Input value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Solve $x^2 - 7x + 12 = 0$." />
        </div>
      </div>

      <div className="mb-4">
        <div className="mb-1.5 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Model solution</h3>
          <Button
            variant="secondary"
            className="px-2 py-1 text-xs"
            disabled={!stepsUnlocked || solutionBusy}
            onClick={() => setSteps((s) => [...s, ""])}
          >
            <Plus size={12} /> Add step
          </Button>
        </div>

        <div className="mb-3 flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-xs font-medium hover:border-accent/50">
              <span>{solutionTranscription || solutionImageFilename ? "Use a different photo" : "Photograph your worked solution"}</span>
              <input
                type="file"
                accept="image/*,application/pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) stageSolutionFile(file);
                  e.target.value = "";
                }}
              />
            </label>
            <span className="text-xs text-text-muted">
              {[solutionPageCount > 1 ? `${solutionPageCount} pages` : null, solutionSourcePage ? `transcribed from page ${solutionSourcePage}` : null]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </div>

          {solutionPageCount > 1 && solutionFile && (
            <div className="flex flex-wrap items-end gap-2">
              <div>
                <Label>Page</Label>
                <input
                  type="number"
                  min={1}
                  max={solutionPageCount}
                  value={solutionPage}
                  onChange={(e) => setSolutionPage(Number(e.target.value) || 1)}
                  className="w-20 rounded-lg border border-border bg-surface-2 px-2 py-1.5 text-right text-sm tabular-nums"
                />
              </div>
              <Button
                className="px-3 py-1.5 text-xs"
                disabled={solutionBusy}
                onClick={() => solutionFile && doTranscribeSolution(solutionFile, Math.min(Math.max(solutionPage, 1), solutionPageCount))}
              >
                Transcribe this page
              </Button>
            </div>
          )}

          {solutionObjectUrl && <img src={solutionObjectUrl} alt="Your handwritten model solution" className="w-full rounded-lg border border-border" />}

          {solutionStatus && (
            <p className={`text-sm ${solutionStatus.ok === false ? "text-danger" : solutionStatus.ok === true ? "text-success" : "text-text-muted"}`}>
              {solutionStatus.message}
            </p>
          )}

          <p className="max-w-2xl text-xs text-text-muted">
            The transcription reports your page exactly as written, mistakes included — a vision model that quietly
            corrected it would hide the error from the symbolic checker and you would never find out. Check it
            against your photo above, then check the maths.
          </p>
        </div>

        {!stepsUnlocked && (
          <p className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-text-muted">
            No model solution yet — photograph your handwritten working to begin.
          </p>
        )}
        {stepsUnlocked && (
          <StepList
            steps={steps.map((latex) => ({ latex }))}
            onChange={(idx, latex) => setSteps((s) => s.map((v, i) => (i === idx ? latex : v)))}
            onRemove={(idx) => setSteps((s) => s.filter((_, i) => i !== idx))}
            lowConfidenceSet={lowConfidence}
          />
        )}
      </div>

      <div className="mb-4">
        <div className="mb-1.5 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Rubric</h3>
          <Button
            variant="secondary"
            className="px-2 py-1 text-xs"
            onClick={() => setCriteria((c) => [...c, { id: `C${c.length + 1}`, max: 1, description: "" }])}
          >
            <Plus size={12} /> Add criterion
          </Button>
        </div>
        <div className="mb-1.5 grid grid-cols-[minmax(0,1fr)_4rem_4rem_1.5rem] items-center gap-2 px-1 text-[10px] font-medium uppercase tracking-wide text-text-muted">
          <span>Criterion description</span>
          <span>ID</span>
          <span>Max marks</span>
          <span />
        </div>
        <div className="flex flex-col gap-2">
          {criteria.map((c, idx) => (
            <div key={idx} className="grid grid-cols-[minmax(0,1fr)_4rem_4rem_1.5rem] items-center gap-2">
              <Input
                value={c.description}
                placeholder="What this criterion rewards"
                aria-label={`Description for criterion ${idx + 1}`}
                onChange={(e) => setCriteria((cs) => cs.map((v, i) => (i === idx ? { ...v, description: e.target.value } : v)))}
                className="min-w-0"
              />
              <Input
                value={c.id}
                aria-label={`ID for criterion ${idx + 1}`}
                onChange={(e) => setCriteria((cs) => cs.map((v, i) => (i === idx ? { ...v, id: e.target.value } : v)))}
                className="w-full font-mono text-xs"
              />
              <Input
                type="number"
                min={0}
                value={String(c.max)}
                aria-label={`Maximum marks for criterion ${idx + 1}`}
                onChange={(e) =>
                  setCriteria((cs) => cs.map((v, i) => (i === idx ? { ...v, max: Number(e.target.value) || 0 } : v)))
                }
                className="w-full px-2 text-right tabular-nums"
              />
              <button
                type="button"
                onClick={() => setCriteria((cs) => cs.filter((_, i) => i !== idx))}
                className="shrink-0 rounded p-1.5 text-text-muted hover:bg-danger-soft hover:text-danger"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {checkResult && (
        <div className={`mb-4 rounded-lg p-3 text-sm ${checkResult.ok ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>
          {checkResult.ok ? (
            <p>The model solution verifies against itself — every step preserves the solution set.</p>
          ) : (
            <ul className="list-inside list-disc space-y-1">
              {checkResult.problems.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {saveError && (
        <div className="mb-4 rounded-lg bg-danger-soft p-3 text-sm text-danger">
          <ul className="list-inside list-disc space-y-1">
            {saveError.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => runCheck()}>
          Check the maths
        </Button>
        <Button onClick={handleSave} disabled={saving}>
          Save question
        </Button>
      </div>
    </Dialog>
  );
}
