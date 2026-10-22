# Code standards

1. Keep it simple, do not overcomplicate.
2. Comments only when necessary.
3. Be concise: a short README and no emojis.
4. IMPORTANT: avoid overly defensive code. Handle exceptions only when necessary.
5. Use uv: ALWAYS `uv run`, NEVER `python3`.
6. TypeScript: strict mode, never `any`.
7. One module owns each external API. The base URL lives there, once. Callers use named functions, not raw paths or a second HTTP client.
8. The agent harness (`agent/harness.py`) is separate from its tools (`agent/tools.py`). Tools read run state from LangChain `ToolRuntime` context, not closures or module globals.
9. Agent instructions state a goal and the constraints. They are not a step-by-step script.
10. Code must be fit for a PR: no mixed-up modules, no duplicated clients, no hardcoded URLs scattered through the tree.
