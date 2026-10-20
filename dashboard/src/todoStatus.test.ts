import { expect, it } from "vitest";
import { claimIdsIn, todoClass, todoLabel } from "./todoStatus";

it("labels to-do statuses", () => {
  expect(todoLabel("to_do")).toBe("To do");
  expect(todoLabel("in_progress")).toBe("In progress");
  expect(todoLabel("done")).toBe("Done");
  expect(todoLabel("left_for_handler")).toBe("Left for a handler");
});

it("reuses claim status colors", () => {
  expect(todoClass("to_do")).toBe("status status-waiting");
  expect(todoClass("in_progress")).toBe("status status-in_progress");
  expect(todoClass("done")).toBe("status status-decided");
  expect(todoClass("left_for_handler")).toBe("status status-left_for_handler");
});

it("finds claim ids in a to-do", () => {
  expect(claimIdsIn("Work CLM-1013 then CLM-1014")).toEqual([
    "CLM-1013",
    "CLM-1014",
  ]);
  expect(claimIdsIn("Write the summary")).toEqual([]);
});
