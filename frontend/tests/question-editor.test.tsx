import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { QuestionEditor } from "../src/components/QuestionEditor";
import { api } from "../src/lib/api";

vi.mock("../src/components/ui/Dialog", () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

afterEach(cleanup);

test("a non-algebraic model solution shows the AI-graded tier instead of a blocking error", async () => {
  vi.spyOn(api, "questionTemplate").mockResolvedValue({ variable: "x", criteria: [] });
  vi.spyOn(api, "validateQuestion").mockResolvedValue({
    ok: true, problems: [], verification_tier: "ai_graded",
    verification_tier_notes: ["Step 2 could not be read as mathematics in 'x': 'a proof step'"],
  });
  render(<QuestionEditor question={null} onClose={vi.fn()} onSaved={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Id"), { target: { value: "q9" } });
  fireEvent.change(screen.getByLabelText(/Prompt/), { target: { value: "Prove something." } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check the maths" })); });
  expect(screen.getByText(/AI-graded, not symbolically verified/)).toBeTruthy();
  expect(screen.getByText(/Step 2 could not be read as mathematics/)).toBeTruthy();
});

test("saving includes the instructor's tier override", async () => {
  vi.spyOn(api, "questionTemplate").mockResolvedValue({ variable: "x", criteria: [] });
  vi.spyOn(api, "validateQuestion").mockResolvedValue({ ok: true, problems: [], verification_tier: "verified", verification_tier_notes: [] });
  vi.spyOn(api, "createQuestion").mockResolvedValue({});
  render(<QuestionEditor question={null} onClose={vi.fn()} onSaved={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Id"), { target: { value: "q9" } });
  fireEvent.change(screen.getByLabelText(/Prompt/), { target: { value: "Solve $x=1$." } });
  fireEvent.change(screen.getByLabelText("Verification tier override"), { target: { value: "ai_graded" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save question" })); });
  expect(vi.mocked(api.createQuestion).mock.calls[0][0].verification_tier_override).toBe("ai_graded");
});
