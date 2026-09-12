import { useEffect, useId, useState } from "react";
import { RefreshCw, Save, SlidersHorizontal } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { FeedbackSettings } from "../types";
import { Button } from "./ui/Button";
import { Label, Textarea } from "./ui/Field";

const defaults: FeedbackSettings = { variation: "balanced", custom_instructions: "", reveal_full_solution: true };
const variations = ["focused", "balanced", "exploratory"] as const;

export function AssignmentFeedbackSettings({ assignmentId, settings = defaults }: {
  assignmentId: string; settings?: FeedbackSettings;
}) {
  const id = useId();
  const [draft, setDraft] = useState(settings);
  const [saved, setSaved] = useState(settings);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { setDraft(settings); setSaved(settings); setMessage(""); },
    [assignmentId, settings.variation, settings.custom_instructions, settings.reveal_full_solution]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  function change(patch: Partial<FeedbackSettings>) {
    setDraft((value) => ({ ...value, ...patch })); setMessage("");
  }
  async function save() {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await api.updateFeedbackSettings(assignmentId, draft);
      setSaved(result.feedback_settings); setDraft(result.feedback_settings);
      setMessage("Feedback settings saved. Existing feedback stays unchanged.");
    } catch (e) {
      setError(e instanceof ApiError ? String(e.body?.detail || e.message) : "Could not save feedback settings.");
    } finally { setBusy(false); }
  }
  return <details className="mt-5 rounded-lg border border-border bg-surface-2/30 p-3">
    <summary className="cursor-pointer text-sm font-medium">
      <span className="ml-1 inline-flex items-center gap-2"><SlidersHorizontal size={14} /> Feedback settings</span>
    </summary>
    <fieldset disabled={busy} className="mt-4 min-w-0 space-y-4">
      <fieldset>
        <legend className="mb-2 text-xs font-medium">Feedback variation</legend>
        <div className="flex flex-wrap gap-2">
          {variations.map((variation) => <label key={variation} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-xs ${draft.variation === variation ? "border-accent/50 bg-accent-soft text-accent-hover" : "border-border bg-surface text-text-muted"}`}>
            <input type="radio" name={`${id}-variation`} value={variation} checked={draft.variation === variation}
              onChange={() => change({ variation })} className="accent-accent" />
            <span className="capitalize">{variation}</span>
          </label>)}
        </div>
        <p className="mt-2 text-xs text-text-muted">Controls how concise or exploratory AI feedback should be.</p>
      </fieldset>
      <div>
        <Label htmlFor={`${id}-instructions`}>Custom instructions</Label>
        <Textarea id={`${id}-instructions`} rows={3} maxLength={2000} value={draft.custom_instructions}
          placeholder="Use simple language and focus on the misconception."
          onChange={(e) => change({ custom_instructions: e.target.value })} />
        <p className="mt-1 text-right font-mono text-[11px] text-text-muted">{draft.custom_instructions.length} / 2000</p>
      </div>
      <div>
        <label className="flex items-start gap-2 text-xs leading-relaxed">
          <input type="checkbox" className="mt-0.5 accent-accent" checked={draft.reveal_full_solution}
            onChange={(e) => change({ reveal_full_solution: e.target.checked })} />
          Allow feedback to reveal the complete worked solution
        </label>
        {!draft.reveal_full_solution && <p className="mt-2 text-xs text-text-muted">Students receive targeted explanations and hints without the full solution.</p>}
      </div>
      <p className="text-xs text-text-muted">Applies when feedback is next generated. Saving settings does not regenerate existing feedback.</p>
      <Button variant="secondary" className="px-3 py-1.5 text-xs" disabled={busy || !dirty} onClick={save}>
        {busy ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />} Save Feedback Settings
      </Button>
    </fieldset>
    {message && <p role="status" className="mt-3 text-xs text-success">{message}</p>}
    {error && <p role="alert" className="mt-3 text-xs text-danger">{error}</p>}
  </details>;
}
