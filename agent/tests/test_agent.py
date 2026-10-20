"""Tests for the UnderCover Agent with a stub model."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent import main
from backend import main as backend_main
from backend import store


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies in place of a real model."""

    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    connection = store.init_db(tmp_path / "agent.db")
    monkeypatch.setattr(backend_main, "db", connection)
    monkeypatch.setattr(main, "backend", lambda: TestClient(backend_main.app))
    with TestClient(backend_main.app) as client:
        yield client
    connection.close()


def test_model_name(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    built = main.model()
    assert built.model_name == "deepseek/deepseek-v4.1-flash"
    assert built.reasoning_effort == "low"
    assert built.request_timeout == 120
    assert built.max_retries == 5
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    override = main.model()
    assert override.model_name == "openrouter/free"


def test_claim_tools():
    names = [tool.name for tool in main._tools_for("CLM-1001")]
    assert names == list(main.CLAIM_TOOLS)


def test_instructions_match_api(api: TestClient):
    assert main.fetch_instructions() == api.get("/api/instructions").json()["claim"]


def test_read_section_records_reading(api: TestClient):
    replies = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_section",
                    "args": {"document": "claims_manual", "number": 9},
                    "id": "1",
                }
            ],
        ),
        AIMessage(content="Read repeat claims."),
    ]
    main.run("CLM-1001", "thread-read", StubModel(messages=iter(replies)))
    claim = api.get("/api/claims/CLM-1001").json()
    details = [step["detail"] for step in claim["steps"]]
    assert "Claims manual, section 9: Repeat claims" in details
    kinds = [step["tool_name"] for step in claim["steps"]]
    assert "reading" in kinds


def test_read_missing_section_is_refusal(api: TestClient):
    replies = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_section",
                    "args": {"document": "claims_manual", "number": 15},
                    "id": "1",
                }
            ],
        ),
        AIMessage(content="Section missing."),
    ]
    main.run("CLM-1001", "thread-missing", StubModel(messages=iter(replies)))
    claim = api.get("/api/claims/CLM-1001").json()
    kinds = [step["tool_name"] for step in claim["steps"]]
    assert "reading" not in kinds


def test_run_approves_and_pays(api: TestClient):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_claim", "args": {}, "id": "1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_section",
                    "args": {"document": "policy_wording", "number": 3},
                    "id": "2",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "record_decision",
                    "args": {
                        "decision": "approve",
                        "payout": 420.0,
                        "reason": "Covered trip delay with receipts attached.",
                        "policy_section": "Section 3 Trip Delay",
                    },
                    "id": "3",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "pay_claim", "args": {"amount": 420.0}, "id": "4"}],
        ),
        AIMessage(content="Approved and paid $420.00."),
    ]
    reply = main.run("CLM-1001", "thread-1", StubModel(messages=iter(replies)))
    assert "420" in reply or "Approved" in reply
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["decision"] == "approve"
    assert claim["paid_amount"] == 420.0
    assert claim["status"] == "decided"
    assert claim["steps"]


def test_run_over_limit_blocks_pay(api: TestClient):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_claim", "args": {}, "id": "1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "record_decision",
                    "args": {
                        "decision": "approve",
                        "payout": 1150.0,
                        "reason": "Covered baggage loss after airline compensation.",
                        "policy_section": "Section 5 Baggage",
                    },
                    "id": "3",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "pay_claim", "args": {"amount": 1150.0}, "id": "4"}],
        ),
        AIMessage(content="Approved; waiting for sign-off."),
    ]
    main.run("CLM-1002", "thread-2", StubModel(messages=iter(replies)))
    claim = api.get("/api/claims/CLM-1002").json()
    assert claim["status"] == "waiting_for_sign_off"
    assert claim["paid_amount"] is None
    assert claim["decision"] == "approve"


def test_run_declines(api: TestClient):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_claim", "args": {}, "id": "1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "record_decision",
                    "args": {
                        "decision": "decline",
                        "payout": 0,
                        "reason": "The loss is excluded by the policy wording.",
                        "policy_section": "Exclusions",
                    },
                    "id": "3",
                }
            ],
        ),
        AIMessage(content="Declined."),
    ]
    main.run("CLM-1003", "thread-3", StubModel(messages=iter(replies)))
    claim = api.get("/api/claims/CLM-1003").json()
    assert claim["decision"] == "decline"
    assert claim["status"] == "decided"
    assert claim["paid_amount"] is None
