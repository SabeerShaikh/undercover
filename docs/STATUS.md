# Status

The claims pilot is running, with lookup of the policy wording and the claims manual.

- `backend/`: SQLite store seeded from `data/` into `undercover.db` (gitignored; override with `UNDERCOVER_DB`). Claims API for the queue, claim detail, policy wording, claims manual sections (`search_documents`, `read_section`), queue and claim instructions, decision, sign-off, pay, steps, start, failure (`left_for_handler` after two attempts), runs and to-do lists, and `POST /api/claims/{id}/run` to start the agent in a background thread. `uv run -m backend.seed` rebuilds the database.
- `agent/`: `run(claim_id, thread_id)` loads claim instructions from the API and decides through backend-only tools, including search and read of sections. Default model is DeepSeek V4.1 Flash. Stub-model tests cover approve/pay, over-limit sign-off, decline, and reading steps. `uv run -m agent` runs the agent on every waiting claim (backend must already be up).
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
