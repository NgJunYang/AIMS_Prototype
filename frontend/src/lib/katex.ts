import katex from "katex";

/** Render bare LaTeX (no "$" delimiters) into `el`. */
export function renderKatexInto(el: HTMLElement, latex: string, displayMode: boolean) {
  try {
    katex.render(latex, el, { throwOnError: false, displayMode: !!displayMode });
  } catch {
    el.textContent = latex;
  }
}

/**
 * Render a string that mixes prose with `$...$`-delimited LaTeX into `el`.
 * Splitting on "$" gives alternating [text, math, text, math, ...] segments
 * (even index = text, odd index = math) — works for zero, one, or many "$"
 * pairs, and for strings with no LaTeX at all. Ported from static/app.js.
 */
export function renderMixed(el: HTMLElement, str: string | null | undefined) {
  el.innerHTML = "";
  if (!str) return;
  const parts = String(str).split("$");
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      const span = document.createElement("span");
      renderKatexInto(span, part, false);
      el.appendChild(span);
    } else if (part) {
      el.appendChild(document.createTextNode(part));
    }
  });
}

/**
 * Complex/symbolic roots arrive Python-flavoured, e.g. "-1 + 2*I". Small
 * display-only cleanup: turn "*I" into "i", then drop remaining "*" so
 * numeric coefficients read naturally.
 */
export function formatRoot(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/\*I\b/g, "i") // "2*I" -> "2i"
    .replace(/\bI\b/g, "i") // a lone "I" (coefficient 1) -> "i"
    .replace(/\*/g, ""); // drop any remaining "*" in numeric coefficients
}

export function formatRootList(list: unknown[] | null | undefined): string {
  return (list || []).map(formatRoot).join(", ");
}

export function humanizeTag(tag: string | null | undefined): string {
  if (!tag) return "";
  return tag
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** Plain-English description of what changed for a divergent step. */
export function divergenceMessage(v: {
  lost_roots?: unknown[];
  gained_roots?: unknown[];
  divergence?: string;
}): string {
  const lost = formatRootList(v.lost_roots);
  const gained = formatRootList(v.gained_roots);
  switch (v.divergence) {
    case "lost_roots":
      return `Solution set changed — lost ${lost || "a solution"}`;
    case "gained_roots":
      return `Solution set changed — gained ${gained || "an extra solution"}`;
    case "different_roots":
      return `Solution set changed — was ${lost || "?"}, now ${gained || "?"}`;
    case "unparseable":
      return "This line could not be interpreted as mathematics";
    default:
      return "Solution set changed";
  }
}
