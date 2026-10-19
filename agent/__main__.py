"""Run the UnderCover Agent on waiting claims: uv run -m agent."""

from __future__ import annotations

import sys

import httpx

from agent import main


def waiting_claim_ids() -> list[str]:
    """Return claim ids that are still waiting in the queue."""
    with main.backend() as client:
        response = client.get("/api/claims")
    response.raise_for_status()
    claims = response.json()
    return [claim["claim_id"] for claim in claims if claim["status"] == "waiting"]


def main_cli() -> int:
    """Process every waiting claim through the agent."""
    try:
        claim_ids = waiting_claim_ids()
    except (httpx.HTTPError, OSError) as exc:
        print(
            "Could not reach the backend at http://localhost:8000.\n"
            "Start it first with: npm run dev\n"
            f"({exc})",
            file=sys.stderr,
        )
        return 1

    if not claim_ids:
        print("No waiting claims.")
        return 0

    print(f"Running the agent on {len(claim_ids)} waiting claim(s).")
    for claim_id in claim_ids:
        print(f"\n=== {claim_id} ===")
        try:
            reply = main.run(claim_id, f"cli-{claim_id}")
            print(reply)
        except (httpx.HTTPError, OSError, RuntimeError, ValueError, KeyError) as exc:
            print(f"Failed on {claim_id}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
