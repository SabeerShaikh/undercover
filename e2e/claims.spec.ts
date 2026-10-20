import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:8000";

test("the queue lists claims including CLM-1001", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "UnderCover" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Open claim CLM-1001" }),
  ).toBeVisible();
  await expect(page.getByText("Maya Patel")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Claims by status" }),
  ).toBeVisible();
});

test("opening a claim shows its story and policy", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open claim CLM-1001" }).click();
  await expect(page.getByRole("heading", { name: "CLM-1001" })).toBeVisible();
  await expect(page.getByText(/Rome/i).first()).toBeVisible();
  await expect(page.getByText("Maya Patel", { exact: true })).toBeVisible();
  await expect(page.getByText(/UnderCover Premium/)).toBeVisible();
  await expect(page.getByText(/Airport hotel/)).toBeVisible();
});

test("instructions are visible and not editable", async ({ page, request }) => {
  const instructionsResponse = await request.get(`${API}/api/instructions`);
  const apiBody = (await instructionsResponse.json()) as {
    queue: string;
    claim: string;
  };
  await page.goto("/");
  await page.getByRole("button", { name: "Instructions" }).click();
  await expect(
    page.getByRole("heading", { name: "Running the queue" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Working a claim" }),
  ).toBeVisible();
  await expect(page.locator("textarea, input")).toHaveCount(0);
  await expect(page.locator("pre.instructions").first()).toContainText(
    apiBody.queue.slice(0, 40),
  );
  await expect(page.locator("pre.instructions").nth(1)).toContainText(
    apiBody.claim.slice(0, 40),
  );
});

test("sign-off pays a claim waiting for handler approval", async ({
  page,
  request,
}) => {
  const claimId = "CLM-1025";
  const decision = await request.post(`${API}/api/claims/${claimId}/decision`, {
    data: {
      decision: "approve",
      payout: 1500,
      reason: "E2E sign-off path.",
      policy_section: "Section 1",
    },
  });
  expect(decision.ok()).toBeTruthy();
  expect((await decision.json()) as { status: string }).toEqual({
    status: "waiting_for_sign_off",
  });

  await page.goto("/");
  await page.getByRole("button", { name: `Open claim ${claimId}` }).click();
  await expect(page.getByText("Waiting for sign-off")).toBeVisible();
  await page.getByRole("button", { name: "Sign off and pay" }).click();
  await expect(page.getByText("Decided")).toBeVisible();
  await expect(page.getByText(/paid \$1,500\.00/)).toBeVisible();
});
