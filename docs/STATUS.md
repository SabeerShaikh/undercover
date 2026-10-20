# Status

The claims pilot is running, with lookup of the policy wording and the claims manual.

- `backend/`: SQLite store seeded from `data/` into `undercover.db` (gitignored; override with `UNDERCOVER_DB`). Claims API for the queue, claim detail, policy wording, claims manual sections (`search_documents`, `read_section`), queue and claim instructions, decision, sign-off, pay, steps, start, failure (`left_for_handler` after two attempts), runs and to-do lists, and `POST /api/claims/{id}/run` to start the agent in a background thread. `uv run -m backend.seed` rebuilds the database.
- `agent/`: `run_queue(cap)` recovers stuck claims, then a queue agent lists waiting claims, writes a to-do list, and hands each one to `work_claim` on a new thread. The harness enforces the cap, reminds the queue agent of missed claims inside the cap, and reports each claim from the record. A failed claim goes back once, then is left for a handler. Default model is DeepSeek V4.1 Flash.
- `dashboard/`: branded queue, claim view (with run, steps, and sign-off), and read-only instructions for running the queue and working a claim. Light and dark surfaces follow `docs/BRAND.md`.
- `e2e/`: Playwright covers the queue, claim detail, instructions, and sign-off path (no model calls).

## How to run

```bash
npm run dev
```

Open http://localhost:5173. The backend is on http://127.0.0.1:8000.

With the backend running, work the queue from the terminal. Reseed first if you need a clean set of 25 waiting claims:

```bash
uv run -m backend.seed
uv run -m agent --cap 5
```

```bash
uv run -m agent
```

works every waiting claim. One named claim:

```bash
uv run -m agent CLM-1001
```

```bash
npm run check
```

Runs ruff, pyright, pytest, ESLint, Prettier, tsc, vitest, and Playwright.
