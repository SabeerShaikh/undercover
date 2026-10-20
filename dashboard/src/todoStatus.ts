import { statusClass } from "./statusLabel";
import type { ClaimStatus, TodoStatus } from "./types";

const LABELS: Record<TodoStatus, string> = {
  to_do: "To do",
  in_progress: "In progress",
  done: "Done",
  left_for_handler: "Left for a handler",
};

const CLAIM_STATUS: Record<TodoStatus, ClaimStatus> = {
  to_do: "waiting",
  in_progress: "in_progress",
  done: "decided",
  left_for_handler: "left_for_handler",
};

export function todoLabel(status: TodoStatus): string {
  return LABELS[status];
}

export function todoClass(status: TodoStatus): string {
  return statusClass(CLAIM_STATUS[status]);
}

export function claimIdsIn(text: string): string[] {
  return text.match(/CLM-\d+/g) ?? [];
}
