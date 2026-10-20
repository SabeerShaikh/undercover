"""Run the UnderCover Agent: uv run -m agent [--cap N] [CLM-1001]."""

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
    """Work one named claim, or run the queue, optionally capped."""
    parser = argparse.ArgumentParser(description="Run the UnderCover Agent.")
    parser.add_argument("claim", nargs="?", help="Work this claim only")
    parser.add_argument(
        "--cap",
        type=int,
        help="Maximum number of claims this queue run may start",
    )
    args = parser.parse_args(argv)

    try:
        if args.claim:
            print(main.work_claim(args.claim))
            return 0
        main.run_queue(args.cap)
        return 0
    except (httpx.HTTPError, OSError) as exc:
        print(
            "Could not reach the backend at http://localhost:8000.\n"
            "Start it first with: npm run dev\n"
            f"({exc})",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
