import { useEffect, useRef } from "react";
import { renderKatexInto, renderMixed } from "../lib/katex";

/** Bare LaTeX (no "$" delimiters), e.g. a model-solution step. */
export function Katex({ latex, display = false, className }: { latex: string; display?: boolean; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (ref.current) renderKatexInto(ref.current, latex, display);
  }, [latex, display]);
  return <span ref={ref} className={className} />;
}

/** Prose mixed with `$...$`-delimited LaTeX, e.g. a question prompt. */
export function Mixed({ text, className }: { text: string | null | undefined; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (ref.current) renderMixed(ref.current, text);
  }, [text]);
  return <span ref={ref} className={className} />;
}
