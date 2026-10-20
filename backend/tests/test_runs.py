"""Tests for attempts, failures, and queue runs."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main, seed, store


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    connection = store.init_db(tmp_path / "runs.db")
    monkeypatch.setattr(main, "db", connection)
    with TestClient(main.app) as test_client:
        yield test_client
    connection.close()


def test_start_and_fail_then_leave_for_handler(client: TestClient):
    first = client.post("/api/claims/CLM-1004/start")
    assert first.status_code == 200
    assert first.json()["attempts"] == 1
    fail = client.post(
        "/api/claims/CLM-1004/failure",
        json={"reason": "The model timed out"},
    )
    assert fail.status_code == 200
    assert fail.json()["status"] == "waiting"
    claim = client.get("/api/claims/CLM-1004").json()
    assert claim["status"] == "waiting"
    assert claim["attempts"] == 1
    assert claim["steps"][-1]["tool_name"] == "error"
    assert "timed out" in claim["steps"][-1]["detail"]

    client.post("/api/claims/CLM-1004/start")
    fail2 = client.post(
        "/api/claims/CLM-1004/failure",
        json={"reason": "The model timed out"},
    )
    assert fail2.json()["status"] == "left_for_handler"
    claim = client.get("/api/claims/CLM-1004").json()
    assert claim["status"] == "left_for_handler"
    assert claim["attempts"] == 2
    assert client.post("/api/claims/CLM-1004/start").status_code == 409
    listed = client.get("/api/claims").json()
    row = next(item for item in listed if item["claim_id"] == "CLM-1004")
    assert row["status"] == "left_for_handler"


def test_fail_claim_wrong_state(client: TestClient):
    waiting = client.post("/api/claims/CLM-1001/failure", json={"reason": "nope"})
    assert waiting.status_code == 409
    client.post(
        "/api/claims/CLM-1001/decision",
        json={
            "decision": "decline",
            "payout": 0,
            "reason": "No.",
            "policy_section": "Section 9",
        },
    )
    decided = client.post("/api/claims/CLM-1001/failure", json={"reason": "nope"})
    assert decided.status_code == 409
    client.post(
        "/api/claims/CLM-1002/decision",
        json={
            "decision": "approve",
            "payout": 1150.0,
            "reason": "Covered.",
            "policy_section": "Section 5",
        },
    )
    held = client.post("/api/claims/CLM-1002/failure", json={"reason": "nope"})
    assert held.status_code == 409
    empty = client.post("/api/claims/CLM-1003/failure", json={"reason": "  "})
    assert empty.status_code == 422


def test_second_decision_and_pay_refused(client: TestClient):
    client.post(
        "/api/claims/CLM-1001/decision",
        json={
            "decision": "approve",
            "payout": 420.0,
            "reason": "Covered trip delay.",
            "policy_section": "Section 3",
        },
    )
    again = client.post(
        "/api/claims/CLM-1001/decision",
        json={
            "decision": "decline",
            "payout": 0,
            "reason": "Changed my mind.",
            "policy_section": "Section 9",
        },
    )
    assert again.status_code == 409
    client.post("/api/claims/CLM-1001/pay", json={"amount": 420.0})
    paid = client.post("/api/claims/CLM-1001/pay", json={"amount": 420.0})
    assert paid.status_code == 409
    assert paid.json()["detail"] == "already_paid"


def test_runs_todos_and_finish(client: TestClient):
    assert client.get("/api/runs/latest").json() is None
    cap0 = client.post("/api/runs", json={"cap": 0})
    assert cap0.status_code == 422
    started = client.post("/api/runs", json={"cap": 5})
    assert started.status_code == 200
    run = started.json()
    assert run["cap"] == 5
    assert run["status"] == "running"
    assert run["started_at"]
    assert run["summary"] is None
    assert run["todos"] == []
    assert client.get("/api/runs/latest").json()["id"] == run["id"]
    second = client.post("/api/runs", json={"cap": 5})
    assert second.status_code == 409

    two = client.put(
        f"/api/runs/{run['id']}/todos",
        json={
            "todos": [
                {"content": "CLM-1001", "status": "to_do"},
                {"content": "CLM-1002", "status": "in_progress"},
            ]
        },
    )
    assert two.status_code == 200
    three = client.put(
        f"/api/runs/{run['id']}/todos",
        json={
            "todos": [
                {"content": "CLM-1001", "status": "done"},
                {"content": "CLM-1002", "status": "done"},
                {"content": "Summary", "status": "to_do"},
            ]
        },
    )
    assert three.status_code == 200
    latest = client.get("/api/runs/latest").json()
    assert [item["content"] for item in latest["todos"]] == [
        "CLM-1001",
        "CLM-1002",
        "Summary",
    ]
    blocked = client.put(
        f"/api/runs/{run['id']}/todos",
        json={"todos": [{"content": "x", "status": "blocked"}]},
    )
    assert blocked.status_code == 422
    blank = client.put(
        f"/api/runs/{run['id']}/todos",
        json={"todos": [{"content": " ", "status": "to_do"}]},
    )
    assert blank.status_code == 422
    missing = client.put(
        "/api/runs/999/todos",
        json={"todos": [{"content": "x", "status": "to_do"}]},
    )
    assert missing.status_code == 404

    finished = client.post(
        f"/api/runs/{run['id']}/finish",
        json={"summary": "Three claims decided."},
    )
    assert finished.status_code == 200
    body = finished.json()
    assert body["status"] == "finished"
    assert body["finished_at"]
    assert body["summary"] == "Three claims decided."
    assert (
        client.put(
            f"/api/runs/{run['id']}/todos",
            json={"todos": [{"content": "x", "status": "to_do"}]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/runs/{run['id']}/finish",
            json={"summary": "Again."},
        ).status_code
        == 409
    )
    nxt = client.post("/api/runs", json={"cap": 2})
    assert nxt.status_code == 200
    assert client.get("/api/runs/latest").json()["id"] == nxt.json()["id"]


def test_unknown_ids(client: TestClient):
    assert client.post("/api/claims/CLM-9999/start").status_code == 404
    assert (
        client.post("/api/claims/CLM-9999/failure", json={"reason": "x"}).status_code
        == 404
    )
    assert (
        client.post("/api/runs/9/finish", json={"summary": "Done."}).status_code == 404
    )
    started = client.post("/api/runs", json={"cap": 1})
    empty = client.post(
        f"/api/runs/{started.json()['id']}/finish", json={"summary": " "}
    )
    assert empty.status_code == 422


def test_reseed_leaves_waiting_claims(tmp_path: Path):
    db_path = tmp_path / "reseed.db"
    connection = store.init_db(db_path)
    store.record_decision(
        connection,
        "CLM-1001",
        {
            "decision": "decline",
            "payout": 0,
            "reason": "Test.",
            "policy_section": "Section 9",
        },
    )
    connection.close()
    seed.reseed(db_path)
    again = store.init_db(db_path)
    claims = store.list_claims(again)
    assert len(claims) == 25
    assert all(claim["status"] == "waiting" for claim in claims)
    again.close()
