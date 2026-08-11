export default function Setup({
  onSubmissionCreated,
}: {
  questionId: string | null;
  onQuestionSelected: (id: string) => void;
  onSubmissionCreated: (submissionId: string) => void;
}) {
  return (
    <div className="mx-auto max-w-6xl p-6">
      <h2 className="text-xl font-semibold">Setup (placeholder)</h2>
      <button
        className="mt-4 rounded bg-accent px-3 py-1.5 text-sm text-white"
        onClick={() => onSubmissionCreated("placeholder")}
      >
        Continue to Confirm (placeholder)
      </button>
    </div>
  );
}
