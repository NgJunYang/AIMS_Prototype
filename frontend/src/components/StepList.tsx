import { X } from "lucide-react";
import { Katex } from "./Math";

export interface EditableStep {
  latex: string;
  confidence?: "high" | "low";
}

export function StepList({
  steps,
  onChange,
  onRemove,
  placeholder,
  lowConfidenceSet,
}: {
  steps: EditableStep[];
  onChange: (index: number, latex: string) => void;
  onRemove: (index: number) => void;
  placeholder?: (index: number) => string;
  /** Question-editor case: flag by matching latex text, not index (see katex.ts port note). */
  lowConfidenceSet?: Set<string>;
}) {
  return (
    <div className="flex flex-col gap-3">
      {steps.map((step, idx) => {
        const isLow = lowConfidenceSet ? lowConfidenceSet.has(step.latex) : step.confidence === "low";
        return (
          <div
            key={idx}
            className={`flex items-start gap-2 rounded-lg p-2 ${
              isLow ? "border border-warning/40 bg-warning-soft" : ""
            }`}
          >
            <div className="min-w-0 flex-1">
              <div className="rounded-md bg-surface-2 px-3 py-2 text-sm">
                <Katex latex={step.latex || "\\text{(empty)}"} display />
              </div>
              <input
                type="text"
                className="mt-1.5 w-full rounded-md border border-border bg-transparent px-2 py-1 font-mono text-xs text-text outline-none focus:border-accent"
                value={step.latex}
                placeholder={placeholder ? placeholder(idx) : `Line ${idx + 1}, e.g. x^2 - 7x + 12 = 0`}
                onChange={(e) => onChange(idx, e.target.value)}
              />
              {isLow && (
                <div className="mt-1 text-xs font-medium text-warning">
                  ⚠ Low-confidence transcription — check this line against the photo
                </div>
              )}
            </div>
            <button
              type="button"
              title="Remove line"
              onClick={() => onRemove(idx)}
              className="mt-1 shrink-0 rounded p-1 text-text-muted hover:bg-danger-soft hover:text-danger"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
