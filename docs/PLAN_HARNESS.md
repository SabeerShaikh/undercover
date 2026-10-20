# Harness plan

Build what `docs/HARNESS.md` asks for on top of the pilot. `docs/PLAN.md` stays as it is.

When this is done, one command works the queue. A queue agent plans the run as a to-do list the team can watch, and hands each claim to a fresh claim agent that looks up the sections it needs. The harness, not the model, catches a failed claim, puts it back once, and leaves it for a handler after a second failure. The backend still enforces every rule in `docs/SPEC.md`, including sign-off over $1,000.

We build this with LangChain `create_agent` and our own tools. Deep Agents and the Claude Agent SDK stay out of `agent/` and `backend/`.

## How a run works

1. `uv run -m agent --cap 5` puts back any claim an earlier run left `in_progress`, then starts a run of at most five claims. With no cap, the run may work every waiting claim.
2. The queue agent lists the waiting claims, chooses the order, and writes a to-do list.
3. For each claim it calls `work_claim`. The harness starts a claim agent on a new thread with only the claim instructions. That agent decides the claim. The harness then returns one line taken from the claim record: the decision and payout, or what went wrong. The model's own last sentence is not the report.
4. The queue agent updates the to-do list from those lines, and tries again any claim that went back to waiting.
5. When the queue agent replies without calling a tool, the harness looks for waiting claims still inside the cap: a claim this run already started that came back, and any waiting claim while the run is under its cap. If it finds any, it names them and lets the agent continue. It does this at most twice, then the run ends.
6. The agent's last reply is the summary for the handlers. The harness stores it and prints it.

`uv run -m agent CLM-1001` still works one named claim, with the claim agent alone and no queue run. The dashboard's Run agent button does the same.

## Why the harness owns the hard parts

The pilot's Python loop already picks claims and feeds each one the whole wording. Moving that loop into a prompt would look like a queue agent and still fail the brief: a model can ignore a cap, skip a claim, and invent the line it reports back.

So:

- **The cap is a tool rule.** `work_claim` refuses a new claim once this run has started as many claims as its cap, and the refusal names the cap. Trying a claim again does not count as a new claim.
- **The missed-claim check is code.** It runs when the queue agent tries to stop, so a summary cannot hide a claim the cap still allows.
- **The one-line report is the claim record.** `CLM-1001  approve  $420.00`. An approval over $1,000 ends `waiting for sign-off`. A failure ends `back in the queue` or `left for a handler`. A claim that was not waiting ends `not started`.
- **A failure is one place.** `work_claim` catches a provider error, a tool error, a step limit, and an agent that finishes with no decision. If the claim is still `in_progress` and has no decision, it calls `fail_claim`. A claim that already has a decision keeps it and is not tried again.

## Claim states

| State | Meaning | On screen |
|---|---|---|
| `waiting` | Not started, or back after one failed attempt | Waiting |
| `in_progress` | A claim agent is working it | In progress |
| `waiting_for_sign_off` | Approved over $1,000; payment held | Waiting for sign-off |
| `decided` | Approved within the limit, declined, referred, or signed off and paid | Decided |
| `left_for_handler` | Failed twice, so a handler works it by hand | Left for a handler |

`left_for_handler` is not a referral and not a sign-off. A referral is a decision. Sign-off is an approval waiting to be paid.

`start_claim` adds one to `attempts`. The second failed attempt sets `left_for_handler`. The limit of two is a named constant in the backend. A claim with a decision is never put back in the queue. `pay` still refuses a second payment, and `record_decision` refuses a second decision.

## Runs and the to-do list

A run has an id, a cap, a status (`running` or `finished`), a start time, a finish time, and a summary. One run is `running` at a time.

Its to-do list is an ordered list of items. Each item has text and a status: `to_do`, `in_progress`, `done`, or `left_for_handler`. `write_todos` replaces the whole list. The queue page shows the latest run's list, so the team can see what the agent means to do.

On screen those four statuses use Cerulean, Marigold, Sea Green, and Raspberry. The same four colors already mark claim states; the to-do list reuses them so "in progress" and "left for a handler" mean the same thing in both places.

## Looking up the wording and the manual

Both documents are split on their numbered headings (`## 3. Trip Delay`): 12 sections in the wording, 14 in the manual. A section is a document name (`policy_wording` or `claims_manual`) plus a number.

The claim agent is not given either document in full. Its instructions end with the contents only: number and title. It searches with `search_documents` and reads one section with `read_section`. After a successful read, the harness records a step the claim page can show, such as `Claims manual, section 9: Repeat claims`.

## Instructions

Two files, seeded into the store and shown read-only: `backend/instructions/queue.md` and `backend/instructions/claim.md`. Written from the wording and the manual. Never from `data/evals/`.

- **Queue.** Run the queue. Do not decide a claim yourself. Choose waiting claims up to the cap, oldest submitted first. Keep one to-do item per claim, plus a check for missed claims and the summary. Mark an item in progress before handing the claim over, and done or left for a handler when the report comes back. Try again a claim whose report says it is back in the queue. Finish with a short summary: how many of each decision, payouts waiting for sign-off, and claims left for a handler.
- **Claim.** The wording is the contract. The manual says how to read it, including a third claim within 12 months, wild animals, and meals without receipts. Read the sections the claim needs. Refer for the manual's reasons as well as the wording's. The recorded section names what was relied on. Explain in two or three sentences.

The contents list is generated from the headings at seed time, so the prompt cannot drift from the files.

## API

Existing claim, decision, pay, sign-off, and step routes stay. Every operation keeps an `operation_id`, a one-line docstring, and no optional inputs.

| Operation | Route | What it does |
|---|---|---|
| `search_documents` | `GET /api/documents/search?query=` | Sections whose title or text contains the query, with the matching paragraphs |
| `read_section` | `GET /api/documents/{document}/sections/{number}` | One section: document, number, title, text |
| `get_instructions` | `GET /api/instructions` | `{queue, claim}`. `claim` ends with the contents, not the section text |
| `start_claim` | `POST /api/claims/{claim_id}/start` | From `waiting` only. Sets `in_progress` and adds one attempt |
| `fail_claim` | `POST /api/claims/{claim_id}/failure` | Body `{reason}`. Needs `in_progress` and no decision. Records an error step, then `waiting` or, on the second attempt, `left_for_handler` |
| `start_run` | `POST /api/runs` | Body `{cap}`. Cap at least 1. 409 if a run is already running. Empty to-do list |
| `get_latest_run` | `GET /api/runs/latest` | Newest run and its list, or `null` |
| `write_todos` | `PUT /api/runs/{run_id}/todos` | Body `{todos: [{content, status}]}`. Replaces the list of a running run |
| `finish_run` | `POST /api/runs/{run_id}/finish` | Body `{summary}`. Marks the run finished |

`read_section` returns 404 for a missing number and 422 for any other document name. `search_documents` returns 422 for an empty query and `[]` when nothing matches. `fail_claim` returns 409 unless the claim is `in_progress` with no decision. `write_todos` returns 422 for an empty item or a status outside the four above.

`uv run -m backend.seed` deletes the SQLite file and lets the next startup seed it again. A decided claim is final, so a live rerun reseeds first.

## The two agents

**Model.** `deepseek/deepseek-v4.1-flash` at low reasoning effort, or `MODEL_NAME` when set. Each model call waits at most 120 seconds and retries up to 5 times, so a timeout or a provider error is usually handled before it fails the claim.

**Claim agent.** `work_claim(claim_id)` calls `start_claim`, loads the `claim` instructions, and runs `create_agent` on a new thread. Tools, each a backend operation: `get_claim`, `search_documents`, `read_section`, `record_decision`, `pay_claim`. A reading step is recorded by the harness when `read_section` succeeds. LangGraph's recursion limit stops an agent that loops; that stop is a failure. If `start_claim` refuses, the report says `not started` and nothing is recorded.

**Queue agent.** `run_queue(cap)` runs `create_agent` with `list_claims`, `write_todos`, and `work_claim`. The run id is its thread id. Its first message states the cap. If the queue agent itself raises, the harness finishes the run with a summary that starts `The run stopped:` and leaves no claim `in_progress`.

**Command line.** `uv run -m agent` works every waiting claim. `uv run -m agent --cap 5` caps the run. `uv run -m agent CLM-1001` works that claim. No waiting claims prints `No claims are waiting` and starts no run.

Tests pass a stub model. The queue tests and the claim tests use separate stubs. Tests never call OpenRouter.

## Dashboard

- **Queue.** A tile for Left for a handler. Above the table, the latest run: cap, Running or Finished, the to-do list, and the summary once it is finished. A claim id in an item opens that claim. Before the first run the panel says `No run yet`. It refreshes with the queue, every two seconds. The queue run is started from the command line; the page is for watching it.
- **Claim.** If the claim came back after one failure, say so. If it was left for a handler, say so. List each section read once, then the steps. A reading step shows Read and the section. An error step shows Failed and the reason.
- **Instructions.** Two read-only panels: Running the queue, and Working a claim.

Playwright drives the pages through the API, with no model calls. Browser checks use the Playwright MCP server at `http://localhost:5173`. Anything marked Live uses the default model after `uv run -m backend.seed`, and works at most five claims.

## Phase 1 — Lookup and instructions

Seed the manual, add search and read, write both instruction files, and point the claim agent at sections instead of the whole wording. Switch the default model. Update `docs/SPEC.md` so the manual is in scope.

**Why first.** The claim agent cannot work "the way a handler would" until a section is something the API can return. The later phases only add the queue around that.

- [x] `curl -s localhost:8000/api/documents/claims_manual/sections/9` returns number 9, title `Repeat claims`, and text that starts `Before deciding any claim`.
- [x] `curl -s localhost:8000/api/documents/policy_wording/sections/3` returns `Trip Delay` and nothing from Baggage Delay.
- [x] Section 13 of the wording and section 15 of the manual return 404. A document named `handbook` returns 422.
- [x] `curl -s "localhost:8000/api/documents/search?query=wild%20animal"` returns manual section 7, `Interpretation notes`, including the wild-animals paragraph. `GIRAFFE` finds that same section. `zeppelin` returns `[]`. An empty query returns 422.
- [x] pytest checks the split: 12 wording sections and 14 manual sections, with numbers and titles.
- [x] `GET /api/instructions` returns `queue` and `claim`. `claim` ends with the contents, including `3. Trip Delay` and `9. Repeat claims`, and does not contain `Unattended means out of your sight` or `Monkeys, gulls, bears, giraffes`.
- [x] A stub run reads manual section 9. The claim's steps include `Claims manual, section 9: Repeat claims`. A read of section 15 comes back as a refusal and records no reading step.
- [x] `test_model_name`: default `deepseek/deepseek-v4.1-flash` with low reasoning effort, a 120 second timeout, and 5 retries. `MODEL_NAME=openrouter/free` overrides the name.
- [x] Browser, instructions: headings `Running the queue` and `Working a claim`, no text box and no edit button.
- [x] `docs/SPEC.md` says decisions follow the wording and the manual, and the manual is gone from "Not for now".
- [x] `npm run check` passes.

## Phase 2 — Runs, attempts, and failures

Add `attempts`, `left_for_handler`, `fail_claim`, and the run with its to-do list. The queue learns the new state. Add `uv run -m backend.seed`.

**Why before the queue agent.** The cap, the retries, and the list the dashboard shows are records. The agent should call them, not invent them.

- [x] pytest covers each new 404, 409, and 422 in the API section above.
- [x] `start_claim` on CLM-1004 sets attempts to 1. `fail_claim` with `The model timed out` sets `waiting`, attempts stay 1, and the last step is that reason.
- [x] Starting and failing it again sets `left_for_handler` and attempts 2. Another `start_claim` returns 409.
- [x] `fail_claim` on a waiting claim, a decided claim, and a claim waiting for sign-off each return 409 and change nothing.
- [x] A second `record_decision` on a decided claim returns 409. A second pay still returns `already_paid`.
- [x] On a fresh database, `GET /api/runs/latest` is `null`.
- [x] `start_run` with cap 5 returns a running run, an empty list, and a start time. Cap 0 returns 422. A second `start_run` while it is running returns 409.
- [x] `write_todos` with two items, then three, leaves exactly those three in order. Status `blocked` returns 422. An empty item returns 422. An unknown run returns 404.
- [x] `finish_run` sets `finished`, a finish time, and the summary. Further todo writes return 409.
- [x] vitest: the queue shows a Left for a handler tile.
- [x] `uv run -m backend.seed` against a copy of the database leaves 25 waiting claims on the next startup.
- [x] `npm run check` passes.

## Phase 3 — A fresh claim agent

Turn the pilot's `run` into `work_claim(claim_id)`: a new thread each attempt, the step limit, failure handling, and the one-line report. `uv run -m agent CLM-1001` prints that line.

**Why a new thread.** Each claim starts with the instructions and one message. The queue's growing list of reports never enters the claim agent's context, so a later claim costs the same as the first.

- [x] Stub, within the limit: `work_claim("CLM-1001")` returns `CLM-1001  approve  $420.00`. The claim is decided and paid.
- [x] Stub, over the limit: the report for CLM-1002 ends `waiting for sign-off`, and nothing is paid.
- [x] A stub that raises on its second call: the report ends `back in the queue`. The claim is `waiting`, attempts 1, and the last step is the error.
- [x] The same failure again: the report ends `left for a handler`, and the claim is `left_for_handler`.
- [x] A stub that finishes without a decision: the report says the agent finished without recording a decision, and the claim is back in the queue.
- [x] A stub that calls `get_claim` in a loop stops at the step limit and the claim goes back to waiting.
- [x] A stub that raises after `record_decision`: the report gives the decision, the claim keeps it, and it is not put back.
- [x] `work_claim` on a decided claim returns `not started` and adds no step and no attempt.
- [x] Working two claims in a row, the claim model's first prompt each time holds only the claim instructions and one message naming that claim.
- [x] `uv run -m agent CLM-1001` prints the report, with `work_claim` stubbed in that test.
- [x] Live, after a reseed: `uv run -m agent CLM-1001` prints one report line. The claim API shows the same decision and payout, a reason of two or three sentences, and at least one reading step.
- [x] `npm run check` passes.

## Phase 4 — The queue agent

Replace the Python loop with `run_queue(cap)`: recovery of stuck claims, the three tools, the cap, the missed-claim check, and the summary. Add `--cap`.

**Why the check is outside the model.** The brief says the agent must not miss a waiting claim inside its cap. A reminder injected when it tries to finish is something a test can force. A sentence in the prompt is not.

- [ ] The queue agent's tools are exactly `list_claims`, `write_todos`, and `work_claim`.
- [ ] Stub run of three waiting claims: it lists them, writes the list, marks each item in progress and then done around `work_claim`, and finishes with a summary. All three are decided. The latest run is `finished` with that summary and every item `done`. The first message states the cap.
- [ ] Cap 2 with four waiting: `work_claim` on a third new claim is refused and the refusal names the cap. Two claims are worked. The other two stay `waiting` with 0 attempts.
- [ ] The claim model raises on the first of three claims. The other two are still decided and the run finishes.
- [ ] A claim that fails once is `waiting`. The stub calls `work_claim` on it again, which the cap allows, and it is decided. Its steps show both attempts with the error between them.
- [ ] A claim that fails both attempts is `left_for_handler`. The report says so. The other claims in the run are still decided.
- [ ] The stub tries to finish while a claim it started is back in the queue. The harness names that claim. The stub works it, then the run finishes. A stub that ignores the reminder gets two, then the run finishes anyway.
- [ ] A claim left `in_progress` before the run starts goes back to the queue with the reason `The run stopped before this claim was finished`, and this run can work it.
- [ ] If the queue model raises, the run finishes with a summary starting `The run stopped:`, and no claim is `in_progress`.
- [ ] With nothing waiting, `run_queue` prints `No claims are waiting` and starts no run.
- [ ] `uv run -m agent` uses every waiting claim, `--cap 5` uses five, and `CLM-1001` works one claim. Tested with the run stubbed.
- [ ] Live, after a reseed, with `npm run dev` up: `uv run -m agent --cap 5` prints a report line per claim it works, then the summary.
- [ ] Live: exactly five claims are no longer `waiting`, and none are `in_progress`. The latest run is `finished`. Every approval over $1,000 is unpaid and waiting for sign-off. Every other approval is paid its payout. Each claim worked has at least one reading step.
- [ ] `npm run check` passes.

## Phase 5 — The queue page and the claim page

Show the run, the to-do list, a claim left for a handler, and the sections the agent read.

**Why the page only watches.** Handlers need to see the plan fill in. Starting the queue from the page would add a second way to launch a run that spends money. The command line is the start; the page follows the records.

- [ ] vitest covers the run panel before the first run, while running, and when finished with a summary; a claim id in an item opening that claim; a claim back in the queue; a claim left for a handler; and the sections read, each once.
- [ ] Playwright: start a run capped at 2 and write two to-do items naming CLM-1013 and CLM-1014. Without a reload, the queue shows both as To do, then follows them to In progress and Done. After the test finishes the run, the page shows Finished and the summary. The CLM-1013 link opens that claim.
- [ ] Playwright: start CLM-1016, record a reading step, and fail it. The claim page says it is back in the queue. Fail it again. The page shows Left for a handler, the section under sections read, and two Failed steps, without a reload.
- [ ] Browser: each to-do status and Left for a handler use the colors in the states section. Light and dark keep the brand surfaces: page `#F0F4F5` / `#04232E`, white / black panels, no outline and no bar across the top.
- [ ] Browser: a reading step shows Read and the section. A failed step shows Failed and its reason.
- [ ] `npm run check` passes.

## Phase 6 — A trial on five claims

Watch one capped run on the dashboard, and update `docs/SPEC.md`, `docs/TECH_STACK.md`, and `docs/STATUS.md`.

- [ ] Live, in the browser, after a reseed, with `/` open: start `uv run -m agent --cap 5`. During the run the to-do list appears, items move from To do to In progress to Done, and claims leave In progress, without a reload. The page ends on Finished and the summary.
- [ ] Live: a claim opened during the run shows its steps and at least one section of the manual.
- [ ] Live: afterwards the queue shows 20 waiting and none in progress.
- [ ] `docs/SPEC.md` describes the run, the to-do list, a fresh claim agent, retries, claims left for a handler, and the sections read.
- [ ] `docs/TECH_STACK.md` names DeepSeek V4.1 Flash and the two entry points, `run_queue(cap)` and `work_claim(claim_id)`.
- [ ] `docs/STATUS.md` says how to reseed, how to work the queue, a capped run, and one claim.
- [ ] `npm run check` passes.

## Not in this plan

- Scoring claims against `data/evals/`.
- A handler deciding a claim that was left for them, or putting it back, from the dashboard. Reseeding resets the queue.
- Starting the queue run from the dashboard.
- More than one run at a time, or working claims in parallel.
- Sign-in, real payments, and messages to customers.
