# Status

The claims pilot is running.

- `backend/`: SQLite store seeded from `data/` into `undercover.db` (gitignored; override with `UNDERCOVER_DB`). Claims API for the queue, claim detail, policy wording, agent instructions, decision, sign-off, pay, steps, status, and `POST /api/claims/{id}/run` to start the agent in a background thread.
- `agent/`: `run(claim_id, thread_id)` loads instructions from the API and decides through backend-only tools. Stub-model tests cover approve/pay, over-limit sign-off, and decline. `uv run -m agent` runs the agent on every waiting claim (backend must already be up).
- `dashboard/`: branded queue, claim view (with run, steps, and sign-off), and read-only instructions. Light and dark surfaces follow `docs/BRAND.md`.
- `e2e/`: Playwright covers the queue, claim detail, instructions, and sign-off path (no model calls).

## How to run

```bash
npm run dev
```

Open http://localhost:5173. The backend is on http://127.0.0.1:8000.

With the backend running, process every waiting claim from the terminal:

```bash
uv run -m agent
```

```bash
npm run check
```

Runs ruff, pyright, pytest, ESLint, Prettier, tsc, vitest, and Playwright.
