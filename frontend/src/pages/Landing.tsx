export default function Landing({ onStart }: { onStart: () => void }) {
  return (
    <div className="p-10">
      <h1 className="text-3xl font-semibold">AIMS</h1>
      <button onClick={onStart} className="mt-4 rounded bg-accent px-4 py-2 text-white">
        Start
      </button>
    </div>
  );
}
