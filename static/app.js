"use strict";

/* =====================================================================
   AIMS frontend — plain vanilla JS, no build step.

   Sections below:
     1. State
     2. API client
     3. Generic render helpers (mixed LaTeX, root formatting, verdicts)
     4. Nav / screen switching
     5. Screen 1 — Setup
     6. Screen 2 — Confirm
     7. Screen 3 — Review
     8. Screen 4 — Class
     9. Init
   ===================================================================== */

// ---------------------------------------------------------------------
// 1. State
// ---------------------------------------------------------------------

const state = {
  questions: [], // Question[]
  currentQuestion: null, // Question | null
  submissionId: null, // string | null
  submission: null, // Submission | null
  uploadedImageUrl: null, // string | null (object URL)
  localSteps: [], // [{index, latex, confidence}] — the editable draft on screen 2
  classChart: null, // Chart | null

  // PDF page picker — a staged file lets Prev/Next and the eventual commit
  // resubmit it without re-asking the lecturer for a file.
  pendingUploadFile: null, // File | null
  uploadSourceType: null, // "image" | "pdf" | null
  uploadPageCount: 1,
  uploadSelectedPage: 1,
  uploadPreviewB64: null, // base64 PNG from /api/uploads/preview (PDF only)
  uploadPreviewBusy: false,

  // Successive submissions need distinct names or the cohort table is one
  // repeated row. Blank input falls back to "Student 1", "Student 2", ...
  submissionsThisSession: 0,

  practiceType: "bare", // "bare" | "scenario"
  practiceBusy: false,
};

/** The typed student name, or an auto-incrementing fallback if left blank. */
function nextStudentPseudonym() {
  const typed = (document.getElementById("student-name").value || "").trim();
  state.submissionsThisSession += 1;
  return typed || `Student ${state.submissionsThisSession}`;
}

// ---------------------------------------------------------------------
// 2. API client
// ---------------------------------------------------------------------

async function apiFetch(path, options) {
  const res = await fetch(path, options);
  let body = null;
  try {
    body = await res.json();
  } catch (_) {
    // no/invalid JSON body — leave body null
  }
  if (!res.ok) {
    const message =
      (body && (body.detail || body.error)) || `Request failed (${res.status})`;
    const err = new Error(message);
    err.status = res.status;
    err.body = body || {};
    throw err;
  }
  return body;
}

const api = {
  listQuestions: () => apiFetch("/api/questions"),
  getQuestion: (id) => apiFetch(`/api/questions/${encodeURIComponent(id)}`),
  createSubmission: (questionId, studentPseudonym) =>
    apiFetch("/api/submissions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question_id: questionId,
        student_pseudonym: studentPseudonym,
      }),
    }),
  transcribe: (submissionId, file, page = 1) => {
    const form = new FormData();
    form.append("file", file);
    form.append("page", String(page));
    return apiFetch(`/api/submissions/${submissionId}/transcribe`, {
      method: "POST",
      body: form,
    });
  },
  inspectUpload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return apiFetch("/api/uploads/inspect", { method: "POST", body: form });
  },
  previewUpload: (file, page) => {
    const form = new FormData();
    form.append("file", file);
    form.append("page", String(page));
    return apiFetch("/api/uploads/preview", { method: "POST", body: form });
  },
  updateSteps: (submissionId, steps) =>
    apiFetch(`/api/submissions/${submissionId}/steps`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps }),
    }),
  mark: (submissionId) =>
    apiFetch(`/api/submissions/${submissionId}/mark`, { method: "POST" }),
  regeneratePractice: (submissionId, questionType) =>
    apiFetch(`/api/submissions/${submissionId}/practice`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_type: questionType }),
    }),
  override: (submissionId, criterionId, proposed) =>
    apiFetch(`/api/submissions/${submissionId}/override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ criterion_id: criterionId, proposed }),
    }),
  classSummary: () => apiFetch("/api/class/summary"),
};

// ---------------------------------------------------------------------
// 3. Generic render helpers
// ---------------------------------------------------------------------

/**
 * Render a string that mixes prose with `$...$`-delimited LaTeX into `el`.
 * Splitting on "$" gives alternating [text, math, text, math, ...] segments
 * (even index = text, odd index = math) — that is the one property this
 * relies on, so it works for zero, one, or many "$" pairs, and for strings
 * that contain no LaTeX at all.
 */
function renderMixed(el, str) {
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

/** Render bare LaTeX (no "$" delimiters) into `el`. */
function renderKatexInto(el, latex, displayMode) {
  try {
    window.katex.render(latex, el, { throwOnError: false, displayMode: !!displayMode });
  } catch (_) {
    el.textContent = latex;
  }
}

/**
 * Complex/symbolic roots arrive Python-flavoured, e.g. "-1 + 2*I". This is a
 * small display-only cleanup, not a general LaTeX converter: turn "*I" into
 * "i", then drop any remaining "*" so numeric coefficients read naturally.
 */
function formatRoot(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/\*I\b/g, "i") // "2*I" -> "2i"
    .replace(/\bI\b/g, "i") // a lone "I" (coefficient 1) -> "i"
    .replace(/\*/g, ""); // drop any remaining "*" in numeric coefficients
}

function formatRootList(list) {
  return (list || []).map(formatRoot).join(", ");
}

function humanizeTag(tag) {
  if (!tag) return "";
  return tag
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** Plain-English description of what changed for a divergent step. */
function divergenceMessage(v) {
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

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function clearChildren(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

// ---------------------------------------------------------------------
// 4. Nav / screen switching
// ---------------------------------------------------------------------

const SCREENS = ["setup", "confirm", "review", "class"];

function showScreen(name) {
  SCREENS.forEach((s) => {
    document.getElementById(`screen-${s}`).classList.toggle("is-active", s === name);
  });
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.screen === name);
  });

  if (name === "confirm") renderConfirmScreen();
  if (name === "review") renderReviewScreen();
  if (name === "class") loadAndRenderClassScreen();
}

function initNav() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => showScreen(btn.dataset.screen));
  });
}

// ---------------------------------------------------------------------
// 5. Screen 1 — Setup
// ---------------------------------------------------------------------

function initSetupScreen() {
  const select = document.getElementById("question-select");
  select.addEventListener("change", () => selectQuestion(select.value));

  document.getElementById("file-input").addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) beginWithUpload(file);
    e.target.value = ""; // allow re-selecting the same file later
  });

  document.getElementById("type-in-btn").addEventListener("click", () => {
    beginManualEntry([]);
  });

  document.getElementById("sample-script-btn").addEventListener("click", async () => {
    const q2 = state.questions.find((q) => q.id === "q2");
    if (!q2) return;
    const notice = document.getElementById("setup-notice");
    if (state.currentQuestion?.id !== "q2") {
      document.getElementById("question-select").value = "q2";
      selectQuestion("q2");
      notice.textContent = "Switched to Q2 for the flagship sample script.";
      notice.classList.remove("hidden");
    } else {
      notice.classList.add("hidden");
    }
    await beginManualEntry([
      { latex: "x^2 = 5x", confidence: "high" },
      { latex: "x = 5", confidence: "high" },
    ]);
  });
}

async function loadQuestions() {
  state.questions = await api.listQuestions();
  const select = document.getElementById("question-select");
  state.questions.forEach((q) => {
    const opt = document.createElement("option");
    opt.value = q.id;
    opt.textContent = `${q.id} — ${stripLatexForOption(q.prompt)}`;
    select.appendChild(opt);
  });

  // Open on a real question rather than an empty screen: the setup screen is
  // the first thing anyone sees, and with nothing selected it shows only a
  // dropdown, which reads as a page that failed to load.
  if (state.questions.length) {
    select.value = state.questions[0].id;
    selectQuestion(state.questions[0].id);
  }
}

/** A plain-text preview for the <option> label (options can't render KaTeX). */
function stripLatexForOption(prompt) {
  return String(prompt).replace(/\$/g, "");
}

function selectQuestion(id) {
  const question = state.questions.find((q) => q.id === id) || null;
  state.currentQuestion = question;

  const detail = document.getElementById("question-detail");
  const entry = document.getElementById("entry-points");

  if (!question) {
    detail.classList.add("hidden");
    entry.classList.add("hidden");
    return;
  }

  renderMixed(document.getElementById("question-prompt"), question.prompt);

  const list = document.getElementById("model-solution-list");
  clearChildren(list);
  question.model_solution_steps.forEach((step) => {
    const li = document.createElement("li");
    renderKatexInto(li, step, false);
    list.appendChild(li);
  });

  const rubricBody = document.getElementById("rubric-table-body");
  clearChildren(rubricBody);
  question.criteria.forEach((c) => {
    const tr = document.createElement("tr");
    tr.className = "border-b border-slate-100 last:border-0";
    tr.innerHTML = `
      <td class="py-2 pr-2 font-mono text-xs text-slate-500 align-top">${c.id}</td>
      <td class="py-2 pr-2 align-top">${escapeHtml(c.description)}</td>
      <td class="py-2 pl-2 text-right align-top tabular-nums">${c.max}</td>
    `;
    rubricBody.appendChild(tr);
  });

  detail.classList.remove("hidden");
  entry.classList.remove("hidden");
  document.getElementById("setup-notice").classList.add("hidden");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

/**
 * A plain image goes straight to transcription, exactly as before — no
 * added latency or clicks. A PDF is staged instead: the lecturer browses
 * pages at zero cost (no LLM call) via /api/uploads/preview before
 * committing one page to the real /transcribe call.
 */
async function beginWithUpload(file) {
  if (!state.currentQuestion) return;

  const looksLikePdf =
    file.type === "application/pdf" || /\.pdf$/i.test(file.name || "");

  const sub = await api.createSubmission(
    state.currentQuestion.id,
    nextStudentPseudonym()
  );
  state.submissionId = sub.id;
  state.submission = sub;
  state.localSteps = [];

  if (!looksLikePdf) {
    state.uploadedImageUrl = URL.createObjectURL(file);
    state.pendingUploadFile = null;
    state.uploadSourceType = "image";
    state.uploadPageCount = 1;
    state.uploadSelectedPage = 1;
    state.uploadPreviewB64 = null;

    showScreen("confirm");
    await transcribeStagedFile(1, file);
    return;
  }

  state.uploadedImageUrl = null;
  state.pendingUploadFile = file;
  state.uploadSourceType = "pdf";
  state.uploadPageCount = 1;
  state.uploadSelectedPage = 1;
  state.uploadPreviewB64 = null;

  showScreen("confirm");
  setConfirmBusy(true, "Reading PDF…");
  try {
    const inspection = await api.inspectUpload(file);
    state.uploadPageCount = inspection.page_count;
    await loadPagePreview(1);
  } catch (err) {
    renderConfirmScreen();
    showConfirmError(err);
  } finally {
    setConfirmBusy(false);
  }
}

/** Render one PDF page as a preview, at zero cost — no submission touched, no LLM call. */
async function loadPagePreview(page) {
  if (!state.pendingUploadFile) return;
  state.uploadPreviewBusy = true;
  renderConfirmScreen();
  try {
    const preview = await api.previewUpload(state.pendingUploadFile, page);
    state.uploadSelectedPage = preview.page;
    state.uploadPageCount = preview.page_count;
    state.uploadPreviewB64 = preview.preview_b64;
  } catch (err) {
    showConfirmError(err);
  } finally {
    state.uploadPreviewBusy = false;
    renderConfirmScreen();
  }
}

/**
 * The real commit: one billed vision-model call. Used by both the plain
 * image fast path (passed `file` directly) and the PDF picker (falls back
 * to the staged `state.pendingUploadFile`).
 */
async function transcribeStagedFile(page, file) {
  const fileToSend = file || state.pendingUploadFile;
  if (!fileToSend || !state.submissionId) return;

  setConfirmBusy(true, "Transcribing the image…");
  try {
    const updated = await api.transcribe(state.submissionId, fileToSend, page);
    state.submission = updated;
    state.localSteps = (
      (updated.transcription && updated.transcription.steps) ||
      []
    ).map((s) => ({ ...s }));
    renderConfirmScreen();
  } catch (err) {
    renderConfirmScreen();
    showConfirmError(err);
  } finally {
    setConfirmBusy(false);
  }
}

async function beginManualEntry(prefill) {
  if (!state.currentQuestion) return;

  const sub = await api.createSubmission(
    state.currentQuestion.id,
    nextStudentPseudonym()
  );
  state.submissionId = sub.id;
  state.submission = sub;
  state.uploadedImageUrl = null;
  state.pendingUploadFile = null;
  state.uploadSourceType = null;
  state.uploadPageCount = 1;
  state.uploadSelectedPage = 1;
  state.uploadPreviewB64 = null;
  state.localSteps = prefill.length
    ? prefill.map((s, i) => ({
        index: i + 1,
        latex: s.latex,
        confidence: s.confidence || "high",
      }))
    : [{ index: 1, latex: "", confidence: "high" }];

  showScreen("confirm");
}

// ---------------------------------------------------------------------
// 6. Screen 2 — Confirm
// ---------------------------------------------------------------------

function initConfirmScreen() {
  document.getElementById("add-step-btn").addEventListener("click", () => {
    state.localSteps.push({
      index: state.localSteps.length + 1,
      latex: "",
      confidence: "high",
    });
    renderConfirmScreen();
  });

  document.getElementById("confirm-mark-btn").addEventListener("click", confirmAndMark);
}

function renderConfirmScreen() {
  const empty = document.getElementById("confirm-empty");
  const body = document.getElementById("confirm-body");

  if (!state.submissionId) {
    empty.classList.remove("hidden");
    body.classList.add("hidden");
    return;
  }
  empty.classList.add("hidden");
  body.classList.remove("hidden");

  const question = state.currentQuestion;
  const context = document.getElementById("confirm-context");
  context.textContent = question
    ? `${question.id} — ${state.submission?.student_pseudonym || "Student A"}`
    : "";

  // --- image / placeholder pane ---
  renderImagePane();

  const notes = document.getElementById("transcription-notes");
  const notesText = state.submission?.transcription?.notes;
  if (notesText) {
    notes.textContent = notesText;
    notes.classList.remove("hidden");
  } else {
    notes.classList.add("hidden");
  }

  // --- editable step list ---
  renderStepList();
}

/**
 * Three cases: a PDF staged but not yet committed to a transcription (a
 * page picker); a committed upload — image or PDF — shown as a plain
 * preview; or manual entry with no upload at all.
 */
function renderImagePane() {
  const imagePane = document.getElementById("image-pane");
  clearChildren(imagePane);

  const hasTranscription = !!state.submission?.transcription;

  if (state.uploadSourceType === "pdf" && !hasTranscription) {
    renderPendingPdfPicker(imagePane);
    return;
  }

  if (state.uploadedImageUrl || (state.uploadSourceType === "pdf" && hasTranscription)) {
    const img = document.createElement("img");
    img.src = state.uploadedImageUrl || `data:image/png;base64,${state.uploadPreviewB64 || ""}`;
    img.alt = "Uploaded student working";
    img.className = "w-full rounded-lg border border-slate-200";
    imagePane.appendChild(img);

    const pageCount = state.submission?.source_page_count;
    if (state.uploadSourceType === "pdf" && pageCount > 1) {
      imagePane.appendChild(
        el(
          "p",
          "text-xs text-slate-500 mt-1",
          `Page ${state.submission.source_page} of ${pageCount}`
        )
      );
    }
    return;
  }

  const placeholder = el(
    "div",
    "text-sm text-slate-500 border border-dashed border-slate-300 rounded-lg p-6 text-center",
    "No image was uploaded — these steps were entered manually."
  );
  imagePane.appendChild(placeholder);
}

/** The page picker for a staged PDF: preview, Prev/Next stepper, and the commit button. */
function renderPendingPdfPicker(container) {
  if (!state.uploadPreviewB64) {
    container.appendChild(
      el(
        "div",
        "text-sm text-slate-500 border border-dashed border-slate-300 rounded-lg p-6 text-center",
        "Loading page preview…"
      )
    );
    return;
  }

  const img = document.createElement("img");
  img.src = `data:image/png;base64,${state.uploadPreviewB64}`;
  img.alt = "PDF page preview";
  img.className = "w-full rounded-lg border border-slate-200";
  container.appendChild(img);

  if (state.uploadPageCount > 1) {
    const stepper = document.createElement("div");
    stepper.className = "flex items-center justify-between gap-2 mt-2";

    const prev = document.createElement("button");
    prev.type = "button";
    prev.className = "btn-secondary text-xs px-3 py-1";
    prev.textContent = "◀ Prev";
    prev.disabled = state.uploadPreviewBusy || state.uploadSelectedPage <= 1;
    prev.addEventListener("click", () => loadPagePreview(state.uploadSelectedPage - 1));
    stepper.appendChild(prev);

    stepper.appendChild(
      el(
        "span",
        "text-xs text-slate-500",
        `Page ${state.uploadSelectedPage} of ${state.uploadPageCount}`
      )
    );

    const next = document.createElement("button");
    next.type = "button";
    next.className = "btn-secondary text-xs px-3 py-1";
    next.textContent = "Next ▶";
    next.disabled = state.uploadPreviewBusy || state.uploadSelectedPage >= state.uploadPageCount;
    next.addEventListener("click", () => loadPagePreview(state.uploadSelectedPage + 1));
    stepper.appendChild(next);

    container.appendChild(stepper);
  }

  const commitBtn = document.createElement("button");
  commitBtn.type = "button";
  commitBtn.className = "btn-primary w-full mt-2";
  commitBtn.textContent = "Transcribe this page";
  commitBtn.disabled = state.uploadPreviewBusy;
  commitBtn.addEventListener("click", () => transcribeStagedFile(state.uploadSelectedPage));
  container.appendChild(commitBtn);
}

function renderStepList() {
  const list = document.getElementById("step-list");
  clearChildren(list);

  state.localSteps.forEach((step, idx) => {
    const row = document.createElement("div");
    row.className = "step-row" + (step.confidence === "low" ? " is-low-confidence" : "");

    const top = document.createElement("div");
    top.className = "flex justify-between items-start gap-2";

    const col = document.createElement("div");
    col.className = "flex-1 min-w-0";

    const preview = document.createElement("div");
    preview.className = "katex-preview";
    renderKatexInto(preview, step.latex || "\\text{(empty)}", true);
    col.appendChild(preview);

    const input = document.createElement("input");
    input.type = "text";
    input.className = "field step-input mt-2 w-full text-sm";
    input.value = step.latex || "";
    input.placeholder = "LaTeX for this line, e.g. x^2 - 5x + 6 = 0";
    input.addEventListener("input", () => {
      state.localSteps[idx].latex = input.value;
      renderKatexInto(preview, input.value || "\\text{(empty)}", true);
    });
    col.appendChild(input);

    if (step.confidence === "low") {
      const flag = el("div", "low-confidence-flag", "⚠ Low-confidence transcription — check this line");
      col.appendChild(flag);
    }

    top.appendChild(col);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "text-slate-400 hover:text-red-600 px-2 shrink-0";
    del.title = "Delete step";
    del.textContent = "✕";
    del.addEventListener("click", () => {
      state.localSteps.splice(idx, 1);
      renderConfirmScreen();
    });
    top.appendChild(del);

    row.appendChild(top);
    list.appendChild(row);
  });
}

function setConfirmBusy(busy, message) {
  const btn = document.getElementById("confirm-mark-btn");
  const progress = document.getElementById("confirm-progress");
  btn.disabled = busy;
  if (busy) {
    progress.textContent = message || "Working…";
    progress.classList.remove("hidden");
  } else {
    progress.classList.add("hidden");
  }
}

function showConfirmError(err) {
  const box = document.getElementById("confirm-error");
  const parts = [];
  if (err.body && err.body.hint) {
    parts.push(`⚠ ${err.body.hint}`);
    if (err.body.detail) parts.push(err.body.detail);
  } else if (err.body && err.body.detail) {
    parts.push(err.body.detail);
  } else {
    parts.push(err.message || "Something went wrong.");
  }
  box.textContent = parts.join(" — ");
  box.classList.remove("hidden");
}

function hideConfirmError() {
  document.getElementById("confirm-error").classList.add("hidden");
}

async function confirmAndMark() {
  if (!state.submissionId) return;
  hideConfirmError();
  setConfirmBusy(true, "Saving confirmed steps…");

  const payload = state.localSteps.map((s, i) => ({
    index: i + 1,
    latex: s.latex,
    confidence: s.confidence || "high",
  }));

  try {
    await api.updateSteps(state.submissionId, payload);

    setConfirmBusy(true, "Marking — this can take several seconds…");
    const marked = await api.mark(state.submissionId);
    state.submission = marked;

    showScreen("review");
  } catch (err) {
    // Stay on this screen; the lecturer's edits are still in state.localSteps.
    showConfirmError(err);
  } finally {
    setConfirmBusy(false);
  }
}

// ---------------------------------------------------------------------
// 7. Screen 3 — Review
// ---------------------------------------------------------------------

function initReviewScreen() {
  document.querySelectorAll("#review-tabs .tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => selectReviewTab(btn.dataset.tab));
  });
}

function selectReviewTab(tab) {
  document.querySelectorAll("#review-tabs .tab-btn").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === tab);
  });
  ["feedback", "misconceptions", "practice"].forEach((t) => {
    document.getElementById(`tab-${t}`).classList.toggle("hidden", t !== tab);
  });
}

function renderReviewScreen() {
  const empty = document.getElementById("review-empty");
  const body = document.getElementById("review-body");
  const sub = state.submission;

  if (!sub || !sub.marks) {
    empty.classList.remove("hidden");
    body.classList.add("hidden");
    return;
  }
  empty.classList.add("hidden");
  body.classList.remove("hidden");

  const question = state.currentQuestion;
  document.getElementById("review-context").textContent = question
    ? `${question.id} — ${sub.student_pseudonym || "Student A"}`
    : sub.student_pseudonym || "";

  renderWarnings(sub.marks.warnings || []);
  renderTotals(sub.marks);
  renderVerifiedSteps(sub.verification, sub.confirmed_steps || []);
  renderMarksList(sub.marks);
  renderFeedbackTab(sub.feedback);
  renderMisconceptionsTab(sub.marks.misconceptions || []);
  renderPracticeTab(sub.practice || []);
}

function renderWarnings(warnings) {
  const box = document.getElementById("review-warnings");
  clearChildren(box);
  if (!warnings.length) {
    box.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");
  warnings.forEach((w) => {
    const line = el("div", "warning-banner", `⚠ ${w}`);
    box.appendChild(line);
  });
}

function renderTotals(marks) {
  document.getElementById(
    "review-total"
  ).textContent = `${marks.total_proposed} / ${marks.total_max}`;
}

function renderVerifiedSteps(verification, confirmedSteps) {
  const list = document.getElementById("verified-steps-list");
  clearChildren(list);

  if (!verification || !verification.steps || !verification.steps.length) {
    list.appendChild(
      el("p", "text-sm text-slate-500", "No symbolic verification available for this submission.")
    );
    return;
  }

  const stepsByIndex = {};
  confirmedSteps.forEach((s) => (stepsByIndex[s.index] = s));

  verification.steps.forEach((v) => {
    const row = document.createElement("div");
    row.className = "verdict-row " + verdictClass(v);
    row.id = `step-row-${v.index}`;

    const head = document.createElement("div");
    head.className = "flex items-center justify-between gap-2 mb-1";
    head.appendChild(el("span", "text-xs font-mono text-slate-400", `Step ${v.index}`));
    head.appendChild(el("span", "verdict-label", verdictLabel(v)));
    row.appendChild(head);

    const latexBox = document.createElement("div");
    latexBox.className = "katex-preview mb-2";
    const source = stepsByIndex[v.index];
    renderKatexInto(latexBox, (source && source.latex) || "", true);
    row.appendChild(latexBox);

    const detail = verdictDetail(v);
    if (detail) row.appendChild(el("p", "text-sm", detail));
    if (v.note) row.appendChild(el("p", "text-xs text-slate-500 mt-1", v.note));

    list.appendChild(row);
  });

  // Final answer status — distinct "not established" vs "incorrect".
  const finalBox = document.createElement("div");
  finalBox.className = "verdict-row " + finalAnswerClass(verification);
  const label = el("span", "verdict-label", "Final answer");
  const head = document.createElement("div");
  head.className = "flex items-center justify-between gap-2 mb-1";
  head.appendChild(el("span", "text-xs font-mono text-slate-400", "Overall"));
  head.appendChild(label);
  finalBox.appendChild(head);
  finalBox.appendChild(el("p", "text-sm", finalAnswerMessage(verification)));
  list.appendChild(finalBox);
}

function verdictClass(v) {
  if (!v.parsed) return "verdict-neutral";
  if (v.equivalent_to_previous === false) return "verdict-bad";
  if (v.equivalent_to_previous === true) return "verdict-good";
  return "verdict-neutral";
}

function verdictLabel(v) {
  if (!v.parsed) return "Not symbolically verified";
  if (v.equivalent_to_previous === false) return "Diverged from previous step";
  if (v.equivalent_to_previous === true) return "Verified";
  return "No verdict — nothing to compare";
}

function verdictDetail(v) {
  if (!v.parsed) return null;
  if (v.equivalent_to_previous === false) return divergenceMessage(v);
  if (v.equivalent_to_previous === true) return "Verified equivalent to the previous step.";
  if (v.solutions && v.solutions.length) {
    return `Solutions so far: ${formatRootList(v.solutions)}`;
  }
  return null;
}

function finalAnswerClass(verification) {
  if (!verification.final_answer_verified) return "verdict-neutral";
  return verification.final_answer_correct ? "verdict-good" : "verdict-bad";
}

function finalAnswerMessage(verification) {
  if (!verification.final_answer_verified) {
    return "Not established — the final line could not be symbolically verified. This does not mean it is wrong; judge it from the written evidence.";
  }
  if (verification.final_answer_correct) {
    return `Correct. Expected: ${formatRootList(verification.model_solutions)}`;
  }
  return `Incorrect. Expected: ${formatRootList(verification.model_solutions)}`;
}

function renderMarksList(marks) {
  const list = document.getElementById("marks-list");
  clearChildren(list);

  marks.criteria.forEach((c) => {
    const card = document.createElement("div");
    card.className = "border border-slate-200 rounded-lg p-3" + (c.overridden ? " bg-indigo-50/40" : "");

    const head = document.createElement("div");
    head.className = "flex items-center justify-between gap-2";
    const title = document.createElement("div");
    title.className = "font-mono text-xs text-slate-500";
    title.textContent = c.criterion_id + (c.overridden ? " · overridden" : "");
    head.appendChild(title);

    const scoreWrap = document.createElement("div");
    scoreWrap.className = "flex items-center gap-1";
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = String(c.max);
    input.value = String(c.proposed);
    input.className = "field w-16 text-right tabular-nums";
    input.addEventListener("change", () => onOverrideChange(c, input));
    scoreWrap.appendChild(input);
    scoreWrap.appendChild(el("span", "text-sm text-slate-400", `/ ${c.max}`));
    head.appendChild(scoreWrap);

    card.appendChild(head);
    card.appendChild(el("p", "text-sm mt-2", c.justification || ""));

    const link = document.createElement("button");
    link.type = "button";
    if (c.evidence_step !== null && c.evidence_step !== undefined) {
      link.className = "see-step-link mt-1";
      link.textContent = `see step ${c.evidence_step}`;
      link.addEventListener("click", () => scrollToStep(c.evidence_step));
    } else {
      link.className = "text-xs text-slate-400 mt-1";
      link.textContent = "no step cited";
      link.disabled = true;
    }
    card.appendChild(link);

    list.appendChild(card);
  });
}

async function onOverrideChange(criterion, input) {
  let value = Number(input.value);
  if (!Number.isFinite(value) || value < 0 || value > criterion.max || !Number.isInteger(value)) {
    // Reject client-side rather than round-tripping to the server for a 400.
    input.value = String(criterion.proposed);
    return;
  }
  try {
    const updated = await api.override(state.submissionId, criterion.criterion_id, value);
    state.submission = updated;
    renderReviewScreen();
  } catch (err) {
    input.value = String(criterion.proposed);
    alert((err.body && (err.body.detail || err.body.error)) || err.message);
  }
}

function scrollToStep(index) {
  const row = document.getElementById(`step-row-${index}`);
  if (!row) return;
  row.scrollIntoView({ behavior: "smooth", block: "center" });
  row.classList.add("is-highlighted");
  setTimeout(() => row.classList.remove("is-highlighted"), 1200);
}

function renderFeedbackTab(feedback) {
  const box = document.getElementById("tab-feedback");
  clearChildren(box);
  if (!feedback) {
    box.appendChild(el("p", "text-sm text-slate-500", "No feedback generated."));
    return;
  }

  const section = (title, text) => {
    const wrap = document.createElement("div");
    wrap.className = "mb-4";
    wrap.appendChild(el("h3", "text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1", title));
    wrap.appendChild(el("p", "text-sm", text || "—"));
    return wrap;
  };

  box.appendChild(section("What went well", feedback.what_went_well));
  box.appendChild(section("What went wrong", feedback.what_went_wrong));
  box.appendChild(section("How to improve", feedback.how_to_improve));

  if (feedback.references && feedback.references.length) {
    const wrap = document.createElement("div");
    wrap.appendChild(el("h3", "text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1", "References"));
    const ul = document.createElement("ul");
    ul.className = "list-disc list-inside text-sm";
    feedback.references.forEach((r) => ul.appendChild(el("li", "", r)));
    wrap.appendChild(ul);
    box.appendChild(wrap);
  }
}

function renderMisconceptionsTab(misconceptions) {
  const box = document.getElementById("tab-misconceptions");
  clearChildren(box);
  if (!misconceptions.length) {
    box.appendChild(el("p", "text-sm text-slate-500", "No misconceptions were identified."));
    return;
  }
  const ul = document.createElement("ul");
  ul.className = "space-y-2";
  misconceptions.forEach((tag) => {
    const li = document.createElement("li");
    li.className = "text-sm border border-slate-200 rounded-lg px-3 py-2";
    li.textContent = humanizeTag(tag);
    ul.appendChild(li);
  });
  box.appendChild(ul);
}

function renderPracticeTab(practice) {
  const box = document.getElementById("tab-practice");
  clearChildren(box);

  box.appendChild(renderPracticeControls());

  if (!practice.length) {
    box.appendChild(el("p", "text-sm text-slate-500", "No practice questions generated."));
    return;
  }

  practice.forEach((p) => {
    const card = document.createElement("div");
    card.className = "border border-slate-200 rounded-lg p-3 mb-3";

    const badges = el("div", "flex flex-wrap gap-1 items-center");
    badges.appendChild(
      el(
        "span",
        "text-xs font-medium text-indigo-700 bg-indigo-50 rounded px-2 py-0.5",
        humanizeTag(p.misconception_tag)
      )
    );
    if (p.question_type === "scenario") {
      badges.appendChild(el("span", "badge-live", "Word problem"));
    }
    card.appendChild(badges);

    const promptEl = document.createElement("div");
    promptEl.className = "mt-2 text-sm";
    renderMixed(promptEl, p.prompt_latex);
    card.appendChild(promptEl);

    const answerEl = document.createElement("div");
    answerEl.className = "mt-2 hidden";
    const answerMath = el("div", "katex-preview");
    renderKatexInto(answerMath, p.answer_latex, false);
    answerEl.appendChild(answerMath);
    // A word problem may legitimately exclude a root. Saying why is the
    // pedagogical point: discarding a root for a stated reason is not the
    // same mistake as losing one without noticing.
    if (p.rejected_note) {
      answerEl.appendChild(
        el("p", "text-xs text-slate-500 mt-1 italic", p.rejected_note)
      );
    }

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "btn-secondary text-xs px-3 py-1 mt-2";
    toggle.textContent = "Show answer";
    toggle.addEventListener("click", () => {
      const showing = !answerEl.classList.contains("hidden");
      answerEl.classList.toggle("hidden", showing);
      toggle.textContent = showing ? "Show answer" : "Hide answer";
    });

    card.appendChild(toggle);
    card.appendChild(answerEl);
    box.appendChild(card);
  });
}

/** Question-type picker: regenerates phrasing without re-marking. */
function renderPracticeControls() {
  const wrap = el("div", "flex flex-wrap gap-2 items-center mb-3");
  wrap.appendChild(el("span", "text-xs text-slate-500", "Question style"));

  [
    { value: "bare", label: "Standard" },
    { value: "scenario", label: "Word problem" },
  ].forEach(({ value, label }) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-secondary text-xs px-3 py-1";
    btn.textContent = label;
    btn.disabled = state.practiceBusy || state.practiceType === value;
    btn.addEventListener("click", () => regeneratePractice(value));
    wrap.appendChild(btn);
  });

  if (state.practiceBusy) {
    wrap.appendChild(el("span", "text-xs text-slate-400", "Regenerating…"));
  }
  return wrap;
}

async function regeneratePractice(questionType) {
  if (!state.submissionId || state.practiceBusy) return;
  state.practiceBusy = true;
  state.practiceType = questionType;
  renderPracticeTab(state.submission?.practice || []);
  try {
    const updated = await api.regeneratePractice(state.submissionId, questionType);
    state.submission = updated;
  } catch (err) {
    alert((err.body && (err.body.detail || err.body.error)) || err.message);
  } finally {
    state.practiceBusy = false;
    renderPracticeTab(state.submission?.practice || []);
  }
}

// ---------------------------------------------------------------------
// 8. Screen 4 — Class
// ---------------------------------------------------------------------

async function loadAndRenderClassScreen() {
  let summary;
  try {
    summary = await api.classSummary();
  } catch (err) {
    document.getElementById("class-recommendation").textContent =
      "Could not load class summary: " + err.message;
    return;
  }
  renderClassSourceNote(summary);
  renderClassStats(summary);
  renderClassChart(summary.misconception_counts || []);
  renderStudentsTable(summary.students || []);
}

/**
 * Say plainly whether these numbers were computed from real marking or are
 * the illustrative fallback. "Computed from 2 real submissions" is worth more
 * than an unlabelled impressive-looking cohort.
 */
function renderClassSourceNote(summary) {
  const box = document.getElementById("class-source-note");
  clearChildren(box);
  if (!summary.source_note) {
    box.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");

  const computed = summary.source === "computed";
  const badge = el(
    "span",
    computed ? "badge-live" : "badge-sample",
    computed ? "Live data" : "Sample data"
  );
  box.appendChild(badge);
  box.appendChild(el("span", "text-slate-500 ml-2", summary.source_note));
}

function renderClassStats(summary) {
  const wrap = document.getElementById("class-stats");
  clearChildren(wrap);
  const stat = (label, value) => {
    const card = document.createElement("div");
    card.className = "stat-card";
    card.appendChild(el("div", "stat-value", String(value)));
    card.appendChild(el("div", "stat-label", label));
    return card;
  };
  wrap.appendChild(stat("Cohort size", summary.cohort_size));
  wrap.appendChild(stat("Marked", summary.marked));
  wrap.appendChild(stat("Mean %", `${summary.mean_percentage}%`));

  document.getElementById("class-recommendation").textContent = summary.recommendation || "";
}

function renderClassChart(counts) {
  const ctx = document.getElementById("misconception-chart").getContext("2d");

  if (state.classChart) {
    state.classChart.destroy();
    state.classChart = null;
  }

  state.classChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: counts.map((c) => c.name),
      datasets: [
        {
          label: "Students affected",
          data: counts.map((c) => c.count),
          backgroundColor: "#A5271B", // --color-red-pen — Chart.js reads this as a literal JS
          // value, not a Tailwind class, so the tailwind.config palette remap can't reach it
          borderRadius: 4,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  });
}

function renderStudentsTable(students) {
  const body = document.getElementById("students-table-body");
  clearChildren(body);
  students.forEach((s) => {
    const tr = document.createElement("tr");
    tr.className = "border-b border-slate-100 last:border-0";
    tr.innerHTML = `
      <td class="py-2 pr-2">${escapeHtml(s.pseudonym)}</td>
      <td class="py-2 pr-2 font-mono text-xs text-slate-500">${escapeHtml(s.question_id)}</td>
      <td class="py-2 pr-2 text-right tabular-nums">${s.mark} / ${s.max}</td>
      <td class="py-2 pl-2">${s.top_misconception ? escapeHtml(humanizeTag(s.top_misconception)) : "—"}</td>
    `;
    body.appendChild(tr);
  });
}

// ---------------------------------------------------------------------
// 9. Init
// ---------------------------------------------------------------------

async function init() {
  initNav();
  initSetupScreen();
  initConfirmScreen();
  initReviewScreen();
  showScreen("setup");
  try {
    await loadQuestions();
  } catch (err) {
    console.error("Failed to load questions", err);
  }
}

document.addEventListener("DOMContentLoaded", init);
