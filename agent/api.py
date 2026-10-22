"""HTTP calls to the UnderCover backend. The base URL lives here, once."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

import httpx

BACKEND_URL = "http://localhost:8000"


def client() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def _get(path: str, **kwargs: Any) -> httpx.Response:
    with client() as http:
        return http.get(path, **kwargs)


def _post(path: str, **kwargs: Any) -> httpx.Response:
    with client() as http:
        return http.post(path, **kwargs)


def _put(path: str, **kwargs: Any) -> httpx.Response:
    with client() as http:
        return http.put(path, **kwargs)


def _ok(response: httpx.Response) -> Any:
    response.raise_for_status()
    return response.json()


def as_json(response: httpx.Response) -> str:
    """Return the body as JSON, or a refused payload when the backend rejects it."""
    if response.status_code >= HTTPStatus.BAD_REQUEST:
        return json.dumps({"status": "refused", "detail": response.json()})
    return json.dumps(response.json())


def list_claims() -> list[dict[str, Any]]:
    """List claims in the queue."""
    return _ok(_get("/api/claims"))


def get_claim(claim_id: str) -> dict[str, Any]:
    """Return one claim with policy, customer, decision and steps."""
    return _ok(_get(f"/api/claims/{claim_id}"))


def instructions() -> dict[str, str]:
    """Return the queue and claim agent instructions."""
    return _ok(_get("/api/instructions"))


def claim_instructions() -> str:
    """Return the claim agent's instructions."""
    return instructions()["claim"]


def queue_instructions() -> str:
    """Return the queue agent's instructions."""
    return instructions()["queue"]


def search_documents(query: str) -> httpx.Response:
    """Search the policy wording and claims manual."""
    return _get("/api/documents/search", params={"query": query})


def read_section(document: str, number: int) -> httpx.Response:
    """Read one numbered section of the wording or the manual."""
    return _get(f"/api/documents/{document}/sections/{number}")


def record_decision(
    claim_id: str, decision: str, payout: float, reason: str, policy_section: str
) -> httpx.Response:
    """Record approve, decline or refer on a claim."""
    return _post(
        f"/api/claims/{claim_id}/decision",
        json={
            "decision": decision,
            "payout": payout,
            "reason": reason,
            "policy_section": policy_section,
        },
    )


def pay_claim(claim_id: str, amount: float) -> httpx.Response:
    """Pay an approved claim for the given amount."""
    return _post(f"/api/claims/{claim_id}/pay", json={"amount": amount})


def add_step(claim_id: str, tool_name: str, detail: str) -> None:
    """Append a step while the agent works a claim."""
    _ok(
        _post(
            f"/api/claims/{claim_id}/steps",
            json={"tool_name": tool_name, "detail": detail},
        )
    )


def start_claim(claim_id: str) -> httpx.Response:
    """Start work on a waiting claim."""
    return _post(f"/api/claims/{claim_id}/start")


def fail_claim(claim_id: str, reason: str) -> httpx.Response:
    """Record a failed attempt on a claim in progress."""
    return _post(f"/api/claims/{claim_id}/failure", json={"reason": reason})


def start_run(cap: int) -> dict[str, Any]:
    """Start a queue run with an empty to-do list."""
    return _ok(_post("/api/runs", json={"cap": cap}))


def write_todos(run_id: int, todos: list[dict[str, str]]) -> httpx.Response:
    """Replace the to-do list of a running run."""
    return _put(f"/api/runs/{run_id}/todos", json={"todos": todos})


def finish_run(run_id: int, summary: str) -> None:
    """Finish a running run with a summary for the handlers."""
    _ok(_post(f"/api/runs/{run_id}/finish", json={"summary": summary}))
