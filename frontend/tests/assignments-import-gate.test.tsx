import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Assignments from "../src/pages/Assignments";
import { api } from "../src/lib/api";
import { ingestionApi } from "../src/lib/ingestionApi";
import { WorkbenchProvider } from "../src/state/WorkbenchContext";

vi.mock("../src/components/ui/Toast", () => ({ useToast: () => ({ error: vi.fn(), success: vi.fn() }) }));

afterEach(cleanup);

test("whole-PDF import is offered for graded CA and final exam assignments, not just tutorials", async () => {
  vi.spyOn(api, "listAssignments").mockResolvedValue([
    { id: "ca1", title: "CA 1", kind: "ca", question_ids: [], roster: [], created_at: "" },
    { id: "exam1", title: "Final Exam", kind: "exam", question_ids: [], roster: [], created_at: "" },
  ]);
  vi.spyOn(api, "listQuestions").mockResolvedValue([]);
  vi.spyOn(ingestionApi, "list").mockResolvedValue([]);
  render(<WorkbenchProvider><Assignments /></WorkbenchProvider>);
  await screen.findByText("CA 1");
  expect(screen.getAllByLabelText("Upload Question Paper PDF")).toHaveLength(2);
});
