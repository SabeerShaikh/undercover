import type { ClaimStatus } from "./types";

const LABELS: Record<ClaimStatus, string> = {
  waiting: "Waiting",
  in_progress: "In progress",
  waiting_for_sign_off: "Waiting for sign-off",
  decided: "Decided",
};

export function statusLabel(status: ClaimStatus): string {
  return LABELS[status];
}

export function statusClass(status: ClaimStatus): string {
  return `status status-${status}`;
}
