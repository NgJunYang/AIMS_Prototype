import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import Confirm from "../src/pages/Confirm";
import { WorkbenchProvider, useWorkbench } from "../src/state/WorkbenchContext";
import { api } from "../src/lib/api";
import type { AssignmentReviewStatus, Question, Submission } from "../src/types";

vi.mock("../src/components/ui/Toast", () => ({ useToast: () => ({ error: vi.fn(), success: vi.fn() }) }));

let records: Submission[];
const clone = <T,>(value: T): T => structuredClone(value);
const record = (id: string) => records.find((s) => s.id === id)!;
function invalidate(sub: Submission) {
  sub.review_invalidated = !!sub.reviewed;
  sub.reviewed = false;
  records.forEach((s) => { s.published = false; });
}
function progress(): AssignmentReviewStatus {
  const ready = records.every((s) => s.reviewed && s.marks && s.feedback);
  return {
    assignment_id: "tutorial5", assignment_title: "Tutorial 5", student_pseudonym: record("s4").student_pseudonym!, student_id: "2500001",
    total_questions: 5, reviewed_count: records.filter((s) => s.reviewed).length,
    ready_to_publish: ready, published: ready && records.every((s) => s.published),
    questions: records.map((s) => ({ question_id: s.question_id, submission_id: s.id, marked: !!s.marks,
      has_feedback: !!s.feedback, reviewed: !!s.reviewed, published: !!s.published, problems: [] })),
  };
}

function Resume() {
  const wb = useWorkbench();
  return <button onClick={() => wb.resumeSubmission("s4")}>Load saved question</button>;
}

async function open(reviewed = 3) {
  records = [1, 2, 3, 4, 5].map((n) => ({
    id: `s${n}`, question_id: `Q${n}`, assignment_id: "tutorial5", channel: "tutorial",
    student_pseudonym: "Student A", student_id: "2500001", published: false,
    reviewed: n <= 3 && n <= reviewed || n === 5 && reviewed >= 4 || reviewed === 5,
    confirmed_steps: [{ index: 1, latex: "x = 5", confidence: "high" }],
    marks: { criteria: [{ criterion_id: "C1", proposed: 2, suggested: 2, max: 3, justification: "Setup" }] },
    feedback: { what_went_well: "AI well", what_went_wrong: "AI attention", how_to_improve: "AI improve", references: [] },
  }));
  if (reviewed === 3) { records[4].marks = null; records[4].feedback = null; }
  vi.spyOn(api, "getSubmission").mockImplementation(async (id) => clone(record(id)));
  vi.spyOn(api, "listQuestions").mockResolvedValue(records.map((s) => ({
    id: s.question_id, prompt: "Solve", criteria: [{ id: "C1", max: 3, description: "Method" }],
    model_solution_steps: ["x = 5"], variable: "x", topic_tag: "quadratics",
  } satisfies Question)));
  vi.spyOn(api, "assignmentReviewStatus").mockImplementation(async () => progress());
  vi.spyOn(api, "review").mockImplementation(async (id, body) => {
    const sub = record(id);
    sub.feedback = { ...body.feedback, references: [] };
    sub.student_pseudonym = body.identity.name;
    sub.student_id = body.identity.student_id;
    sub.reviewed = true;
    sub.review_invalidated = false;
    return clone(sub);
  });
  vi.spyOn(api, "publishAssignment").mockImplementation(async () => {
    if (!progress().ready_to_publish) throw new Error("Incomplete tutorial");
    records.forEach((s) => { s.published = true; });
    return progress();
  });
  vi.spyOn(api, "unpublishAssignment").mockImplementation(async () => {
    records.forEach((s) => { s.published = false; });
    return progress();
  });
  vi.spyOn(api, "publish").mockRejectedValue(new Error("Individual publication must not be used"));
  vi.spyOn(api, "override").mockImplementation(async (id, criterionId, proposed) => {
    const sub = record(id);
    invalidate(sub);
    Object.assign(sub.marks!.criteria.find((c) => c.criterion_id === criterionId)!, { proposed, overridden: true });
    return clone(sub);
  });
  vi.spyOn(api, "updateFeedback").mockImplementation(async (id, feedback) => {
    const sub = record(id);
    invalidate(sub);
    sub.feedback = { ...feedback, references: [] };
    return clone(sub);
  });
  render(<WorkbenchProvider><Resume /><Confirm /></WorkbenchProvider>);
  // Flush the async Workbench resume and its progress effect before asserting.
  await act(async () => { fireEvent.click(screen.getByText("Load saved question")); });
  await screen.findByText(`${reviewed} / 5 questions reviewed`);
}

beforeEach(() => vi.spyOn(window, "confirm").mockReturnValue(true));
afterEach(cleanup);

test("shows ordered 3/5 progress and blocks incomplete tutorial publication", async () => {
  await open();
  expect((screen.getByRole("button", { name: "Publish Tutorial Results" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText("Not marked")).toBeTruthy();
  expect(screen.getByText("2 questions still require instructor review before results can be published.")).toBeTruthy();
  expect(screen.queryByText(/visible to the student as soon/)).toBeNull();
});

test("review saves pending identity and all feedback before separate group publication", async () => {
  await open(4);
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Confirmed Student A" } });
  for (const [label, value] of [["What went well", "Final well"], ["What needs attention", "Final attention"], ["How to improve", "Final improve"]]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  fireEvent.click(screen.getByRole("button", { name: "Mark Question as Reviewed" }));
  await screen.findByText("5 / 5 questions reviewed");
  expect(api.review).toHaveBeenCalledWith("s4", {
    identity: { name: "Confirmed Student A", student_id: "2500001" },
    feedback: expect.objectContaining({ what_went_well: "Final well", what_went_wrong: "Final attention", how_to_improve: "Final improve" }),
  });
  expect(api.publishAssignment).not.toHaveBeenCalled();
  const publish = screen.getByRole("button", { name: "Publish Tutorial Results" }) as HTMLButtonElement;
  expect(publish.disabled).toBe(false);
  fireEvent.click(publish);
  await screen.findByText(/All reviewed marks and feedback for Tutorial 5 are now available/);
  expect(api.publishAssignment).toHaveBeenCalledWith("s4");
  expect(api.publish).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Unpublish Tutorial Results" }));
  await screen.findByRole("button", { name: "Publish Tutorial Results" });
  expect(records.every((s) => !s.published)).toBe(true);
});

test("feedback edits after review block release and require another review", async () => {
  await open(5);
  fireEvent.change(screen.getByLabelText("How to improve"), { target: { value: "Changed advice" } });
  expect((screen.getByRole("button", { name: "Publish Tutorial Results" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Save feedback edits" }));
  await screen.findByText("4 / 5 questions reviewed");
  expect(screen.getByText("The assessment changed after the previous review.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Review Question Again" }));
  await screen.findByText("5 / 5 questions reviewed");
  expect(record("s4").feedback!.how_to_improve).toBe("Changed advice");
});

test("score overrides retain AI suggestion and invalidate review", async () => {
  await open(5);
  const score = screen.getByRole("spinbutton", { name: /Suggested score for C1/ });
  fireEvent.change(score, { target: { value: "3" } });
  fireEvent.blur(score);
  await screen.findByText("4 / 5 questions reviewed");
  expect(screen.getByText("AI suggested: 2 / 3 · Instructor final: 3 / 3")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Publish Tutorial Results" }) as HTMLButtonElement).disabled).toBe(true);
});

test("review waits for an override that is still saving", async () => {
  await open(4);
  let finish!: () => void;
  vi.mocked(api.override).mockImplementation(() => new Promise((resolve) => {
    finish = () => { invalidate(record("s4")); resolve(clone(record("s4"))); };
  }));
  const score = screen.getByRole("spinbutton", { name: /Suggested score for C1/ });
  fireEvent.change(score, { target: { value: "3" } });
  fireEvent.blur(score);
  await userEvent.click(screen.getByRole("button", { name: "Mark Question as Reviewed" }));
  expect(api.review).not.toHaveBeenCalled();
  finish();
  await waitFor(() => expect((screen.getByRole("button", { name: "Mark Question as Reviewed" }) as HTMLButtonElement).disabled).toBe(false));
});

test("progress opens another question through Workbench", async () => {
  await open();
  fireEvent.click(screen.getByRole("button", { name: "✓ Q1" }));
  await screen.findByText("Q1 — Instructor Review");
  expect(api.getSubmission).toHaveBeenCalledWith("s1");
});

test("progress failure disables publication and leaves a retry", async () => {
  await open(5);
  vi.mocked(api.assignmentReviewStatus).mockRejectedValue(new Error("Progress unavailable"));
  fireEvent.click(screen.getByRole("button", { name: "Refresh tutorial progress" }));
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "Publish Tutorial Results" })).toBeNull();
  expect(api.publishAssignment).not.toHaveBeenCalled();
});

test("dirty working cannot be approved against previous marks", async () => {
  await open(5);
  // Direct input covers the debounce window before automatic marking begins.
  const inputs = screen.getAllByRole("textbox");
  const working = inputs.find((input) => (input as HTMLInputElement).value === "x = 5")!;
  fireEvent.change(working, { target: { value: "x = 3" } });
  expect((screen.getByRole("button", { name: "Review Question Again" }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Publish Tutorial Results" }) as HTMLButtonElement).disabled).toBe(true);
});
