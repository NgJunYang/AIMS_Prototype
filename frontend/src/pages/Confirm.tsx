import { Plus } from "lucide-react";
import { useWorkbench } from "../state/WorkbenchContext";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { StepList } from "../components/StepList";

export default function Confirm({ onMarked }: { onMarked: () => void }) {
  const { state, addStep, updateStepLatex, removeStep, confirmAndMark, loadPagePreview, transcribeStagedFile } =
    useWorkbench();

  if (!state.submissionId) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-10">
        <p className="rounded-lg border border-dashed border-border p-8 text-center text-text-muted">
          Nothing to confirm yet — start from Setup.
        </p>
      </div>
    );
  }

  const hasTranscription = !!state.submission?.transcription;
  const notes = state.submission?.transcription?.notes;

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <p className="mb-1 font-mono text-xs uppercase tracking-wide text-text-muted">Confirm</p>
      <h1 className="mb-1 text-2xl font-semibold">
        {state.currentQuestion?.id} — {state.submission?.student_pseudonym || "Student"}
      </h1>
      <p className="mb-8 max-w-2xl text-sm text-text-muted">
        This is the record of what the student wrote. Everything downstream — the symbolic verification, the marks,
        the feedback — is generated from what you confirm here, not from the raw machine transcription. Fix
        anything that's wrong before proceeding.
      </p>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <p className="mb-3 font-mono text-xs uppercase tracking-wide text-text-muted">Uploaded working</p>
          <ImagePane
            uploadSourceType={state.uploadSourceType}
            hasTranscription={hasTranscription}
            uploadedImageUrl={state.uploadedImageUrl}
            uploadPreviewB64={state.uploadPreviewB64}
            uploadPreviewBusy={state.uploadPreviewBusy}
            uploadPageCount={state.uploadPageCount}
            uploadSelectedPage={state.uploadSelectedPage}
            sourcePageCount={state.submission?.source_page_count ?? undefined}
            sourcePage={state.submission?.source_page ?? undefined}
            onPrev={() => loadPagePreview(state.uploadSelectedPage - 1)}
            onNext={() => loadPagePreview(state.uploadSelectedPage + 1)}
            onCommit={() => transcribeStagedFile(state.uploadSelectedPage)}
          />
          {notes && <p className="mt-3 rounded-lg bg-surface-2 p-3 text-sm text-text-muted">{notes}</p>}
        </Card>

        <Card>
          <div className="mb-3 flex items-center justify-between">
            <p className="font-mono text-xs uppercase tracking-wide text-text-muted">Confirm the transcription</p>
            <Button variant="secondary" className="px-2 py-1 text-xs" onClick={addStep}>
              <Plus size={12} /> Add step
            </Button>
          </div>

          <StepList steps={state.localSteps} onChange={updateStepLatex} onRemove={removeStep} />

          {state.confirmError && (
            <div className="mt-4 rounded-lg bg-danger-soft p-3 text-sm text-danger">{state.confirmError}</div>
          )}

          {state.confirmBusy && <p className="mt-4 text-sm text-text-muted">{state.confirmBusyMessage}</p>}

          <Button onClick={() => confirmAndMark(onMarked)} disabled={state.confirmBusy} className="mt-6 w-full py-3">
            Confirm &amp; Mark
          </Button>
        </Card>
      </div>
    </div>
  );
}

function ImagePane({
  uploadSourceType,
  hasTranscription,
  uploadedImageUrl,
  uploadPreviewB64,
  uploadPreviewBusy,
  uploadPageCount,
  uploadSelectedPage,
  sourcePageCount,
  sourcePage,
  onPrev,
  onNext,
  onCommit,
}: {
  uploadSourceType: "image" | "pdf" | null;
  hasTranscription: boolean;
  uploadedImageUrl: string | null;
  uploadPreviewB64: string | null;
  uploadPreviewBusy: boolean;
  uploadPageCount: number;
  uploadSelectedPage: number;
  sourcePageCount?: number;
  sourcePage?: number;
  onPrev: () => void;
  onNext: () => void;
  onCommit: () => void;
}) {
  // Pending PDF, not yet committed to a transcription: page picker.
  if (uploadSourceType === "pdf" && !hasTranscription) {
    if (!uploadPreviewB64) {
      return (
        <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-text-muted">
          Loading page preview…
        </div>
      );
    }
    return (
      <div>
        <img src={`data:image/png;base64,${uploadPreviewB64}`} alt="PDF page preview" className="w-full rounded-lg border border-border" />
        {uploadPageCount > 1 && (
          <div className="mt-2 flex items-center justify-between gap-2">
            <Button variant="secondary" className="px-3 py-1 text-xs" disabled={uploadPreviewBusy || uploadSelectedPage <= 1} onClick={onPrev}>
              ◀ Prev
            </Button>
            <span className="text-xs text-text-muted">
              Page {uploadSelectedPage} of {uploadPageCount}
            </span>
            <Button
              variant="secondary"
              className="px-3 py-1 text-xs"
              disabled={uploadPreviewBusy || uploadSelectedPage >= uploadPageCount}
              onClick={onNext}
            >
              Next ▶
            </Button>
          </div>
        )}
        <Button className="mt-2 w-full" disabled={uploadPreviewBusy} onClick={onCommit}>
          Transcribe this page
        </Button>
      </div>
    );
  }

  if (uploadedImageUrl || (uploadSourceType === "pdf" && hasTranscription)) {
    return (
      <div>
        <img
          src={uploadedImageUrl || `data:image/png;base64,${uploadPreviewB64 || ""}`}
          alt="Uploaded student working"
          className="w-full rounded-lg border border-border"
        />
        {uploadSourceType === "pdf" && sourcePageCount && sourcePageCount > 1 && (
          <p className="mt-1 text-xs text-text-muted">
            Page {sourcePage} of {sourcePageCount}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-text-muted">
      No image was uploaded — these steps were entered manually.
    </div>
  );
}
