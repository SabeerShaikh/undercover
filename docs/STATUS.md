# Status

The claims pilot is running, with lookup of the policy wording and the claims manual.

- `backend/`: SQLite store seeded from `data/` into `undercover.db` (gitignored; override with `UNDERCOVER_DB`). Claims API for the queue, claim detail, policy wording, claims manual sections (`search_documents`, `read_section`), queue and claim instructions, decision, sign-off, pay, steps, start, failure (`left_for_handler` after two attempts), runs and to-do lists, and `POST /api/claims/{id}/run` to start the agent in a background thread. `uv run -m backend.seed` rebuilds the database.
- `agent/`: `work_claim(claim_id)` starts a claim agent on a new thread with claim instructions only. It looks up sections through backend tools, records a one-line report from the claim record, and fails a claim that is still in progress with no decision (back to the queue once, then left for a handler). Default model is DeepSeek V4.1 Flash. `uv run -m agent CLM-1001` works one claim. `uv run -m agent` still loops waiting claims until the queue agent lands.
- `dashboard/`: branded queue, claim view (with run, steps, and sign-off), and read-only instructions for running the queue and working a claim. Light and dark surfaces follow `docs/BRAND.md`.
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
