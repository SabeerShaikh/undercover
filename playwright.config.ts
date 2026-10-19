import path from "node:path";
import { defineConfig } from "@playwright/test";

const e2eDb = path.join(import.meta.dirname, "e2e", "undercover-e2e.db");

export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e/test-results",
  reporter: "list",
  use: { baseURL: "http://localhost:5173" },
  webServer: [
    {
      command: "uv run -m uvicorn backend.main:app --port 8000",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: false,
      env: { ...process.env, UNDERCOVER_DB: e2eDb },
    },
    {
      command: "npx vite dashboard --port 5173 --strictPort",
      url: "http://localhost:5173",
      reuseExistingServer: false,
    },
  ],
});
