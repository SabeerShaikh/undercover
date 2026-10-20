"""Run the UnderCover Agent: uv run -m agent [CLM-1001]."""

from __future__ import annotations

import argparse
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


def main_cli(argv: list[str] | None = None) -> int:
    """Work one named claim, or every waiting claim."""
    parser = argparse.ArgumentParser(description="Run the UnderCover Agent.")
    parser.add_argument("claim", nargs="?", help="Work this claim only")
    args = parser.parse_args(argv)

    try:
        if args.claim:
            print(main.work_claim(args.claim))
            return 0
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
        print(main.work_claim(claim_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
