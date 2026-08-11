export default function Confirm({ onMarked }: { submissionId: string; onMarked: () => void }) {
  return (
    <div className="mx-auto max-w-6xl p-6">
      <h2 className="text-xl font-semibold">Confirm (placeholder)</h2>
      <button className="mt-4 rounded bg-accent px-3 py-1.5 text-sm text-white" onClick={onMarked}>
        Confirm &amp; Mark (placeholder)
      </button>
    </div>
  );
}
