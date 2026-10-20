"""Tests for the claims API."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main, store


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    connection = store.init_db(tmp_path / "api.db")
    monkeypatch.setattr(main, "db", connection)
    with TestClient(main.app) as test_client:
        yield test_client
    connection.close()


def test_list_claims(client: TestClient):
    response = client.get("/api/claims")
    assert response.status_code == 200
    claims = response.json()
    assert len(claims) == 25
    clm = next(c for c in claims if c["claim_id"] == "CLM-1001")
    assert clm["status"] == "waiting"
    assert clm["amount_claimed"] == 420.0
    assert clm["customer_name"] == "Maya Patel"
    assert clm["decision"] is None
    assert clm["payout"] is None


def test_get_claim(client: TestClient):
    response = client.get("/api/claims/CLM-1001")
    assert response.status_code == 200
    claim = response.json()
    assert "story" in claim
    assert claim["story"]
    assert claim["documents"]
    assert claim["policy"]["policy_id"] == "POL-2001"
    assert claim["plan"]["trip_delay_max"] == 800.0
    assert claim["customer"]["previous_claims"]


def test_policy_wording_and_instructions(client: TestClient):
    wording = client.get("/api/policy-wording")
    assert wording.status_code == 200
    assert wording.json()["text"].strip()
    instructions = client.get("/api/instructions")
    assert instructions.status_code == 200
    body = instructions.json()
    assert "UnderCover Agent" in body["claim"]
    assert body["queue"]


def test_decline_then_pay_fails(client: TestClient):
    decision = client.post(
        "/api/claims/CLM-1001/decision",
        json={
            "decision": "decline",
            "payout": 0,
            "reason": "Not covered.",
            "policy_section": "Section 3",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "decided"
    pay = client.post("/api/claims/CLM-1001/pay", json={"amount": 100})
    assert pay.status_code == 409


def test_approve_and_pay(client: TestClient):
    decision = client.post(
        "/api/claims/CLM-1001/decision",
        json={
            "decision": "approve",
            "payout": 420.0,
            "reason": "Covered trip delay with receipts.",
            "policy_section": "Section 3 Trip Delay",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "decided"
    pay = client.post("/api/claims/CLM-1001/pay", json={"amount": 420.0})
    assert pay.status_code == 200
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["paid_amount"] == 420.0


def test_approve_over_limit_needs_sign_off(client: TestClient):
    decision = client.post(
        "/api/claims/CLM-1002/decision",
        json={
            "decision": "approve",
            "payout": 1150.0,
            "reason": "Covered baggage loss.",
            "policy_section": "Section 5 Baggage",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "waiting_for_sign_off"
    pay = client.post("/api/claims/CLM-1002/pay", json={"amount": 1150.0})
    assert pay.status_code == 409
    sign = client.post("/api/claims/CLM-1002/sign-off")
    assert sign.status_code == 200
    pay2 = client.post("/api/claims/CLM-1002/pay", json={"amount": 1150.0})
    assert pay2.status_code == 200
    claim = client.get("/api/claims/CLM-1002").json()
    assert claim["status"] == "decided"
    assert claim["paid_amount"] == 1150.0


def test_status_and_steps(client: TestClient):
    status = client.post(
        "/api/claims/CLM-1001/status",
        json={"status": "in_progress"},
    )
    assert status.status_code == 200
    step = client.post(
        "/api/claims/CLM-1001/steps",
        json={"tool_name": "get_claim", "detail": "Loaded CLM-1001"},
    )
    assert step.status_code == 200
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "in_progress"
    assert claim["steps"][0]["tool_name"] == "get_claim"
