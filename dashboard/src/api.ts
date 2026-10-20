import type { ClaimDetail, QueueClaim } from "./types";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed: ${String(response.status)}`);
  }
  return (await response.json()) as T;
}

export async function fetchClaims(): Promise<QueueClaim[]> {
  return readJson(await fetch("/api/claims"));
}

export async function fetchClaim(claimId: string): Promise<ClaimDetail> {
  return readJson(await fetch(`/api/claims/${claimId}`));
}

export interface InstructionsText {
  queue: string;
  claim: string;
}

export async function fetchInstructions(): Promise<InstructionsText> {
  return readJson<InstructionsText>(await fetch("/api/instructions"));
}

export async function signOffClaim(claimId: string): Promise<void> {
  await readJson(
    await fetch(`/api/claims/${claimId}/sign-off`, { method: "POST" }),
  );
}

export async function payClaim(claimId: string, amount: number): Promise<void> {
  await readJson(
    await fetch(`/api/claims/${claimId}/pay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount }),
    }),
  );
}

export async function startAgent(claimId: string): Promise<void> {
  await readJson(await fetch(`/api/claims/${claimId}/run`, { method: "POST" }));
}

export async function signOffAndPay(
  claimId: string,
  amount: number,
): Promise<void> {
  await signOffClaim(claimId);
  await payClaim(claimId, amount);
}
