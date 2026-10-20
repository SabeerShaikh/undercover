import { statusLabel } from "./statusLabel";
import type { ClaimStatus, QueueClaim } from "./types";

const STATUS_ORDER: ClaimStatus[] = [
  "waiting",
  "in_progress",
  "waiting_for_sign_off",
  "decided",
  "left_for_handler",
];

export interface StatusCount {
  status: ClaimStatus;
  label: string;
  count: number;
}

export interface DecisionCount {
  decision: string;
  label: string;
  count: number;
}

export function countByStatus(claims: QueueClaim[]): StatusCount[] {
  const counts = new Map<ClaimStatus, number>();
  for (const status of STATUS_ORDER) {
    counts.set(status, 0);
  }
  for (const claim of claims) {
    counts.set(claim.status, (counts.get(claim.status) ?? 0) + 1);
  }
  return STATUS_ORDER.map((status) => ({
    status,
    label: statusLabel(status),
    count: counts.get(status) ?? 0,
  }));
}

export function decisionLabel(decision: string): string {
  const labels: Record<string, string> = {
    approve: "Approve",
    decline: "Decline",
    refer: "Refer",
    none: "No decision",
  };
  return labels[decision] ?? decision;
}

export function countByDecision(claims: QueueClaim[]): DecisionCount[] {
  const counts = new Map<string, number>();
  for (const claim of claims) {
    const key = claim.decision ?? "none";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const order = ["approve", "decline", "refer", "none"];
  const keys = [
    ...order.filter((key) => counts.has(key)),
    ...[...counts.keys()]
      .filter((key) => !order.includes(key))
      .sort((a, b) => a.localeCompare(b)),
  ];
  return keys.map((decision) => ({
    decision,
    label: decisionLabel(decision),
    count: counts.get(decision) ?? 0,
  }));
}
