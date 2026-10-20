import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import type { ClaimDetail, QueueClaim, QueueRun } from "./types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const queue: QueueClaim[] = [
  {
    claim_id: "CLM-1001",
    summary: "Flight home canceled",
    amount_claimed: 420,
    status: "waiting",
    decision: null,
    payout: null,
    customer_name: "Maya Patel",
  },
  {
    claim_id: "CLM-1002",
    summary: "Suitcase lost",
    amount_claimed: 1150,
    status: "waiting_for_sign_off",
    decision: "approve",
    payout: 1150,
    customer_name: "Tom Becker",
  },
];

const claim1001: ClaimDetail = {
  claim_id: "CLM-1001",
  summary: "Flight home canceled",
  story: "My flight home from Rome was canceled.",
  amount_claimed: 420,
  status: "waiting",
  items: [
    {
      description: "Airport hotel, one night",
      category: "accommodation",
      amount: 245,
    },
    { description: "Dinner and breakfast", category: "meals", amount: 95 },
    { description: "Taxis", category: "transport", amount: 80 },
  ],
  documents: [
    {
      name: "Hotel receipt",
      type: "receipt",
      content: "Total paid: $245.00.",
    },
  ],
  decision: null,
  payout: null,
  reason: null,
  policy_section: null,
  signed_off: false,
  paid_amount: null,
  attempts: 0,
  policy: {
    policy_id: "POL-2001",
    plan: "premium",
    trip: {
      destination: "Rome, Italy",
      departs_on: "2026-06-10",
      returns_on: "2026-06-18",
    },
  },
  plan: {
    name: "UnderCover Premium",
    trip_delay_max: 800,
    baggage_max: 1500,
    deductible: 50,
  },
  customer: {
    name: "Maya Patel",
    previous_claims: [
      {
        claim_id: "CLM-0412",
        filed_on: "2024-08-19",
        incident_date: "2024-08-09",
        claim_type: "baggage_delay",
        summary: "Bag late in Lisbon",
        outcome: "approved",
        amount_paid: 140,
      },
    ],
  },
  steps: [],
};

const claim1002: ClaimDetail = {
  ...claim1001,
  claim_id: "CLM-1002",
  summary: "Suitcase lost",
  story: "My suitcase never arrived.",
  amount_claimed: 1150,
  status: "waiting_for_sign_off",
  decision: "approve",
  payout: 1150,
  reason: "Covered baggage loss.",
  policy_section: "Section 5",
  customer: { name: "Tom Becker", previous_claims: [] },
  policy: {
    policy_id: "POL-2002",
    plan: "premium",
    trip: {
      destination: "Prague, Czech Republic",
      departs_on: "2026-06-20",
      returns_on: "2026-06-29",
    },
  },
  items: [
    { description: "Hard-shell suitcase", category: "luggage", amount: 280 },
  ],
  documents: [],
  steps: [{ tool_name: "record_decision", detail: "approve payout=1150" }],
};

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function queueFetch(
  extra?: (url: string, method: string) => Response | undefined,
  run: QueueRun | null = null,
) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/runs/latest")) {
      return Promise.resolve(jsonResponse(run));
    }
    const custom = extra?.(url, method);
    if (custom) return Promise.resolve(custom);
    if (url.endsWith("/api/claims") && method === "GET") {
      return Promise.resolve(jsonResponse(queue));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
}

it("shows the claims queue", async () => {
  vi.stubGlobal("fetch", queueFetch());
  render(<App />);
  expect(await screen.findByText("CLM-1001")).toBeDefined();
  expect(screen.getByText("Maya Patel")).toBeDefined();
  expect(screen.getByText("$420.00")).toBeDefined();
  expect(screen.getByText(/2 claims/)).toBeDefined();
  expect(screen.getByText(/still open/)).toBeDefined();
  expect(screen.getByLabelText("Claims by status")).toBeDefined();
  expect(screen.getByLabelText("Claims by decision")).toBeDefined();
  expect(screen.getByLabelText("Waiting: 1")).toBeDefined();
  expect(screen.getByLabelText("Waiting for sign-off: 1")).toBeDefined();
  expect(screen.getByLabelText("Left for a handler: 0")).toBeDefined();
  expect(screen.getByLabelText("Approve: 1")).toBeDefined();
  expect(screen.getAllByText("$1,150.00").length).toBeGreaterThan(0);
});

it("opens a claim with story, items, documents and policy", async () => {
  vi.stubGlobal(
    "fetch",
    queueFetch((url) => {
      if (url.includes("/api/claims/CLM-1001")) {
        return jsonResponse(claim1001);
      }
      return undefined;
    }),
  );
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Open claim CLM-1001" }),
  );
  expect(
    await screen.findByText("My flight home from Rome was canceled."),
  ).toBeDefined();
  expect(screen.getByText(/Airport hotel/)).toBeDefined();
  expect(screen.getByText(/Hotel receipt/)).toBeDefined();
  expect(screen.getByText("Maya Patel")).toBeDefined();
  expect(screen.getByText(/UnderCover Premium/)).toBeDefined();
});

it("shows a decision and signs off a waiting claim", async () => {
  let current = claim1002;
  vi.stubGlobal(
    "fetch",
    queueFetch((url, method) => {
      if (url.includes("/sign-off")) {
        current = { ...current, signed_off: true };
        return jsonResponse({ status: "signed_off" });
      }
      if (url.includes("/pay")) {
        current = { ...current, status: "decided", paid_amount: 1150 };
        return jsonResponse({ status: "paid" });
      }
      if (url.includes("/api/claims/CLM-1002")) {
        return jsonResponse(current);
      }
      return method === "GET" ? undefined : jsonResponse({}, 404);
    }),
  );
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Open claim CLM-1002" }),
  );
  expect(await screen.findByText("Covered baggage loss.")).toBeDefined();
  expect(screen.getByText("approve")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Sign off and pay" }));
  await waitFor(() => {
    expect(screen.getByText(/paid \$1,150\.00/)).toBeDefined();
  });
});

it("starts the agent on a waiting claim", async () => {
  let current: ClaimDetail = claim1001;
  vi.stubGlobal(
    "fetch",
    queueFetch((url, method) => {
      if (url.endsWith("/run") && method === "POST") {
        current = {
          ...current,
          status: "in_progress",
          steps: [{ tool_name: "get_claim", detail: "Read claim CLM-1001" }],
        };
        return jsonResponse({ status: "started" });
      }
      if (url.includes("/api/claims/CLM-1001")) {
        return jsonResponse(current);
      }
      return undefined;
    }),
  );
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Open claim CLM-1001" }),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Run agent" }));
  expect(await screen.findByText("In progress")).toBeDefined();
  expect(screen.getByText(/get_claim/)).toBeDefined();
});

it("shows read-only instructions", async () => {
  const queueText = "You run the UnderCover claims queue.";
  const claimText = "You are the UnderCover Agent.";
  vi.stubGlobal(
    "fetch",
    queueFetch((url) => {
      if (url.endsWith("/api/instructions")) {
        return jsonResponse({ queue: queueText, claim: claimText });
      }
      return undefined;
    }),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Instructions" }));
  expect(
    await screen.findByRole("heading", { name: "Running the queue" }),
  ).toBeDefined();
  expect(
    screen.getByRole("heading", { name: "Working a claim" }),
  ).toBeDefined();
  expect(screen.getByText(queueText)).toBeDefined();
  expect(screen.getByText(claimText)).toBeDefined();
  expect(screen.queryByRole("textbox")).toBeNull();
});

it("shows no run yet before the first run", async () => {
  vi.stubGlobal("fetch", queueFetch());
  render(<App />);
  expect(await screen.findByText("No run yet")).toBeDefined();
});

it("shows a running run and opens a claim from a to-do item", async () => {
  const running: QueueRun = {
    id: 1,
    cap: 2,
    status: "running",
    summary: null,
    started_at: "2026-01-01T00:00:00Z",
    finished_at: null,
    todos: [
      { content: "Work CLM-1013", status: "in_progress" },
      { content: "Work CLM-1014", status: "to_do" },
    ],
  };
  vi.stubGlobal(
    "fetch",
    queueFetch((url) => {
      if (url.includes("/api/claims/CLM-1013")) {
        return jsonResponse({ ...claim1001, claim_id: "CLM-1013" });
      }
      return undefined;
    }, running),
  );
  render(<App />);
  expect(await screen.findByText(/Running/)).toBeDefined();
  expect(screen.getByText(/Cap 2/)).toBeDefined();
  expect(screen.getByText("To do")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "CLM-1013" }));
  expect(
    await screen.findByRole("heading", { name: "CLM-1013" }),
  ).toBeDefined();
});

it("shows a finished run with its summary", async () => {
  const finished: QueueRun = {
    id: 2,
    cap: 5,
    status: "finished",
    summary: "Five claims decided.",
    started_at: "2026-01-01T00:00:00Z",
    finished_at: "2026-01-01T00:10:00Z",
    todos: [{ content: "Work CLM-1001", status: "done" }],
  };
  vi.stubGlobal("fetch", queueFetch(undefined, finished));
  render(<App />);
  expect(await screen.findByText(/Finished/)).toBeDefined();
  expect(screen.getByText("Five claims decided.")).toBeDefined();
  expect(screen.getByText("Done")).toBeDefined();
});

it("says a claim came back after a failed attempt", async () => {
  const returned: ClaimDetail = {
    ...claim1001,
    attempts: 1,
    steps: [{ tool_name: "error", detail: "The model timed out" }],
  };
  vi.stubGlobal(
    "fetch",
    queueFetch((url) => {
      if (url.includes("/api/claims/CLM-1001")) return jsonResponse(returned);
      return undefined;
    }),
  );
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Open claim CLM-1001" }),
  );
  expect(
    await screen.findByText("This claim came back after a failed attempt."),
  ).toBeDefined();
  expect(screen.getByText("Failed The model timed out")).toBeDefined();
});

it("shows a claim left for a handler and each section once", async () => {
  const left: ClaimDetail = {
    ...claim1001,
    status: "left_for_handler",
    attempts: 2,
    steps: [
      {
        tool_name: "reading",
        detail: "Claims manual, section 9: Repeat claims",
      },
      {
        tool_name: "reading",
        detail: "Claims manual, section 9: Repeat claims",
      },
      { tool_name: "error", detail: "Timed out" },
      { tool_name: "error", detail: "Timed out again" },
    ],
  };
  vi.stubGlobal(
    "fetch",
    queueFetch((url) => {
      if (url.includes("/api/claims/CLM-1001")) return jsonResponse(left);
      return undefined;
    }),
  );
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Open claim CLM-1001" }),
  );
  expect(
    await screen.findByText(
      "This claim was left for a handler after two failed attempts.",
    ),
  ).toBeDefined();
  expect(screen.getByText("Left for a handler")).toBeDefined();
  expect(screen.getByText("Sections read")).toBeDefined();
  expect(
    screen.getAllByText("Claims manual, section 9: Repeat claims", {
      exact: true,
    }),
  ).toHaveLength(1);
  expect(
    screen.getAllByText("Read Claims manual, section 9: Repeat claims"),
  ).toHaveLength(2);
  expect(screen.getByText("Failed Timed out")).toBeDefined();
  expect(screen.getByText("Failed Timed out again")).toBeDefined();
});
