# Process

`uv sync` and `npm install` at the repo root install everything, including a git pre-commit hook. `npm run dev` starts the backend and the dashboard.

`npm run check` runs every check:

- Python: ruff (lint and format), pyright, and pytest with 80% coverage
- TypeScript: ESLint, Prettier, tsc, and vitest with 80% coverage
- Playwright end-to-end tests

The pre-commit hook runs the format, lint, type and unit test checks on every commit.

## Planning

When asked to plan, as in "Please plan the pilot", write the plan to `docs/PLAN.md` and write no code.

- Split the work into phases, usually 5 or 6, each building on the last.
- Name the modules each phase will add or change, and which existing module owns any external API. Do not leave HTTP calls, tools, and run loops in one `main.py`.
- Give each phase detailed success criteria that you can verify yourself: tests that pass, commands and their output, API calls and their responses, and pages you check in the browser with the Playwright MCP server. Write each one as a checkbox.
- Then stop and wait until you are asked to implement the plan.

## Implementing

When asked to implement the plan, as in "Please implement the plan for the pilot", build every phase in order without stopping. For each phase:

1. Build it, with tests.
2. Check every success criterion and fix whatever fails.
3. Tick off its criteria in `docs/PLAN.md` and update `docs/STATUS.md`.
4. Commit. The pre-commit hook runs the checks; if it fails, fix the problem and commit again.

When the last phase is done, run `npm run check` and report the results.

## Structure

A passing test run is not enough. Before you plan or merge, check that the modules would survive a simple PR review.

- **One API module per service.** The agent talks to the backend only through `agent/api.py`. The dashboard talks to it only through `dashboard/src/api.ts`. Do not open HTTP clients or hardcode `/api/...` paths in tools, the harness, views, or `main.py`.
- **Harness, tools, and domain stay apart.** Cap, retries, missed claims, and failure handling live in `agent/harness.py`. Tools live in `agent/tools.py` and take `runtime: ToolRuntime[...]`. Do not close over claim ids or run ids, and do not grow `main.py` into a dumping ground.
- **Instructions are goals.** Write what the agent is for and the rules it must keep. Do not write a fixed workflow of "first do this, then that".
- **Look next door.** A messy pattern in the agent often has a twin in the backend or dashboard. Fix those in the same change.

The harness build put every URL, tool, and run loop in `agent/main.py` because the plan listed behavior, not module boundaries, and these rules were missing. Tests stayed green. That does not pass review.

## Rules

- Add tests with each change. Tests never call a model; use a stub model.
- Outside a plan, commit each change once you have checked it.
- Run `npm run check` before you hand work over.
- Never use `git commit --no-verify`.
- Never lower a threshold, turn off a rule or exclude a file to get a green run. If a rule looks wrong, stop and ask.
- Keep `docs/STATUS.md` up to date.
- Never push.
- Don't open `data/evals/` unless you're asked to.
- Everything must work on Windows: write `package.json` scripts as `uv run` commands or `.mjs` files.
