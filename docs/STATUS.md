# Status

Pilot through Phase 3: store, API and agent.

- `backend/`: SQLite store seeded from `data/`, health route, and claims API (queue, claim, wording, instructions, decision, sign-off, pay, steps, status)
- `agent/`: `run(claim_id, thread_id)` with tools that call the backend only; stub-model tests for approve/pay, over-limit sign-off, and decline
- `dashboard/`: still the skeleton health page (Phase 4 next)
- Database: `undercover.db` at the repo root (gitignored), created on backend start

Run the API and skeleton UI with `npm run dev`.
