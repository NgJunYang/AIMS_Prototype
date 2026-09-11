import { useState } from "react";
import { ingestionApi } from "../lib/ingestionApi";

export function ImportSourcePages({ id, pages, solution = false }: { id: string; pages: number[]; solution?: boolean }) {
  const [selected, setSelected] = useState(pages[0] || 1);
  const page = pages.includes(selected) ? selected : pages[0];
  if (!page) return <p className="text-xs text-text-muted">No source page identified.</p>;
  return <div className="my-3">
    <label className="text-xs text-text-muted">Source page{" "}
      <select aria-label="Source page" className="rounded border border-border bg-surface p-1" value={page} onChange={(e) => setSelected(Number(e.target.value))}>
        {pages.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
    </label>
    <a href={ingestionApi.page(id, page, solution)} target="_blank" rel="noreferrer" className="ml-3 text-xs text-accent-hover underline">Open full page</a>
    <img src={ingestionApi.page(id, page, solution)} alt={`Original document page ${page}`} className="mt-2 max-h-[36rem] w-full rounded-lg border border-border bg-white object-contain" />
  </div>;
}
