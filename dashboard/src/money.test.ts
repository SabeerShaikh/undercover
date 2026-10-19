import { expect, it } from "vitest";
import { formatUsd } from "./money";

it("formats US dollars with cents", () => {
  expect(formatUsd(1150)).toBe("$1,150.00");
  expect(formatUsd(420)).toBe("$420.00");
});
