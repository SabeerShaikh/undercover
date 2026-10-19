import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import type { ClaimDetail, QueueClaim } from "./types";

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
    customer_name: "Maya Patel",
  },
  {
    claim_id: "CLM-1002",
    summary: "Suitcase lost",
    amount_claimed: 1150,
    status: "waiting_for_sign_off",
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

it("shows the claims queue", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(queue)));
  render(<App />);
  expect(await screen.findByText("CLM-1001")).toBeDefined();
  expect(screen.getByText("Maya Patel")).toBeDefined();
  expect(screen.getByText("$420.00")).toBeDefined();
  expect(screen.getByText("Waiting")).toBeDefined();
});

it("opens a claim with story, items, documents and policy", async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = requestUrl(input);
    if (url.endsWith("/api/claims"))
      return Promise.resolve(jsonResponse(queue));
    if (url.includes("/api/claims/CLM-1001")) {
      return Promise.resolve(jsonResponse(claim1001));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "CLM-1001" }));
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
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/claims") && method === "GET") {
      return Promise.resolve(jsonResponse(queue));
    }
    if (url.includes("/sign-off")) {
      current = { ...current, signed_off: true };
      return Promise.resolve(jsonResponse({ status: "signed_off" }));
    }
    if (url.includes("/pay")) {
      current = {
        ...current,
        status: "decided",
        paid_amount: 1150,
      };
      return Promise.resolve(jsonResponse({ status: "paid" }));
    }
    if (url.includes("/api/claims/CLM-1002")) {
      return Promise.resolve(jsonResponse(current));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "CLM-1002" }));
  expect(await screen.findByText("Covered baggage loss.")).toBeDefined();
  expect(screen.getByText("approve")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Sign off and pay" }));
  await waitFor(() => {
    expect(screen.getByText(/paid \$1,150\.00/)).toBeDefined();
  });
});

it("starts the agent on a waiting claim", async () => {
  let current: ClaimDetail = claim1001;
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/claims"))
      return Promise.resolve(jsonResponse(queue));
    if (url.endsWith("/run") && method === "POST") {
      current = {
        ...current,
        status: "in_progress",
        steps: [{ tool_name: "get_claim", detail: "Read claim CLM-1001" }],
      };
      return Promise.resolve(jsonResponse({ status: "started" }));
    }
    if (url.includes("/api/claims/CLM-1001")) {
      return Promise.resolve(jsonResponse(current));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "CLM-1001" }));
  fireEvent.click(await screen.findByRole("button", { name: "Run agent" }));
  expect(await screen.findByText("In progress")).toBeDefined();
  expect(screen.getByText(/get_claim/)).toBeDefined();
});

it("shows read-only instructions", async () => {
  const text = "You are the UnderCover Agent.";
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = requestUrl(input);
    if (url.endsWith("/api/claims"))
      return Promise.resolve(jsonResponse(queue));
    if (url.endsWith("/api/instructions")) {
      return Promise.resolve(jsonResponse({ text }));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Instructions" }));
  expect(await screen.findByText(text)).toBeDefined();
  expect(screen.queryByRole("textbox")).toBeNull();
});
