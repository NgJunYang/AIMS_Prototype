import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { api } from "../lib/api";
import { ingestionApi } from "../lib/ingestionApi";
import { useWorkbench } from "../state/WorkbenchContext";
import type { AssignmentReviewStatus, ImportQuestion, ImportWorking, TutorialImport } from "../types";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { Input, Label, Textarea } from "./ui/Field";
import { StepList } from "./StepList";
import { ImportSourcePages } from "./ImportSourcePages";

export function TutorialImportPanel({ assignmentId, ready, onChanged, onOpen }: {
  assignmentId: string; ready: boolean; onChanged: () => void; onOpen: () => void;
}) {
  const wb = useWorkbench();
  const [draft, setDraft] = useState<TutorialImport | null>(null);
  const [imports, setImports] = useState<TutorialImport[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [markErrors, setMarkErrors] = useState<string[]>([]);
  const [progress, setProgress] = useState<AssignmentReviewStatus | null>(null);

  useEffect(() => { ingestionApi.list(assignmentId).then(setImports).catch((e) => setError(String(e.message))); }, [assignmentId, draft?.revision, draft?.id]);
  useEffect(() => {
    let active = true;
    setProgress(null);
    const anchor = draft?.submission_ids[0];
    if (anchor) api.assignmentReviewStatus(anchor).then((value) => { if (active) setProgress(value); }).catch((e) => { if (active) setError(String(e.message)); });
    return () => { active = false; };
  }, [draft]);

  async function run(message: string, task: () => Promise<void>) {
    if (busy) return;
    setBusy(message); setError("");
    try { await task(); }
    catch (e) { setError(e instanceof Error ? e.message : "Import failed. Your saved work is unchanged."); }
    finally { setBusy(""); }
  }
  function updateQuestion(index: number, patch: Partial<ImportQuestion>) {
    setDraft((d) => d && ({ ...d, questions: d.questions.map((q, i) => i === index ? { ...q, ...patch } : q),
      solutions: d.solutions.map((s) => s.question_id === d.questions[index].question_id ? { ...s, confirmed: false } : s) }));
  }
  function updateWorking(index: number, patch: Partial<ImportWorking>) {
    const field = draft!.stage === "solutions" ? "solutions" : "answers";
    setDraft((d) => d && ({ ...d, [field]: d[field].map((w, i) => i === index ? { ...w, confirmed: false, ...patch } : w) }));
  }
  async function mark(id: string) {
    const result = await ingestionApi.mark(id);
    setMarkErrors(result.results.filter((r) => r.error).map((r) => `${r.question_id}: ${r.error}`));
    setDraft(await ingestionApi.get(id));
  }
  const working = draft?.stage === "solutions" ? draft.solutions : draft?.answers || [];
  const mappingsReady = !!draft && working.length === draft.questions.length && working.every((s) => s.confirmed && s.question_id) &&
    new Set(working.map((s) => s.question_id)).size === draft.questions.length;

  return <section className="mt-5 border-t border-border pt-4" aria-label="Whole tutorial PDF import">
    <h3 className="text-sm font-semibold tracking-tight">Whole tutorial PDF import</h3>
    <p className="mb-4 mt-1.5 max-w-2xl text-xs leading-relaxed text-text-muted">Review the detected content before saving or marking. Up to 20 pages / 20 MB per PDF. Results stay private until final tutorial publication.</p>
    {error && <p role="alert" className="my-3 rounded-lg border border-danger/20 bg-danger-soft/50 px-3 py-2.5 text-sm text-danger">{error}</p>}
    <fieldset disabled={!!busy} className="min-w-0 disabled:opacity-60">
      <div className="flex flex-wrap gap-4">
        {!ready && <PdfInput label="Upload Question Paper PDF" onFile={(file) => run("Detecting questions…", async () => { setDraft(await ingestionApi.questions(assignmentId, file)); setMarkErrors([]); })} />}
        {ready && <PdfInput label="Upload Completed Tutorial PDF" onFile={(file) => run("Detecting student answers…", async () => { setDraft(await ingestionApi.student(assignmentId, file)); setMarkErrors([]); })} />}
      </div>
      {imports.length > 0 && <label className="my-3 block text-xs text-text-muted">Resume saved import{" "}
        <select aria-label="Resume saved import" value={draft?.id || ""} onChange={(e) => e.target.value && run("Loading import…", async () => { setDraft(await ingestionApi.get(e.target.value)); setMarkErrors([]); })} className="mt-1 w-full rounded border border-border bg-surface p-2">
          <option value="">Choose an import</option>
          {imports.map((item) => <option key={item.id} value={item.id}>{item.filename} · {item.kind} · {item.stage} · {item.id}</option>)}
        </select>
      </label>}
      {draft && <div className="mt-4 space-y-4">
        <p className="text-sm font-semibold">{draft.filename} <Badge tone="neutral">{draft.stage}</Badge></p>
        {draft.warnings.map((warning, i) => <p key={i} className="text-xs text-warning">{warning}</p>)}
        <details><summary className="cursor-pointer text-xs text-accent-hover">Inspect original {draft.stage === "solutions" && draft.solution_page_count ? "solution" : "uploaded"} PDF pages</summary>
          <ImportSourcePages key={`${draft.id}-${draft.stage}`} id={draft.id} solution={draft.stage === "solutions" && !!draft.solution_page_count} pages={Array.from({ length: draft.stage === "solutions" && draft.solution_page_count ? draft.solution_page_count : draft.page_count }, (_, i) => i + 1)} />
        </details>

        {(draft.stage === "questions" || draft.stage === "solutions") && <>
          <h4 className="font-semibold">{draft.stage === "questions" ? "Detected Questions" : "Confirmed Questions"} · {draft.questions.length}</h4>
          {draft.questions.map((question, index) => <div key={question.question_id || index} className="space-y-2 rounded-lg border border-border bg-surface-2 p-3">
            <Label>Question label</Label><Input aria-label={`Question ${index + 1} label`} value={question.label} onChange={(e) => updateQuestion(index, { label: e.target.value })} />
            <Label>Question text</Label><Textarea aria-label={`Question ${index + 1} text`} value={question.prompt} onChange={(e) => updateQuestion(index, { prompt: e.target.value })} />
            {question.confidence === "low" && <Badge tone="warning">Check detected question</Badge>}
            {question.notes && <p className="text-xs text-text-muted">{question.notes}</p>}
            {question.problems.map((problem, i) => <p key={i} className="text-xs text-warning">{problem}</p>)}
            <PageNumbers value={question.source_pages} onChange={(source_pages) => updateQuestion(index, { source_pages })} />
            <div className="flex gap-2">
              <Input aria-label={`Variable for ${question.label}`} value={question.variable} className="w-20" onChange={(e) => updateQuestion(index, { variable: e.target.value })} />
              <Input aria-label={`Topic for ${question.label}`} value={question.topic_tag} onChange={(e) => updateQuestion(index, { topic_tag: e.target.value })} />
            </div>
            {draft.stage === "questions" && <div className="flex gap-2">
              <Button variant="ghost" aria-label={`Move ${question.label} up`} disabled={index === 0} onClick={() => setDraft({ ...draft, questions: move(draft.questions, index, -1) })}><ArrowUp size={13} /></Button>
              <Button variant="ghost" aria-label={`Move ${question.label} down`} disabled={index === draft.questions.length - 1} onClick={() => setDraft({ ...draft, questions: move(draft.questions, index, 1) })}><ArrowDown size={13} /></Button>
              <Button variant="ghost" aria-label={`Delete ${question.label}`} onClick={() => setDraft({ ...draft, questions: draft.questions.filter((_, i) => i !== index) })}><Trash2 size={13} /></Button>
            </div>}
          </div>)}
          {draft.stage === "questions" && <>
            <Button variant="secondary" onClick={() => setDraft({ ...draft, questions: [...draft.questions, { question_id: null, label: "", prompt: "", variable: "x", topic_tag: "quadratics", source_pages: [], confidence: "low", notes: "Manually added", problems: [] }] })}><Plus size={13} /> Add Question</Button>
            <Button className="ml-2" disabled={!draft.questions.length} onClick={() => run("Saving question drafts…", async () => setDraft(await ingestionApi.confirmQuestions(draft)))}>Confirm Questions</Button>
          </>}
          {draft.stage === "solutions" && <PdfInput label="Upload Model Solutions PDF" onFile={(file) => run("Matching model solutions…", async () => setDraft(await ingestionApi.solutions(draft, file)))} />}
        </>}

        {draft.stage === "answers" && <div className="grid gap-3 sm:grid-cols-2">
          <div><Label>Student name</Label><Input aria-label="Imported student name" value={draft.identity.name || ""} onChange={(e) => setDraft({ ...draft, identity: { ...draft.identity, name: e.target.value } })} /></div>
          <div><Label>Student ID</Label><Input aria-label="Imported student ID" value={draft.identity.student_id || ""} onChange={(e) => setDraft({ ...draft, identity: { ...draft.identity, student_id: e.target.value } })} /></div>
          {draft.identity.confidence === "low" && <p className="text-xs text-warning">Check the extracted identity against the source.</p>}
        </div>}
        {(draft.stage === "answers" || draft.stage === "solutions" && draft.solution_page_count > 0) && <>
          <h4 className="font-semibold">{draft.stage === "answers" ? "Detected Student Answers" : "Model Solution Matching"}</h4>
          {working.map((item, index) => <div key={item.block_id || index} className="space-y-3 rounded-lg border border-border p-3">
            <div className="flex items-center justify-between gap-2"><span className="font-mono text-sm">{item.label || "Unlabelled block"}</span><Badge tone={item.confirmed ? "success" : item.status === "detected" ? "neutral" : "warning"}>{item.confirmed ? "Confirmed" : item.status === "not_detected" ? "No answer detected" : item.status === "uncertain" ? "Review required" : "Detected — check mapping"}</Badge></div>
            <label className="block text-xs">Matches question
              <select aria-label={`Mapping ${index + 1}`} className="mt-1 w-full rounded border border-border bg-surface p-2" value={item.question_id || ""} onChange={(e) => updateWorking(index, { question_id: e.target.value || null })}>
                <option value="">Unmatched — choose question</option>{draft.questions.map((q) => <option key={q.question_id} value={q.question_id!}>{q.label}: {q.prompt.slice(0, 90)}</option>)}
              </select>
            </label>
            {item.notes && <p className="text-xs text-text-muted">{item.notes}</p>}
            <PageNumbers value={item.source_pages} onChange={(source_pages) => updateWorking(index, { source_pages })} />
            <StepList steps={item.steps} onChange={(idx, latex) => updateWorking(index, { status: "detected", steps: item.steps.map((s, i) => i === idx ? { ...s, latex } : s) })} onRemove={(idx) => updateWorking(index, { steps: item.steps.filter((_, i) => i !== idx) })} />
            <Button variant="secondary" onClick={() => updateWorking(index, { status: "detected", steps: [...item.steps, { index: item.steps.length + 1, latex: "", confidence: "high" }] })}><Plus size={13} /> Add working line</Button>
            {draft.stage === "solutions" && <div className="space-y-2">
              <p className="text-xs font-semibold">Master rubric draft</p>
              {item.criteria.map((criterion, ci) => <div key={ci} className="flex gap-2">
                <Input aria-label={`Criterion ${index + 1}.${ci + 1} ID`} className="w-20" value={criterion.id} onChange={(e) => updateWorking(index, { criteria: item.criteria.map((c, i) => i === ci ? { ...c, id: e.target.value } : c) })} />
                <Textarea aria-label={`Criterion ${index + 1}.${ci + 1} description`} value={criterion.description} onChange={(e) => updateWorking(index, { criteria: item.criteria.map((c, i) => i === ci ? { ...c, description: e.target.value } : c) })} />
                <Input type="number" min={0} aria-label={`Criterion ${index + 1}.${ci + 1} marks`} className="w-20" value={criterion.max} onChange={(e) => updateWorking(index, { criteria: item.criteria.map((c, i) => i === ci ? { ...c, max: Number(e.target.value) } : c) })} />
                <Button variant="ghost" aria-label={`Remove criterion ${index + 1}.${ci + 1}`} onClick={() => updateWorking(index, { criteria: item.criteria.filter((_, i) => i !== ci) })}><Trash2 size={13} /></Button>
              </div>)}
              <Button variant="secondary" onClick={() => updateWorking(index, { criteria: [...item.criteria, { id: `C${item.criteria.length + 1}`, max: 1, description: "" }] })}>Add criterion</Button>
            </div>}
            {draft.stage === "answers" && <Button variant="ghost" onClick={() => updateWorking(index, { steps: [], status: "not_detected" })}>Set unanswered (clear working)</Button>}
            <Button variant="ghost" onClick={() => setDraft({ ...draft, [draft.stage === "solutions" ? "solutions" : "answers"]: working.filter((_, i) => i !== index) })}>Delete extra block</Button>
            <label className="flex items-start gap-2 text-xs"><input aria-label={`Confirm block ${index + 1}`} type="checkbox" checked={item.confirmed} onChange={(e) => updateWorking(index, { confirmed: e.target.checked })} />I checked this mapping, working{draft.stage === "solutions" ? " and rubric" : " (including any missing answer)"} against the source.</label>
          </div>)}
          <Button variant="secondary" onClick={() => setDraft({ ...draft, [draft.stage === "solutions" ? "solutions" : "answers"]: [...working, { block_id: crypto.randomUUID(), label: "Manual block", question_id: null, steps: [], source_pages: [], criteria: [], confidence: "low", status: "not_detected", notes: "Manually added", confirmed: false }] })}>Add missing block</Button>
          <Button className="ml-2" disabled={!mappingsReady} onClick={() => run(draft.stage === "solutions" ? "Validating solutions and rubrics…" : "Creating submissions and marking questions…", async () => {
            if (draft.stage === "solutions") { setDraft(await ingestionApi.confirmSolutions(draft)); onChanged(); await wb.loadQuestions(); }
            else { const saved = await ingestionApi.confirmAnswers(draft); setDraft(saved); await mark(saved.id); }
          })}>{draft.stage === "solutions" ? "Confirm Solutions & Rubrics" : "Confirm & Start Marking"}</Button>
        </>}
        {draft.stage === "complete" && draft.kind === "setup" && <p className="text-sm text-success">Tutorial setup complete. Upload a completed student tutorial next.</p>}
        {draft.stage === "complete" && draft.kind === "student" && <>
          <p className="text-sm">{draft.submission_ids.length} individual submissions saved.</p>
          {progress && <p className="text-sm">AI marking: {progress.questions.filter((q) => q.marked).length} / {progress.total_questions} · Instructor review: {progress.reviewed_count} / {progress.total_questions} · Published: {progress.published ? "Yes" : "No"}</p>}
          {markErrors.map((message) => <p key={message} role="alert" className="text-xs text-danger">{message}</p>)}
          <Button variant="secondary" onClick={() => run("Marking incomplete questions…", async () => mark(draft.id))}>Start / Retry Incomplete Marking</Button>
          <Button className="ml-2" onClick={() => run("Opening instructor review…", async () => { if (await wb.resumeSubmission(draft.submission_ids[0])) onOpen(); })}>Open Instructor Review</Button>
        </>}
      </div>}
    </fieldset>
    {busy && <p role="status" className="mt-3 flex gap-2 text-sm text-text-muted"><RefreshCw size={15} className="animate-spin" />{busy}</p>}
  </section>;
}

function PdfInput({
  label,
  onFile,
}: {
  label: string;
  onFile: (file: File) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState("");

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-3">
      <input
        ref={fileRef}
        aria-label={label}
        className="hidden"
        type="file"
        accept="application/pdf,.pdf"
        onChange={(e) => {
          const file = e.target.files?.[0];

          if (file) {
            setSelectedFile(file.name);
            onFile(file);
          }

          e.target.value = "";
        }}
      />

      <Button
        type="button"
        variant="secondary"
        className="cursor-pointer px-3 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
        onClick={() => fileRef.current?.click()}
      >
        <Upload size={13} aria-hidden="true" />
        {label}
      </Button>
      {selectedFile && <p className="min-w-0 truncate text-xs text-text-muted" title={selectedFile}>Selected: {selectedFile}</p>}
    </div>
  );
}

function PageNumbers({ value, onChange }: { value: number[]; onChange: (pages: number[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  useEffect(() => setText(value.join(", ")), [value]);
  return <label className="block text-xs text-text-muted">Source pages (comma-separated)<Input aria-label="Source pages" value={text} onChange={(e) => setText(e.target.value)} onBlur={() => onChange(text.trim() ? text.split(",").map((p) => Number(p.trim())) : [])} /></label>;
}
function move<T>(items: T[], index: number, offset: number) {
  const next = [...items];
  [next[index], next[index + offset]] = [next[index + offset], next[index]];
  return next;
}
