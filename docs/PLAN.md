# Pilot plan

Build the claims platform in `docs/SPEC.md`: a SQLite backend, a handler dashboard, and a first UnderCover Agent that decides claims from the policy wording.

The skeleton already has health checks, `run(claim_id, thread_id)`, and a one-page dashboard. This plan fills that in. It does not add sign-in, the claims manual, real payments, customer messages, or anything from a later brief.

## Approach

- **One SQLite file** the backend creates on startup and seeds from `data/` (claims, policies, customers, plans, company settings, `policy_wording.md`). Held-out files in `data/evals/` stay unused.
- **The backend owns all records.** The dashboard and the agent reach claims, wording and the agent's instructions only through its API. Paying a claim is its own operation and takes the amount. A payout over the company limit of $1,000.00 needs sign-off; the backend refuses to pay until then, even if the agent calls pay.
- **Claim status** is what handlers see: `waiting`, `in_progress`, `waiting_for_sign_off`, `decided`. Seeded claims start as `waiting` (the files say `open`).
- **The agent** stays LangChain `create_agent` on OpenRouter. Tools are backend calls. Tests pass a stub model; they never call OpenRouter.
- **The dashboard** is React on the existing Vite proxy. Queue, claim, and read-only instructions. Brand from `docs/BRAND.md`. While the agent works, the page polls steps the backend stored from tool calls.

SQLAlchemy is already in the `server` extra, but the pilot only needs SQLite. Use the stdlib `sqlite3` module so the default `uv sync` environment is enough.

## Phase 1 — Store and seed

Load UnderCover's records into SQLite so later phases have one place to read and write.

**Build**

- A small store module: open `undercover.db` (gitignored), create tables, seed once from `data/claims.json`, `policies.json`, `customers.json`, `plans.json`, `company.json` and `data/policy_wording.md`.
- Tables for claims (including working status, decision fields, sign-off and paid amount), policies, customers (with previous claims), plans, company, policy wording, agent instructions, and agent steps.
- Default instructions in the store, written so the agent decides from the wording, history and plan limits, explains in two or three sentences with the relevant section, and does not see `data/evals/`.
- Keep `GET /api/health`.

**Why this first.** The API, agent and screens all share the same records. Seeding here means later phases do not parse JSON files themselves.

**Success criteria**

- [x] `uv run pytest -q` passes, including new store tests.
- [x] A store test seeds from `data/` and lists 25 claims, all with status `waiting`.
- [x] A store test loads CLM-1001 with story, items, documents, policy POL-2001 (Premium, Rome trip) and customer Maya Patel's previous claims.
- [x] A store test reads the policy wording (non-empty markdown) and the payout approval limit `1000.0`.
- [x] Seeding a second time does not duplicate claims.
- [x] `undercover.db` is in `.gitignore`.

## Phase 2 — Backend API

Give handlers and the agent HTTP operations for the queue and a claim's life cycle. Every route has an `operation_id`, a one-line docstring and no optional inputs.

**Build**

| Operation | Role |
|---|---|
| `GET /api/claims` | Queue: each claim's id, summary, amount claimed, customer name, status |
| `GET /api/claims/{claim_id}` | Full claim: story, items, documents, policy, plan, customer and history, decision, payout, reasons, sign-off, paid amount, steps |
| `GET /api/policy-wording` | The contract text |
| `GET /api/instructions` | The agent's instructions (read only) |
| `POST /api/claims/{claim_id}/decision` | Record approve, decline or refer, with payout, a short reason and the policy section. Approve with payout over $1,000.00 sets `waiting_for_sign_off`; otherwise `decided` |
| `POST /api/claims/{claim_id}/sign-off` | Handler sign-off on a claim waiting for it |
| `POST /api/claims/{claim_id}/pay` | Pay a given amount. 409 if the claim is waiting for sign-off, already paid, or not approved |
| `POST /api/claims/{claim_id}/steps` | Append a step (tool name and detail) while the agent works |
| `POST /api/claims/{claim_id}/status` | Set `in_progress` when the agent starts (only from `waiting`) |

Money in JSON is numbers; the UI formats US dollars.

**Why this next.** The spec's rules live in the backend. The agent cannot pay a large claim by skipping the UI if pay itself enforces sign-off.

**Success criteria**

- [x] `uv run pytest -q` passes, including API tests with `TestClient`.
- [x] `GET /api/claims` returns 25 claims and includes CLM-1001 as waiting with amount `420.0`.
- [x] `GET /api/claims/CLM-1001` includes the story, documents, policy, plan limits and previous claims.
- [x] `GET /api/policy-wording` and `GET /api/instructions` return text.
- [x] Decline CLM-1001: status `decided`, pay returns 409.
- [x] Approve CLM-1001 for `420.0`, then pay `420.0`: status `decided`, paid amount `420.0`.
- [x] Approve CLM-1002 (claimed `1150.0`) for `1150.0`: status `waiting_for_sign_off`; pay returns 409; after sign-off, pay `1150.0` succeeds and status is `decided`.
- [x] `curl -s http://127.0.0.1:8000/api/health` → `{"status":"ok"}` with the backend running.

## Phase 3 — The UnderCover Agent

Replace the hello-world agent with one that works a claim the way a handler does.

**Build**

- Tools that only call the backend: read instructions, read a claim, read the policy wording, record a decision, pay, and write a step before/after each meaningful call (or have the tools write steps themselves).
- `run(claim_id, thread_id, llm=None)` sets the claim `in_progress`, loads instructions from the API (not a constant in the agent), invokes `create_agent`, and returns the final reply. Default model remains `openai/gpt-6-luna` with low reasoning effort, or `MODEL_NAME` when set.
- Drop the health-only tool and hello prompt.
- Stub-model tests: a path that approves and pays CLM-1001; a path that approves CLM-1002 over the limit, tries to pay, and leaves it waiting for sign-off; a path that declines. Backend client in tests is `TestClient`.

**Why this shape.** `TECH_STACK.md` keeps one entry point and forces the agent through the API, so it cannot open `data/evals/` or pay around the limit.

**Success criteria**

- [x] `uv run pytest -q` passes; agent tests never set a real `OPENROUTER_API_KEY` on the stub paths.
- [x] Stub run on CLM-1001: decision approve, paid `420.0`, status `decided`, steps recorded.
- [x] Stub run on CLM-1002 with payout `1150.0`: status `waiting_for_sign_off`, paid amount empty/zero, even if the scripted model calls pay.
- [x] `test_model_name` still checks default `openai/gpt-6-luna` and `MODEL_NAME=openrouter/free`.
- [x] Instructions the agent uses match `GET /api/instructions`.

## Phase 4 — Dashboard: queue and claim

Let handlers see the queue and a claim in full, including a decision when there is one.

**Build**

- App shell with UnderCover branding (Instrument Sans / Instrument Serif / JetBrains Mono, colors and surfaces from `docs/BRAND.md`, light and dark).
- Queue view: all claims with status waiting, in progress, waiting for sign-off, or decided. Sea Green, Marigold and Coral for three statuses side by side; Cerulean and Raspberry if a fourth and fifth are needed. Amounts as `$1,150.00`. Identifiers in JetBrains Mono.
- Claim view: story, items, documents, policy and plan, customer history, decision (approve / decline / refer), payout, two-or-three-sentence reason, policy section.
- Sign-off control on `waiting_for_sign_off` claims; it calls sign-off then pay for the approved amount.
- No sign-in. Keep `/api/health` available; the health-only home page goes away.

**Why UI after the API.** Screens stay dumb clients. Sign-off in the UI still hits the same pay rule as the agent.

**Success criteria**

- [x] `npx vitest run --root dashboard --coverage` passes at 80%.
- [x] `npm run dev`: open `/`, queue shows 25 claims including CLM-1001.
- [x] Open CLM-1001: story, hotel/meals/taxis items, documents, Maya Patel, Premium policy.
- [x] After a test decision on a claim, the claim view shows the decision and reason; the queue status updates.
- [x] Put CLM-1002 in `waiting_for_sign_off` via the API, open it, sign off in the browser; it becomes decided and paid.
- [x] Light and dark both use the brand surfaces (page `#F0F4F5` / `#04232E`, panels white / black, no top bar line).

## Phase 5 — Live work, run, and instructions

Show the agent working, let a handler start it, and show its instructions read-only.

**Build**

- Run control on a waiting claim: `POST` a backend start route that calls `agent.main.run` in a background thread (so the UI can poll). The start route is for the dashboard; tests inject the stub model the same way as unit tests, or the route accepts no model and tests cover `run` in pytest only while e2e drives state through the API.
- Claim view polls the claim while status is `in_progress` and lists steps in order (tool name and detail).
- Instructions view: the text from `GET /api/instructions`, read only. No editor.

**Why a backend start route.** The agent is a Python function. The dashboard should not spawn it. A thread plus polling is enough for the pilot; no extra queue product.

**Success criteria**

- [x] `uv run pytest -q` covers the start route with a stub model on CLM-1001 and ends `decided` and paid.
- [x] Vitest covers the run control, the step list, and the instructions view.
- [x] Browser: instructions view shows the same wording as `GET /api/instructions` and has no inputs.
- [x] Browser: start the agent on a waiting claim (stub or a short real run if a key is present); status becomes in progress, steps appear, then a decision.
- [x] Queue uses “in progress” while that run is live.

## Phase 6 — End-to-end checks and status

Lock the handler path with Playwright and leave the repo runnable.

**Build**

- Playwright specs (no model calls): queue lists claims; open a claim; instructions are visible and not editable; sign-off path for a claim placed in `waiting_for_sign_off` through the API.
- Replace the health-only e2e spec.
- Update `docs/STATUS.md`: what exists, how to run it (`npm run dev`), where the database lives.

**Success criteria**

- [x] `npx playwright test` passes.
- [x] `npm run check` passes (ruff, pyright, pytest 80%, ESLint, Prettier, tsc, vitest 80%, Playwright).
- [x] `docs/STATUS.md` matches the running app.
- [x] Windows-safe: scripts stay `uv run` / npm / `.mjs`; no Unix-only shell.

## Out of scope

- Claims manual in the agent's context
- Sign-in
- Real payments or customer messages
- Reading `data/evals/`
- Harness middleware, durable graphs, swarms, AWS (later briefs)
