import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { TutorialImportPanel } from "../src/components/TutorialImportPanel";
import { WorkbenchProvider } from "../src/state/WorkbenchContext";
import { ingestionApi } from "../src/lib/ingestionApi";
import { api } from "../src/lib/api";
import type { ImportWorking, TutorialImport } from "../src/types";

let remote: TutorialImport;
const copy = <T,>(value: T): T => structuredClone(value);
const questions = () => ["Q1", "Q2(a)"].map((label, i) => ({ question_id: `qid${i}`, label,
  prompt: `Solve x = ${i + 1}`, variable: "x", topic_tag: "algebra", source_pages: [1, 2], confidence: "high" as const, notes: "", problems: [] }));
const working = (): ImportWorking[] => questions().map((q, i) => ({ block_id: `block${i}`, question_id: q.question_id,
  label: q.label, source_pages: [1, 2], confidence: "high", status: "detected", confirmed: false,
  steps: [{ index: 1, latex: `x = ${i + 1}`, confidence: "high" }], notes: "", criteria: [{ id: "C1", max: 2, description: "Correct working" }] }));
const onOpen = vi.fn();
const onChanged = vi.fn();

beforeEach(() => {
  remote = { id: "import123", assignment_id: "t5", kind: "setup", stage: "questions", revision: 0, filename: "questions.pdf",
    page_count: 2, solution_page_count: 0, title: "Tutorial 5", questions: questions(), solutions: [], answers: [],
    identity: { name: null, student_id: null, confidence: "low" }, warnings: [], submission_ids: [] };
  vi.spyOn(ingestionApi, "list").mockResolvedValue([]);
  vi.spyOn(ingestionApi, "get").mockImplementation(async () => copy(remote));
  vi.spyOn(ingestionApi, "questions").mockImplementation(async () => copy(remote));
  vi.spyOn(ingestionApi, "confirmQuestions").mockImplementation(async (draft) => {
    remote = { ...copy(draft), stage: "solutions", revision: draft.revision + 1 };
    return copy(remote);
  });
  vi.spyOn(ingestionApi, "solutions").mockImplementation(async (draft) => {
    remote = { ...copy(draft), solutions: working(), solution_page_count: 2, revision: draft.revision + 1 };
    return copy(remote);
  });
  vi.spyOn(ingestionApi, "confirmSolutions").mockImplementation(async (draft) => {
    remote = { ...copy(draft), stage: "complete", revision: draft.revision + 1 }; return copy(remote);
  });
  vi.spyOn(ingestionApi, "student").mockImplementation(async () => {
    remote = { ...remote, id: "student123", filename: "student.pdf", kind: "student", stage: "answers", questions: questions(),
      identity: { name: "Alex Tan", student_id: "2500123", confidence: "high" }, answers: working() };
    return copy(remote);
  });
  vi.spyOn(ingestionApi, "confirmAnswers").mockImplementation(async (draft) => {
    remote = { ...copy(draft), stage: "complete", submission_ids: ["s1", "s2"], revision: draft.revision + 1 }; return copy(remote);
  });
  vi.spyOn(ingestionApi, "mark").mockResolvedValue({ complete: true, results: [
    { submission_id: "s1", question_id: "qid0", marked: true, error: null }, { submission_id: "s2", question_id: "qid1", marked: true, error: null }] });
  vi.spyOn(api, "assignmentReviewStatus").mockResolvedValue({ assignment_id: "t5", assignment_title: "Tutorial 5", student_pseudonym: "Alex Tan", student_id: "2500123",
    total_questions: 2, reviewed_count: 0, ready_to_publish: false, published: false,
    questions: questions().map((q, i) => ({ question_id: q.question_id, submission_id: `s${i + 1}`, marked: true, has_feedback: true, reviewed: false, published: false, problems: [] })) });
  vi.spyOn(api, "listQuestions").mockResolvedValue([]);
  vi.spyOn(api, "getSubmission").mockResolvedValue({ id: "s1", question_id: "qid0", assignment_id: "t5", student_pseudonym: "Alex Tan", student_id: "2500123", confirmed_steps: [] });
  vi.spyOn(api, "publishAssignment").mockRejectedValue(new Error("Import must never publish"));
  onOpen.mockClear(); onChanged.mockClear();
});
afterEach(cleanup);

function mount(ready = false) {
  return render(<WorkbenchProvider><TutorialImportPanel assignmentId="t5" ready={ready} onChanged={onChanged} onOpen={onOpen} /></WorkbenchProvider>);
}
async function upload(label: string) {
  await act(async () => { fireEvent.change(screen.getByLabelText(label), { target: { files: [new File(["%PDF-test"], "tutorial.pdf", { type: "application/pdf" })] } }); });
}
async function click(name: string) {
  await act(async () => { fireEvent.click(screen.getByRole("button", { name })); });
}

test("question detection stays editable and preserves instructor changes/order at confirmation", async () => {
  mount();
  await upload("Upload Question Paper PDF");
  fireEvent.change(screen.getByLabelText("Question 1 text"), { target: { value: "Professor edited prompt" } });
  fireEvent.change(screen.getByLabelText("Question 1 label"), { target: { value: "Question 1" } });
  await click("Move Question 1 down");
  await click("Confirm Questions");
  const saved = vi.mocked(ingestionApi.confirmQuestions).mock.calls[0][0];
  expect(saved.questions.map((q) => q.label)).toEqual(["Q2(a)", "Question 1"]);
  expect(saved.questions[1].prompt).toBe("Professor edited prompt");
  expect(ingestionApi.mark).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Upload Model Solutions PDF")).toBeTruthy();
});

test("solutions and rubrics require per-block confirmation and remain editable", async () => {
  mount();
  await upload("Upload Question Paper PDF");
  await click("Confirm Questions");
  await upload("Upload Model Solutions PDF");
  const button = screen.getByRole("button", { name: "Confirm Solutions & Rubrics" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("Criterion 1.1 marks"), { target: { value: "4" } });
  fireEvent.click(screen.getByLabelText("Confirm block 1"));
  fireEvent.click(screen.getByLabelText("Confirm block 2"));
  expect(button.disabled).toBe(false);
  // A further rubric edit resets its acknowledgement.
  fireEvent.change(screen.getByLabelText("Criterion 1.1 description"), { target: { value: "Professor rubric" } });
  expect(button.disabled).toBe(true);
  fireEvent.click(screen.getByLabelText("Confirm block 1"));
  await click("Confirm Solutions & Rubrics");
  expect(remote.solutions[0].criteria[0]).toEqual({ id: "C1", max: 4, description: "Professor rubric" });
  expect(onChanged).toHaveBeenCalled();
  expect(ingestionApi.mark).not.toHaveBeenCalled();
});

test("student segmentation saves corrected identity/working before marking and opens existing review", async () => {
  mount(true);
  await upload("Upload Completed Tutorial PDF");
  expect(screen.getByText("Detected Student Answers")).toBeTruthy();
  expect(ingestionApi.mark).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Imported student name"), { target: { value: "Confirmed Alex" } });
  const line = screen.getAllByRole("textbox").find((input) => (input as HTMLInputElement).value === "x = 1")!;
  fireEvent.change(line, { target: { value: "x = 12" } });
  expect((screen.getByRole("button", { name: "Confirm & Start Marking" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByLabelText("Confirm block 1"));
  fireEvent.click(screen.getByLabelText("Confirm block 2"));
  await click("Confirm & Start Marking");
  expect(vi.mocked(ingestionApi.confirmAnswers).mock.calls[0][0].identity.name).toBe("Confirmed Alex");
  expect(vi.mocked(ingestionApi.confirmAnswers).mock.calls[0][0].answers[0].steps[0].latex).toBe("x = 12");
  expect(vi.mocked(ingestionApi.confirmAnswers).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(ingestionApi.mark).mock.invocationCallOrder[0]);
  expect(api.publishAssignment).not.toHaveBeenCalled();
  expect(screen.getByText(/Instructor review: 0 \/ 2 · Published: No/)).toBeTruthy();
  await click("Open Instructor Review");
  expect(api.getSubmission).toHaveBeenCalledWith("s1");
  expect(onOpen).toHaveBeenCalled();
});

test("missing student answers are visible and can be confirmed blank", async () => {
  vi.mocked(ingestionApi.student).mockImplementation(async () => ({ ...remote, kind: "student", stage: "answers", identity: { name: "Alex", student_id: "2500123", confidence: "high" },
    answers: working().map((w, i) => i === 1 ? { ...w, status: "not_detected", steps: [] } : w) }));
  mount(true);
  await upload("Upload Completed Tutorial PDF");
  expect(screen.getByText("No answer detected")).toBeTruthy();
  fireEvent.click(screen.getByLabelText("Confirm block 1")); fireEvent.click(screen.getByLabelText("Confirm block 2"));
  await click("Confirm & Start Marking");
  expect(vi.mocked(ingestionApi.confirmAnswers).mock.calls[0][0].answers[1].steps).toEqual([]);
});

test("unmatched or duplicate mappings prevent confirmation until corrected", async () => {
  mount(true);
  await upload("Upload Completed Tutorial PDF");
  fireEvent.change(screen.getByLabelText("Mapping 2"), { target: { value: "qid0" } });
  fireEvent.click(screen.getByLabelText("Confirm block 1")); fireEvent.click(screen.getByLabelText("Confirm block 2"));
  expect((screen.getByRole("button", { name: "Confirm & Start Marking" }) as HTMLButtonElement).disabled).toBe(true);
  expect(ingestionApi.confirmAnswers).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Mapping 2"), { target: { value: "qid1" } });
  fireEvent.click(screen.getByLabelText("Confirm block 2"));
  expect((screen.getByRole("button", { name: "Confirm & Start Marking" }) as HTMLButtonElement).disabled).toBe(false);
});

test("conflict errors preserve corrections and do not launch marking", async () => {
  vi.mocked(ingestionApi.confirmAnswers).mockRejectedValue(new Error("Submissions already exist; nothing overwritten."));
  mount(true);
  await upload("Upload Completed Tutorial PDF");
  fireEvent.change(screen.getByLabelText("Imported student name"), { target: { value: "Corrected name" } });
  fireEvent.click(screen.getByLabelText("Confirm block 1")); fireEvent.click(screen.getByLabelText("Confirm block 2"));
  await click("Confirm & Start Marking");
  expect(screen.getByRole("alert").textContent).toContain("already exist");
  expect((screen.getByLabelText("Imported student name") as HTMLInputElement).value).toBe("Corrected name");
  expect(ingestionApi.mark).not.toHaveBeenCalled();
});

test("partial marking errors expose retry without repeating confirmation", async () => {
  vi.mocked(ingestionApi.mark).mockResolvedValue({ complete: false, results: [{ submission_id: "s1", question_id: "qid0", marked: false, error: "Marking unavailable" }] });
  mount(true);
  await upload("Upload Completed Tutorial PDF");
  fireEvent.click(screen.getByLabelText("Confirm block 1")); fireEvent.click(screen.getByLabelText("Confirm block 2"));
  await click("Confirm & Start Marking");
  expect(screen.getByRole("alert").textContent).toContain("Marking unavailable");
  await click("Start / Retry Incomplete Marking");
  expect(ingestionApi.confirmAnswers).toHaveBeenCalledTimes(1);
  expect(ingestionApi.mark).toHaveBeenCalledTimes(2);
});
