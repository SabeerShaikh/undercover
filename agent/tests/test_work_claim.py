"""Tests for work_claim failure handling and the one-line report."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent import __main__ as cli
from agent import main
from backend import main as backend_main
from backend import store


class StubModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def boom_on_second() -> GenericFakeChatModel:
    calls = {"n": 0}

    class BoomOnSecond(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise RuntimeError("503: The model is unavailable")
            return super()._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )

    return BoomOnSecond(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "get_claim", "args": {}, "id": "1"}],
                )
            ]
        )
    )


class LoopGetClaim(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        message = AIMessage(
            content="",
            tool_calls=[{"name": "get_claim", "args": {}, "id": str(uuid4())}],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def recording_stub(messages: list[AIMessage]) -> tuple[GenericFakeChatModel, list]:
    prompts: list = []

    class RecordingStub(StubModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            prompts.append(list(messages))
            return super()._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )

    return RecordingStub(messages=iter(messages)), prompts


def _approve_replies(payout: float, pay: bool) -> list[AIMessage]:
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
                        "payout": payout,
                        "reason": "Covered.",
                        "policy_section": "Section 3",
                    },
                    "id": "2",
                }
            ],
        ),
    ]
    if pay:
        replies.append(
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "pay_claim", "args": {"amount": payout}, "id": "3"}
                ],
            )
        )
    replies.append(AIMessage(content="done"))
    return replies


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    connection = store.init_db(tmp_path / "work.db")
    monkeypatch.setattr(backend_main, "db", connection)
    monkeypatch.setattr(main, "backend", lambda: TestClient(backend_main.app))
    with TestClient(backend_main.app) as client:
        yield client
    connection.close()


def test_work_claim_approves_and_pays(api: TestClient):
    report = main.work_claim(
        "CLM-1001", StubModel(messages=iter(_approve_replies(420.0, pay=True)))
    )
    assert report == "CLM-1001  approve  $420.00"
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["paid_amount"] == 420.0


def test_work_claim_over_limit(api: TestClient):
    report = main.work_claim(
        "CLM-1002",
        StubModel(messages=iter(_approve_replies(1150.0, pay=True))),
    )
    assert report.endswith("waiting for sign-off")
    claim = api.get("/api/claims/CLM-1002").json()
    assert claim["status"] == "waiting_for_sign_off"
    assert claim["paid_amount"] is None


def test_provider_error_returns_to_queue(api: TestClient):
    report = main.work_claim("CLM-1001", boom_on_second())
    assert "back in the queue" in report
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "waiting"
    assert claim["attempts"] == 1
    assert claim["steps"][-1]["tool_name"] == "error"


def test_second_failure_left_for_handler(api: TestClient):
    main.work_claim("CLM-1001", boom_on_second())
    report = main.work_claim("CLM-1001", boom_on_second())
    assert "left for a handler" in report
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "left_for_handler"
    assert claim["attempts"] == 2


def test_finishes_without_decision(api: TestClient):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_claim", "args": {}, "id": "1"}],
        ),
        AIMessage(content="I am done looking."),
    ]
    report = main.work_claim("CLM-1001", StubModel(messages=iter(replies)))
    assert "finished without recording a decision" in report
    assert "back in the queue" in report
    assert api.get("/api/claims/CLM-1001").json()["status"] == "waiting"


def test_step_limit_returns_to_queue(api: TestClient):
    report = main.work_claim("CLM-1001", LoopGetClaim(messages=iter([])))
    assert "back in the queue" in report
    assert api.get("/api/claims/CLM-1001").json()["status"] == "waiting"


def test_error_after_decision_keeps_it(api: TestClient):
    calls = {"n": 0}

    class BoomAfterDecision(StubModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise RuntimeError("provider down")
            return super()._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )

    report = main.work_claim(
        "CLM-1001",
        BoomAfterDecision(
            messages=iter(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "record_decision",
                                "args": {
                                    "decision": "decline",
                                    "payout": 0,
                                    "reason": "Excluded.",
                                    "policy_section": "Section 9",
                                },
                                "id": "1",
                            }
                        ],
                    )
                ]
            )
        ),
    )
    assert "decline" in report
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["decision"] == "decline"
    assert claim["status"] == "decided"
    kinds = [step["tool_name"] for step in claim["steps"]]
    assert "error" not in kinds


def test_not_started_on_decided_claim(api: TestClient):
    api.post(
        "/api/claims/CLM-1001/decision",
        json={
            "decision": "decline",
            "payout": 0,
            "reason": "Already done.",
            "policy_section": "Section 9",
        },
    )
    report = main.work_claim("CLM-1001", StubModel(messages=iter([])))
    assert "not started" in report
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["attempts"] == 0
    assert claim["steps"] == []


def test_fresh_context_each_claim(api: TestClient):
    first, _ = recording_stub(_approve_replies(420.0, pay=True))
    main.work_claim("CLM-1001", first)
    second, prompts = recording_stub(
        [
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
                            "reason": "Excluded.",
                            "policy_section": "Section 9",
                        },
                        "id": "2",
                    }
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    main.work_claim("CLM-1003", second)
    prompt = prompts[0]
    texts = [getattr(msg, "content", "") for msg in prompt]
    joined = " ".join(str(text) for text in texts)
    assert "CLM-1003" in joined
    assert "CLM-1001" not in joined
    instructions = api.get("/api/instructions").json()["claim"]
    assert instructions in joined or any(
        instructions[:40] in str(text) for text in texts
    )


def test_cli_one_claim(api: TestClient, monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr(
        main, "work_claim", lambda claim_id, llm=None: f"report {claim_id}"
    )
    assert cli.main_cli(["CLM-1001"]) == 0
    assert "report CLM-1001" in capsys.readouterr().out
