"""Tests for starting the agent from the API."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent import main as agent_main
from backend import main, store


class StubModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    connection = store.init_db(tmp_path / "run.db")
    monkeypatch.setattr(main, "db", connection)
    monkeypatch.setattr(agent_main, "backend", lambda: TestClient(main.app))
    with TestClient(main.app) as test_client:
        yield test_client
    monkeypatch.setattr(main, "agent_llm", None)
    connection.close()


def test_run_route_approves_and_pays(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_claim", "args": {}, "id": "1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_policy_wording", "args": {}, "id": "2"}],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "record_decision",
                    "args": {
                        "decision": "approve",
                        "payout": 420.0,
                        "reason": "Covered trip delay with receipts.",
                        "policy_section": "Section 3 Trip Delay",
                    },
                    "id": "3",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "pay", "args": {"amount": 420.0}, "id": "4"}],
        ),
        AIMessage(content="Done."),
    ]
    monkeypatch.setattr(main, "agent_llm", StubModel(messages=iter(replies)))
    started = client.post("/api/claims/CLM-1001/run")
    assert started.status_code == 200
    assert started.json()["status"] == "started"

    claim = None
    for _ in range(100):
        claim = client.get("/api/claims/CLM-1001").json()
        if claim["status"] == "decided" and claim["paid_amount"] == 420.0:
            break
        time.sleep(0.05)
    assert claim is not None
    assert claim["decision"] == "approve"
    assert claim["paid_amount"] == 420.0
    assert claim["status"] == "decided"
