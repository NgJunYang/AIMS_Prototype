import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  Copy,
  Keyboard,
  Loader2,
  Mail,
  RefreshCw,
  Send,
  Sparkles,
  Upload,
} from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Input, Label, Textarea } from "../components/ui/Field";
import { StepList } from "../components/StepList";
import { Katex, Mixed } from "../components/Math";
import { useToast } from "../components/ui/Toast";
import { api, ApiError } from "../lib/api";
import { humanizeTag } from "../lib/katex";
import type { Question } from "../types";

type Stage = "pick" | "verify" | "result";
interface EditStep {
  latex: string;
  confidence?: "high" | "low";
}
interface StudentCriterion {
  criterion_id: string;
  proposed: number;
  max: number;
  justification: string;
}
interface StudentView {
  channel: "tutorial" | "test";
  question_id: string;
  question_prompt: string;
  student_pseudonym: string;
  total_proposed: number;
  total_max: number;
  criteria: StudentCriterion[];
  feedback: { what_went_well: string; what_went_wrong: string; how_to_improve: string; references: string[] } | null;
  practice: any[];
  final_answer_correct: boolean;
  final_answer_verified: boolean;
}
type ChatMsg = { role: "user" | "assistant"; content: string };

function problem(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.body?.detail;
    return Array.isArray(d) ? d.join(" ") : String(d || err.message);
  }
  return err instanceof Error ? err.message : "Something went wrong.";
}

export default function Student() {
  const toast = useToast();
  const [stage, setStage] = useState<Stage>("pick");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [questionId, setQuestionId] = useState("");
  const [name, setName] = useState("");
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [scanUrl, setScanUrl] = useState<string | null>(null);
  const [steps, setSteps] = useState<EditStep[]>([]);
  const [busy, setBusy] = useState(false);
  const [busyMsg, setBusyMsg] = useState("");
  const [view, setView] = useState<StudentView | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [resultCode, setResultCode] = useState(() => new URLSearchParams(window.location.search).get("result") || "");
  const [resultError, setResultError] = useState("");

  async function openResult(id: string) {
    if (!id.trim() || busy) return;
    setBusy(true);
    setBusyMsg("Loading your released result…");
    setResultError("");
    setView(null);
    try {
      const result = await api.studentView(id.trim());
      setSubmissionId(id.trim());
      setView(result);
      setStage("result");
      const url = new URL(window.location.href);
      url.searchParams.set("result", id.trim());
      window.history.replaceState(null, "", url);
    } catch (err) {
      setResultError(err instanceof ApiError && err.status === 403
        ? "This result has not been released, or the instructor has unpublished it."
        : err instanceof ApiError && err.status === 404
          ? "No result was found for that code. Check the code with your instructor."
          : problem(err));
      setStage("pick");
    } finally { setBusy(false); }
  }

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("result");
    if (id) void openResult(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    api
      .listQuestions()
      .then((qs: Question[]) => {
        setQuestions(qs);
        if (qs.length) setQuestionId(qs[0].id);
      })
      .catch((err) => toast.error(problem(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const question = useMemo(() => questions.find((q) => q.id === questionId) || null, [questions, questionId]);

  async function begin(): Promise<string | null> {
    const sub = await api.createSubmission(questionId, name.trim() || "Student", "tutorial");
    setSubmissionId(sub.id);
    return sub.id;
  }

  async function handleFile(file: File) {
    if (!questionId || busy) return;
    setBusy(true);
    setBusyMsg("Reading your working…");
    try {
      const id = await begin();
      if (!id) return;
      setScanUrl(URL.createObjectURL(file));
      const updated = await api.transcribe(id, file, 1);
      setSteps(((updated.transcription?.steps as EditStep[]) || []).map((s) => ({ ...s })));
      setStage("verify");
    } catch (err) {
      toast.error(problem(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleTypeIn() {
    if (!questionId || busy) return;
    setBusy(true);
    try {
      const id = await begin();
      if (!id) return;
      setScanUrl(null);
      setSteps([{ latex: "", confidence: "high" }]);
      setStage("verify");
    } catch (err) {
      toast.error(problem(err));
    } finally {
      setBusy(false);
    }
  }

  async function confirmAndScore() {
    if (!submissionId || busy) return;
    if (!steps.some((s) => s.latex.trim())) {
      toast.error("Add at least one line of working first.");
      return;
    }
    setBusy(true);
    setBusyMsg("Checking your working and preparing feedback…");
    try {
      const payload = steps.map((s, i) => ({ index: i + 1, latex: s.latex, confidence: s.confidence || "high" }));
      await api.updateSteps(submissionId, payload);
      await api.mark(submissionId);
      setView(await api.studentView(submissionId));
      setStage("result");
    } catch (err) {
      toast.error(problem(err));
    } finally {
      setBusy(false);
    }
  }

  function restart() {
    const url = new URL(window.location.href);
    url.searchParams.delete("result");
    window.history.replaceState(null, "", url);
    setResultError("");
    setStage("pick");
    setSubmissionId(null);
    setScanUrl(null);
    setSteps([]);
    setView(null);
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Student</p>
      <h1 className="mb-6 text-2xl font-semibold">Check your working and get feedback</h1>

      {stage === "pick" && (
        <Card className="mb-6">
          <h2 className="mb-2 text-lg font-semibold">Open an instructor-released result</h2>
          <p className="mb-3 text-sm text-text-muted">Use the result link from your instructor, or enter its result code below.</p>
          <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={(e) => { e.preventDefault(); void openResult(resultCode); }}>
            <div className="min-w-0 flex-1"><Label htmlFor="result-code">Result code</Label><Input id="result-code" value={resultCode} onChange={(e) => setResultCode(e.target.value)} /></div>
            <Button type="submit" disabled={busy || !resultCode.trim()}>Open result</Button>
          </form>
          {resultError && <p role="alert" className="mt-3 text-sm text-danger">{resultError}</p>}
        </Card>
      )}

      {stage === "pick" && (
        <Card className="flex flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="student-name">Your name</Label>
              <Input id="student-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Alex Tan" />
            </div>
            <div>
              <Label htmlFor="student-question">Question</Label>
              <select
                id="student-question"
                className="h-[38px] w-full rounded-lg border border-border bg-surface-2 px-3 text-sm text-text outline-none focus:border-accent"
                value={questionId}
                onChange={(e) => setQuestionId(e.target.value)}
              >
                {questions.map((q) => (
                  <option key={q.id} value={q.id}>
                    {q.id} — {q.prompt.replace(/\$/g, "")}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {question && (
            <div className="rounded-lg border border-border bg-surface-2/50 p-3">
              <p className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-wide text-text-muted">The question</p>
              <Mixed text={question.prompt} className="text-sm" />
            </div>
          )}

          <input
            ref={fileRef}
            type="file"
            accept="image/*,application/pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
              e.target.value = "";
            }}
          />
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => fileRef.current?.click()} disabled={busy || !questionId}>
              <Upload size={16} /> Upload a photo of my working
            </Button>
            <Button variant="secondary" onClick={handleTypeIn} disabled={busy || !questionId}>
              <Keyboard size={16} /> Type it in instead
            </Button>
          </div>
          {busy && (
            <p className="flex items-center gap-2 text-sm text-text-muted">
              <Loader2 className="animate-spin" size={14} /> {busyMsg}
            </p>
          )}
        </Card>
      )}

      {stage === "verify" && (
        <Card className="flex flex-col gap-4">
          <div className="rounded-lg border border-accent/25 bg-accent-soft/40 p-3 text-sm text-accent-hover">
            Check the digitised version below matches your handwriting. Fix any line that came out wrong before you
            continue — your score and feedback are based on exactly this.
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <p className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wide text-text-muted">Your scan</p>
              {scanUrl ? (
                <img src={scanUrl} alt="Your uploaded working" className="w-full rounded-lg border border-border bg-white" />
              ) : (
                <div className="grid h-40 place-items-center rounded-lg border border-dashed border-border text-sm text-text-muted">
                  Typed in — no photo
                </div>
              )}
            </div>
            <div>
              <p className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wide text-text-muted">Digitised working</p>
              <StepList
                steps={steps}
                onChange={(i, latex) => setSteps((cur) => cur.map((s, idx) => (idx === i ? { ...s, latex } : s)))}
                onRemove={(i) => setSteps((cur) => cur.filter((_, idx) => idx !== i))}
              />
              <Button
                variant="secondary"
                className="mt-2 px-2.5 py-1 text-xs"
                onClick={() => setSteps((cur) => [...cur, { latex: "", confidence: "high" }])}
              >
                Add a line
              </Button>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={confirmAndScore} disabled={busy}>
              {busy ? <Loader2 className="animate-spin" size={16} /> : <Check size={16} />} This matches my working
            </Button>
            <Button variant="ghost" onClick={restart} disabled={busy}>
              Start over
            </Button>
          </div>
          {busy && <p className="text-sm text-text-muted">{busyMsg}</p>}
        </Card>
      )}

      {stage === "result" && view && submissionId && (
        <div className="flex flex-col gap-6">
          <ResultCard view={view} />
          <ChatCard submissionId={submissionId} />
          <EmailCard submissionId={submissionId} />
          <PracticeCard
            submissionId={submissionId}
            practice={view.practice}
            onPractice={(p) => setView({ ...view, practice: p })}
          />
          <div>
            <Button variant="secondary" onClick={restart}>
              <ArrowRight size={16} /> Check another question
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function ResultCard({ view }: { view: StudentView }) {
  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-wide text-text-muted">{view.question_id}</p>
          <p className="mt-1 text-sm font-medium">{view.student_pseudonym}</p>
          <p className="mt-1 text-sm text-text-muted">{view.channel === "test" ? "Reviewed and released by your instructor." : "Marked automatically — no instructor review needed for tutorials."}</p>
          <Mixed text={view.question_prompt} className="mt-2 text-sm" />
        </div>
        <div className="flex items-center gap-2">
          {view.final_answer_verified && (
            <Badge tone={view.final_answer_correct ? "success" : "danger"}>
              {view.final_answer_correct ? "Final answer correct" : "Final answer differs"}
            </Badge>
          )}
          <div className="rounded-xl border border-border bg-surface px-4 py-2 text-right">
            <p className="font-mono text-xl font-semibold tabular-nums">
              {view.total_proposed} <span className="text-sm font-normal text-text-muted">/ {view.total_max}</span>
            </p>
            <p className="text-[10px] uppercase tracking-wider text-text-muted">your score</p>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {view.criteria.map((c) => (
          <div key={c.criterion_id} className="rounded-lg border border-border p-2.5 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs text-text-muted">{c.criterion_id}</span>
              <span className="font-mono tabular-nums">
                {c.proposed} / {c.max}
              </span>
            </div>
            {c.justification && <p className="mt-1 text-xs leading-relaxed">{c.justification}</p>}
          </div>
        ))}
      </div>

      {view.feedback && (
        <div className="mt-4 flex flex-col gap-3 border-t border-border pt-4 text-sm">
          <FeedbackLine label="What went well" text={view.feedback.what_went_well} />
          <FeedbackLine label="What went wrong" text={view.feedback.what_went_wrong} />
          <FeedbackLine label="How to improve" text={view.feedback.how_to_improve} />
          {!!view.feedback.references?.length && (
            <p className="text-xs text-text-muted">Revisit: {view.feedback.references.join(", ")}</p>
          )}
        </div>
      )}
    </Card>
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

function ChatCard({ submissionId }: { submissionId: string }) {
  const toast = useToast();
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    const next: ChatMsg[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const res = await api.chat(submissionId, next);
      setMessages([...next, { role: "assistant", content: res.answer }]);
    } catch (err) {
      setMessages(messages);
      setInput(text);
      toast.error(problem(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Ask about your feedback</p>
      <p className="mb-3 text-xs text-text-muted">
        The tutor answers from your marked work only. It can't change your score — use the email option for that.
      </p>
      {messages.length > 0 && (
        <div className="mb-3 flex flex-col gap-2">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                m.role === "user" ? "self-end bg-accent-soft text-accent-hover" : "self-start bg-surface-2"
              }`}
            >
              {m.content}
            </div>
          ))}
          {busy && (
            <div className="self-start rounded-lg bg-surface-2 px-3 py-2 text-sm text-text-muted">
              <Loader2 className="inline animate-spin" size={13} /> thinking…
            </div>
          )}
        </div>
      )}
      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="e.g. Why did I lose a mark on step 2?"
        />
        <Button onClick={send} disabled={busy || !input.trim()}>
          <Send size={15} />
        </Button>
      </div>
    </Card>
  );
}

function EmailCard({ submissionId }: { submissionId: string }) {
  const toast = useToast();
  const [concern, setConcern] = useState("");
  const [draft, setDraft] = useState<{ subject: string; body: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function generate() {
    if (!concern.trim() || busy) return;
    setBusy(true);
    try {
      setDraft(await api.draftEmail(submissionId, concern.trim()));
    } catch (err) {
      toast.error(problem(err));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
      toast.success("Draft copied — paste it into your email.");
    } catch {
      toast.error("Could not copy automatically — select the text and copy it.");
    }
  }

  return (
    <Card>
      <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Email my instructor</p>
      <p className="mb-3 text-xs text-text-muted">
        Describe your question and we'll draft an email about this specific question. You send it yourself.
      </p>
      <Textarea
        rows={2}
        value={concern}
        onChange={(e) => setConcern(e.target.value)}
        placeholder="e.g. I think x = 0 should also count as a solution"
      />
      <Button className="mt-2" variant="secondary" onClick={generate} disabled={busy || !concern.trim()}>
        {busy ? <Loader2 className="animate-spin" size={15} /> : <Mail size={15} />} Draft the email
      </Button>

      {draft && (
        <div className="mt-3 rounded-lg border border-border bg-surface-2/60 p-3 text-sm">
          <p className="font-semibold">Subject: {draft.subject}</p>
          <p className="mt-2 whitespace-pre-wrap leading-relaxed">{draft.body}</p>
          <Button className="mt-3 px-2.5 py-1 text-xs" variant="secondary" onClick={copy}>
            <Copy size={13} /> Copy draft
          </Button>
        </div>
      )}
    </Card>
  );
}

function PracticeCard({
  submissionId,
  practice,
  onPractice,
}: {
  submissionId: string;
  practice: any[];
  onPractice: (p: any[]) => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState<Record<number, boolean>>({});

  async function regen(type: "bare" | "scenario") {
    if (busy) return;
    setBusy(true);
    try {
      const updated = await api.regeneratePractice(submissionId, type);
      onPractice((updated.practice as any[]) || []);
      setShown({});
    } catch (err) {
      toast.error(problem(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-xs uppercase tracking-wide text-text-muted">Practice on your weak spots</p>
        <div className="flex gap-2">
          <Button variant="secondary" className="px-2.5 py-1 text-xs" disabled={busy} onClick={() => regen("bare")}>
            {busy ? <RefreshCw className="animate-spin" size={12} /> : <Sparkles size={12} />} Standard
          </Button>
          <Button variant="secondary" className="px-2.5 py-1 text-xs" disabled={busy} onClick={() => regen("scenario")}>
            Word problems
          </Button>
        </div>
      </div>
      {!practice?.length ? (
        <p className="text-sm text-text-muted">No practice questions yet.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {practice.map((p, i) => (
            <div key={i} className="rounded-lg border border-border p-3 text-sm">
              <Badge tone="accent">{humanizeTag(p.misconception_tag)}</Badge>
              <div className="mt-2">
                <Mixed text={p.prompt_latex} />
              </div>
              {shown[i] && (
                <div className="mt-2 rounded-md bg-surface-2 px-2 py-1.5">
                  <Katex latex={p.answer_latex} />
                </div>
              )}
              <button
                className="mt-2 text-[11px] font-medium text-accent-hover underline underline-offset-2"
                onClick={() => setShown((s) => ({ ...s, [i]: !s[i] }))}
              >
                {shown[i] ? "Hide answer" : "Show answer"}
              </button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
