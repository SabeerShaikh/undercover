import { expect, it } from "vitest";
import { countByDecision, countByStatus } from "./queueStats";
import type { QueueClaim } from "./types";

const claims: QueueClaim[] = [
  {
    claim_id: "CLM-1",
    summary: "a",
    amount_claimed: 1,
    status: "waiting",
    decision: null,
    payout: null,
    customer_name: "A",
  },
  {
    claim_id: "CLM-2",
    summary: "b",
    amount_claimed: 2,
    status: "decided",
    decision: "approve",
    payout: 100,
    customer_name: "B",
  },
  {
    claim_id: "CLM-3",
    summary: "c",
    amount_claimed: 3,
    status: "decided",
    decision: "decline",
    payout: 0,
    customer_name: "C",
  },
];

it("counts claims by status", () => {
  const counts = countByStatus(claims);
  expect(counts.find((row) => row.status === "waiting")?.count).toBe(1);
  expect(counts.find((row) => row.status === "decided")?.count).toBe(2);
  expect(counts.find((row) => row.status === "in_progress")?.count).toBe(0);
});

it("counts claims by decision", () => {
  const counts = countByDecision(claims);
  expect(counts.find((row) => row.decision === "approve")?.count).toBe(1);
  expect(counts.find((row) => row.decision === "decline")?.count).toBe(1);
  expect(counts.find((row) => row.decision === "none")?.count).toBe(1);
});
