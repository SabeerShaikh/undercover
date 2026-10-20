import { expect, test, type APIRequestContext } from "@playwright/test";

const API = "http://127.0.0.1:8000";

async function finishRunning(request: APIRequestContext): Promise<void> {
  const latest = (await (
    await request.get(`${API}/api/runs/latest`)
  ).json()) as {
    id: number;
    status: string;
  } | null;
  if (latest?.status === "running") {
    await request.post(`${API}/api/runs/${String(latest.id)}/finish`, {
      data: { summary: "Cleared for e2e." },
    });
  }
}

test("the queue follows a run's to-do list without a reload", async ({
  page,
  request,
}) => {
  await finishRunning(request);
  const started = await request.post(`${API}/api/runs`, { data: { cap: 2 } });
  expect(started.ok()).toBeTruthy();
  const run = (await (await request.get(`${API}/api/runs/latest`)).json()) as {
    id: number;
  };
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Latest run" });
  await expect(panel).toContainText("Running");
  await request.put(`${API}/api/runs/${String(run.id)}/todos`, {
    data: {
      todos: [
        { content: "Work CLM-1013", status: "to_do" },
        { content: "Work CLM-1014", status: "to_do" },
      ],
    },
  });
  await expect(panel.getByText("To do").first()).toBeVisible();
  await expect(panel.getByRole("button", { name: "CLM-1013" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "CLM-1014" })).toBeVisible();
  await request.put(`${API}/api/runs/${String(run.id)}/todos`, {
    data: {
      todos: [
        { content: "Work CLM-1013", status: "in_progress" },
        { content: "Work CLM-1014", status: "to_do" },
      ],
    },
  });
  await expect(panel.getByText("In progress")).toBeVisible();
  await request.put(`${API}/api/runs/${String(run.id)}/todos`, {
    data: {
      todos: [
        { content: "Work CLM-1013", status: "done" },
        { content: "Work CLM-1014", status: "done" },
      ],
    },
  });
  await expect(panel.getByText("Done").first()).toBeVisible();
  await request.post(`${API}/api/runs/${String(run.id)}/finish`, {
    data: { summary: "Two claims planned." },
  });
  await expect(panel).toContainText("Finished");
  await expect(panel).toContainText("Two claims planned.");
  await panel.getByRole("button", { name: "CLM-1013" }).click();
  await expect(page.getByRole("heading", { name: "CLM-1013" })).toBeVisible();
});

test("a failed claim shows readings and is left for a handler", async ({
  page,
  request,
}) => {
  const queue = (await (await request.get(`${API}/api/claims`)).json()) as {
    claim_id: string;
    status: string;
  }[];
  const waiting = queue.filter((claim) => claim.status === "waiting");
  expect(waiting.length).toBeGreaterThan(0);
  const claimId = waiting[0].claim_id;
  await page.goto("/");
  await page.getByRole("button", { name: `Open claim ${claimId}` }).click();
  await expect(page.getByRole("heading", { name: claimId })).toBeVisible();
  expect(
    (await request.post(`${API}/api/claims/${claimId}/start`)).ok(),
  ).toBeTruthy();
  expect(
    (
      await request.post(`${API}/api/claims/${claimId}/steps`, {
        data: {
          tool_name: "reading",
          detail: "Claims manual, section 9: Repeat claims",
        },
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await request.post(`${API}/api/claims/${claimId}/failure`, {
        data: { reason: "The model timed out" },
      })
    ).ok(),
  ).toBeTruthy();
  await expect(
    page.getByText("This claim came back after a failed attempt."),
  ).toBeVisible();
  expect(
    (await request.post(`${API}/api/claims/${claimId}/start`)).ok(),
  ).toBeTruthy();
  expect(
    (
      await request.post(`${API}/api/claims/${claimId}/failure`, {
        data: { reason: "The model timed out again" },
      })
    ).ok(),
  ).toBeTruthy();
  await expect(
    page.getByText("Left for a handler", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Claims manual, section 9: Repeat claims", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Read Claims manual, section 9: Repeat claims"),
  ).toBeVisible();
  await expect(
    page.getByText("Failed The model timed out", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Failed The model timed out again", { exact: true }),
  ).toBeVisible();
});
