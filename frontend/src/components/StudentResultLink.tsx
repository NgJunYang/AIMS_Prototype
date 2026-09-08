import { useState } from "react";
import { Button } from "./ui/Button";

export function StudentResultLink({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const url = new URL(window.location.href);
  url.search = "";
  url.hash = "";
  url.searchParams.set("result", id);
  async function copy() {
    try { await navigator.clipboard.writeText(url.href); setCopied(true); setError(""); }
    catch { setError("Copy the link manually using Open student result, or share the result code below."); }
  }
  return (
    <div className="mt-3 flex flex-col gap-2 text-xs">
      <a className="font-medium text-accent underline underline-offset-4" href={url.href} target="_blank" rel="noopener noreferrer">Open student result</a>
      <Button variant="secondary" className="w-full" onClick={copy}>{copied ? "Link copied" : "Copy result link"}</Button>
      <p className="break-all text-text-muted">Result code: {id}</p>
      <p className="text-text-muted">Prototype access: share only with the intended student. This app does not have student sign-in yet.</p>
      {error && <p role="alert" className="text-danger">{error}</p>}
    </div>
  );
}
