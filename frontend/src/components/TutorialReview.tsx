import { useEffect, useState } from "react";
import { Check, RefreshCw, Send } from "lucide-react";
import { useWorkbench } from "../state/WorkbenchContext";
import { api } from "../lib/api";
import type { AssignmentReviewStatus, Submission } from "../types";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { StudentResultLink } from "./StudentResultLink";

export function TutorialReview({ disabled }: { disabled: boolean }) {
  const wb = useWorkbench();
  const { state } = wb;
  const sub = state.submission!;
  const [loaded, setLoaded] = useState<{ submission: Submission; status: AssignmentReviewStatus } | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    setLoaded(null);
    api.assignmentReviewStatus(sub.id).then((status) => {
      if (active) setLoaded({ submission: sub, status });
    }).catch((err: unknown) => {
      if (active) setError(err instanceof Error ? err.message : "Could not load tutorial progress.");
    });
    return () => { active = false; };
  }, [sub, refresh]);

  useEffect(() => {
    const reload = () => setRefresh((value) => value + 1);
    window.addEventListener("focus", reload);
    return () => window.removeEventListener("focus", reload);
  }, []);

  // Never enable publication using progress loaded for an earlier assessment.
  const status = loaded?.submission === sub ? loaded.status : null;
  const pending = state.feedbackDraft !== null ||
    state.localName.trim() !== sub.student_pseudonym ||
    state.localStudentId.trim() !== (sub.student_id || "");
  const reviewed = !!sub.reviewed && !pending && !disabled;
  const invalidated = !!sub.review_invalidated || (!!sub.reviewed && (pending || disabled));
  const busy = state.reviewBusy || state.confirmBusy || state.autoRefreshing;
  const remaining = status ? status.total_questions - status.reviewed_count : 0;

  async function act(action: "review" | "publish" | "unpublish") {
    setError("");
    try {
      if (action === "review") await wb.saveReview("review");
      else await wb.publishTutorial(action === "publish");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save tutorial review.");
    } finally {
      setRefresh((value) => value + 1);
    }
  }

  async function openQuestion(id: string) {
    setError("");
    try { await wb.resumeSubmission(id); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not open question."); }
  }

  return (
    <section className="mt-5 rounded-lg border border-border bg-surface-2/50 p-3" aria-label="Instructor Review">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{sub.question_id} — Instructor Review</h3>
        <Badge tone={reviewed ? "success" : "warning"}>{reviewed ? "✓ Reviewed" : "Review required"}</Badge>
      </div>
      <p className="mb-3 text-xs text-text-muted">
        {invalidated ? "The assessment changed after the previous review." : sub.marks && sub.feedback ? "AI marking complete" : "Mark this question and generate feedback before reviewing."}
      </p>
      <Button className="w-full" variant={reviewed ? "secondary" : "primary"}
        disabled={busy || disabled || reviewed || !sub.marks || !sub.feedback}
        onClick={() => act("review")}>
        <Check size={14} /> {reviewed ? "Reviewed" : invalidated ? "Review Question Again" : "Mark Question as Reviewed"}
      </Button>
      <p className="mt-2 text-[11px] text-text-muted">Review saves your feedback and confirmed identity. Results stay private until you publish the whole tutorial.</p>

      {error && <p role="alert" className="mt-3 text-xs text-danger">{error}</p>}
      <div className="mt-4 border-t border-border pt-3" aria-live="polite">
        {!status ? <p className="text-xs text-text-muted">Loading tutorial progress…</p> : <>
          <h4 className="text-sm font-semibold">{status.assignment_title}</h4>
          <p className="mt-1 text-xs text-text-muted">{status.student_pseudonym}{status.student_id ? ` · ${status.student_id}` : ""}</p>
          <p className="my-3 text-sm font-medium">{status.reviewed_count} / {status.total_questions} questions reviewed</p>
          <ul className="space-y-2">
            {status.questions.map((question) => {
              const changedHere = question.submission_id === sub.id && (pending || disabled);
              const label = !question.submission_id && question.problems.some((p) => p.includes("multiple")) ? "Duplicate submissions" :
                !question.marked ? "Not marked" : !question.has_feedback ? "Missing feedback" :
                  question.reviewed && !changedHere ? "Reviewed" : "Review required";
              return <li key={question.question_id} className="flex items-center justify-between gap-2 text-xs">
                <button className="font-mono text-accent-hover underline underline-offset-2 disabled:text-text-muted disabled:no-underline"
                  disabled={busy || !question.submission_id || question.submission_id === sub.id}
                  onClick={() => question.submission_id && openQuestion(question.submission_id)}>
                  {label === "Reviewed" ? "✓" : "○"} {question.question_id}
                </button>
                <span className={label === "Reviewed" ? "text-success" : "text-text-muted"}>{label}</span>
              </li>;
            })}
          </ul>
          {status.published ? <div className="mt-4">
            <Badge tone="success">✓ Published</Badge>
            <p className="mt-2 text-xs text-text-muted">All reviewed marks and feedback for {status.assignment_title} are now available to the student.</p>
            <Button variant="secondary" className="mt-3 w-full" disabled={busy} onClick={() => act("unpublish")}>Unpublish Tutorial Results</Button>
            <StudentResultLink id={sub.id} />
          </div> : <>
            <p className="mt-4 text-xs text-text-muted">
              {pending || disabled ? "Save and review pending assessment changes before publishing." :
                status.ready_to_publish ? "Ready to publish" :
                  `${remaining} question${remaining === 1 ? "" : "s"} still require instructor review before results can be published.`}
            </p>
            <Button className="mt-3 w-full" disabled={busy || disabled || pending || !status.ready_to_publish} onClick={() => act("publish")}>
              <Send size={14} /> Publish Tutorial Results
            </Button>
          </>}
        </>}
        <Button variant="secondary" className="mt-3 w-full" disabled={busy} onClick={() => { setError(""); setRefresh((value) => value + 1); }}>
          <RefreshCw size={13} /> Refresh tutorial progress
        </Button>
      </div>
    </section>
  );
}
