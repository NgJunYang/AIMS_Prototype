import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Assignments from "../src/pages/Assignments";
import { api } from "../src/lib/api";

vi.mock("../src/components/ui/Toast", () => ({ useToast: () => ({ error: vi.fn(), success: vi.fn() }) }));

afterEach(cleanup);

async function open(settings?: object) {
  vi.spyOn(api, "listAssignments").mockResolvedValue([{ id: "ca1", title: "CA 1", kind: "ca", question_ids: [], roster: [], created_at: "", feedback_settings: settings }]);
  vi.spyOn(api, "listQuestions").mockResolvedValue([]);
  vi.spyOn(api, "updateFeedbackSettings").mockImplementation(async (_, value) => ({ feedback_settings: value }));
  vi.spyOn(api, "regenerateFeedback").mockRejectedValue(new Error("Saving settings must not regenerate"));
  render(<Assignments />);
  await screen.findByText("CA 1");
  fireEvent.click(screen.getByText("Feedback settings"));
}

test("old assignments load balanced disclosure defaults without generating feedback", async () => {
  await open();
  expect((screen.getByRole("radio", { name: "balanced" }) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
  expect((screen.getByLabelText("Custom instructions") as HTMLTextAreaElement).value).toBe("");
  expect((screen.getByRole("button", { name: "Save Feedback Settings" }) as HTMLButtonElement).disabled).toBe(true);
  expect(api.regenerateFeedback).not.toHaveBeenCalled();
});

test("loads saved settings and saves changed variation, instructions and disclosure", async () => {
  await open({ variation: "focused", custom_instructions: "Year 1 language", reveal_full_solution: false });
  expect((screen.getByRole("radio", { name: "focused" }) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
  expect(screen.getByText(/targeted explanations and hints/)).toBeTruthy();
  expect((screen.getByLabelText("Custom instructions") as HTMLTextAreaElement).value).toBe("Year 1 language");
  fireEvent.click(screen.getByRole("radio", { name: "exploratory" }));
  fireEvent.change(screen.getByLabelText("Custom instructions"), { target: { value: "Focus on the misconception." } });
  fireEvent.click(screen.getByRole("checkbox"));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save Feedback Settings" })); });
  expect(api.updateFeedbackSettings).toHaveBeenCalledExactlyOnceWith("ca1", {
    variation: "exploratory", custom_instructions: "Focus on the misconception.", reveal_full_solution: true,
  });
  expect(screen.getByRole("status").textContent).toContain("Existing feedback stays unchanged");
  expect(api.regenerateFeedback).not.toHaveBeenCalled();
});

test("failed settings save retains the instructor's draft", async () => {
  await open();
  vi.mocked(api.updateFeedbackSettings).mockRejectedValue(new Error("Disconnected"));
  fireEvent.change(screen.getByLabelText("Custom instructions"), { target: { value: "Keep my edits" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save Feedback Settings" })); });
  expect(screen.getByRole("alert")).toBeTruthy();
  expect((screen.getByLabelText("Custom instructions") as HTMLTextAreaElement).value).toBe("Keep my edits");
  expect((screen.getByRole("button", { name: "Save Feedback Settings" }) as HTMLButtonElement).disabled).toBe(false);
});
