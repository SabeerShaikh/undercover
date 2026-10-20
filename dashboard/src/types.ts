export type ClaimStatus =
  | "waiting"
  | "in_progress"
  | "waiting_for_sign_off"
  | "decided"
  | "left_for_handler";

export interface QueueClaim {
  claim_id: string;
  summary: string;
  amount_claimed: number;
  status: ClaimStatus;
  decision: string | null;
  payout: number | null;
  customer_name: string;
}

export interface ClaimItem {
  description: string;
  category: string;
  amount: number;
}

export interface ClaimDocument {
  name: string;
  type: string;
  content: string;
}

export interface PreviousClaim {
  claim_id: string;
  filed_on: string;
  incident_date: string;
  claim_type: string;
  summary: string;
  outcome: string;
  amount_paid: number;
}

export interface ClaimStep {
  tool_name: string;
  detail: string;
}

export type TodoStatus = "to_do" | "in_progress" | "done" | "left_for_handler";

export interface RunTodo {
  content: string;
  status: TodoStatus;
}

export interface QueueRun {
  id: number;
  cap: number;
  status: "running" | "finished";
  summary: string | null;
  started_at: string;
  finished_at: string | null;
  todos: RunTodo[];
}

export interface ClaimDetail {
  claim_id: string;
  summary: string;
  story: string;
  amount_claimed: number;
  status: ClaimStatus;
  attempts: number;
  items: ClaimItem[];
  documents: ClaimDocument[];
  decision: string | null;
  payout: number | null;
  reason: string | null;
  policy_section: string | null;
  signed_off: boolean;
  paid_amount: number | null;
  policy: {
    policy_id: string;
    plan: string;
    trip: { destination: string; departs_on: string; returns_on: string };
  };
  plan: {
    name: string;
    trip_delay_max: number;
    baggage_max: number;
    deductible: number;
  } | null;
  customer: {
    name: string;
    previous_claims: PreviousClaim[];
  };
  steps: ClaimStep[];
}

export type View =
  | { name: "queue" }
  | { name: "claim"; claimId: string }
  | { name: "instructions" };
