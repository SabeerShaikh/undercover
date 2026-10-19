"""The UnderCover backend."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend import store

app = FastAPI(title="UnderCover")
db = store.init_db()


class DecisionBody(BaseModel):
    decision: str
    payout: float
    reason: str
    policy_section: str


class PayBody(BaseModel):
    amount: float


class StepBody(BaseModel):
    tool_name: str
    detail: str


class StatusBody(BaseModel):
    status: str = Field(examples=["in_progress"])


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/claims", operation_id="list_claims")
def list_claims() -> list[dict[str, Any]]:
    """List claims in the queue."""
    return store.list_claims(db)


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str) -> dict[str, Any]:
    """Return one claim with policy, customer, decision and steps."""
    claim = store.get_claim(db, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


@app.get("/api/policy-wording", operation_id="get_policy_wording")
def get_policy_wording() -> dict[str, str]:
    """Return the policy wording."""
    return {"text": store.get_policy_wording(db)}


@app.get("/api/instructions", operation_id="get_instructions")
def get_instructions() -> dict[str, str]:
    """Return the agent's instructions."""
    return {"text": store.get_instructions(db)}


@app.post("/api/claims/{claim_id}/decision", operation_id="record_decision")
def record_decision(claim_id: str, body: DecisionBody) -> dict[str, str]:
    """Record an approve, decline or refer decision on a claim."""
    status = store.record_decision(
        db,
        claim_id,
        {
            "decision": body.decision,
            "payout": body.payout,
            "reason": body.reason,
            "policy_section": body.policy_section,
        },
    )
    if status is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return {"status": status}


@app.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off")
def sign_off(claim_id: str) -> dict[str, str]:
    """Sign off a claim that is waiting for handler approval."""
    if not store.sign_off(db, claim_id):
        raise HTTPException(status_code=409, detail="Claim is not waiting for sign-off")
    return {"status": "signed_off"}


@app.post("/api/claims/{claim_id}/pay", operation_id="pay_claim")
def pay_claim(claim_id: str, body: PayBody) -> dict[str, str]:
    """Pay an approved claim for the given amount."""
    ok, reason = store.pay(db, claim_id, body.amount)
    if not ok:
        if reason == "not_found":
            raise HTTPException(status_code=404, detail="Claim not found")
        raise HTTPException(status_code=409, detail=reason)
    return {"status": "paid"}


@app.post("/api/claims/{claim_id}/steps", operation_id="add_step")
def add_step(claim_id: str, body: StepBody) -> dict[str, str]:
    """Append a step while the agent works a claim."""
    if not store.add_step(db, claim_id, body.tool_name, body.detail):
        raise HTTPException(status_code=404, detail="Claim not found")
    return {"status": "ok"}


@app.post("/api/claims/{claim_id}/status", operation_id="set_status")
def set_status(claim_id: str, body: StatusBody) -> dict[str, str]:
    """Set a claim's working status."""
    if not store.set_status(db, claim_id, body.status):
        raise HTTPException(status_code=409, detail="Cannot set status")
    return {"status": body.status}
