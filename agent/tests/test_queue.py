"""Tests for the queue agent: cap, retries, missed-claim check, CLI."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent import __main__ as cli
from agent import main
from agent.tools import QUEUE_TOOLS


class StubModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def recording_stub(messages: list[AIMessage]) -> tuple[GenericFakeChatModel, list]:
    prompts: list = []

    class RecordingStub(StubModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            prompts.append(list(messages))
            return super()._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )

    return RecordingStub(messages=iter(messages)), prompts


def _approve_replies(payout: float = 420.0, pay: bool = True) -> list[AIMessage]:
    replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_claim", "args": {}, "id": str(uuid4())}],
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
                    "id": str(uuid4()),
                }
            ],
        ),
    ]
    if pay:
        replies.append(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "pay_claim",
                        "args": {"amount": payout},
                        "id": str(uuid4()),
                    }
                ],
            )
        )
    replies.append(AIMessage(content="done"))
    return replies


def _human_claim_id(messages) -> str | None:
    last = messages[-1] if messages else None
    content = getattr(last, "content", "") if last is not None else ""
    if isinstance(content, str) and content.startswith("Work claim "):
        return content.split()[2].rstrip(".")
    return None


def claim_script(actions: dict[str, list[str]]) -> GenericFakeChatModel:
    leftover = {key: list(value) for key, value in actions.items()}
    session = {"claim_id": None, "action": "approve", "step": 0}

    class Scripted(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            started = _human_claim_id(messages)
            if started:
                session["claim_id"] = started
                session["step"] = 0
                queued = leftover.get(started, [])
                session["action"] = queued.pop(0) if queued else "approve"
            session["step"] += 1
            if session["action"] == "fail":
                if session["step"] >= 2:
                    raise RuntimeError("503: The model is unavailable")
                message = AIMessage(
                    content="",
                    tool_calls=[{"name": "get_claim", "args": {}, "id": str(uuid4())}],
                )
                return ChatResult(generations=[ChatGeneration(message=message)])
            replies = _approve_replies()
            index = min(session["step"] - 1, len(replies) - 1)
            return ChatResult(generations=[ChatGeneration(message=replies[index])])

    return Scripted(messages=iter([]))


def _tool(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id}],
    )


def _todos(*items: tuple[str, str]) -> list[dict[str, str]]:
    return [{"content": content, "status": status} for content, status in items]


def queue_messages_for(claim_ids: list[str], extra: list[AIMessage] | None = None):
    check = "Check for missed claims"
    summary = "Write the summary"
    todos = _todos(
        *[(claim_id, "to_do") for claim_id in claim_ids],
        (check, "to_do"),
        (summary, "to_do"),
    )
    messages = [
        _tool("list_claims", {}, "list"),
        _tool("write_todos", {"todos": [dict(item) for item in todos]}, "plan"),
    ]
    for index, claim_id in enumerate(claim_ids):
        todos[index] = {"content": claim_id, "status": "in_progress"}
        messages.append(
            _tool(
                "write_todos",
                {"todos": [dict(item) for item in todos]},
                f"ip-{claim_id}",
            )
        )
        messages.append(_tool("work_claim", {"claim_id": claim_id}, f"w-{claim_id}"))
        todos[index] = {"content": claim_id, "status": "done"}
        messages.append(
            _tool(
                "write_todos",
                {"todos": [dict(item) for item in todos]},
                f"done-{claim_id}",
            )
        )
    if extra:
        messages.extend(extra)
    messages.append(AIMessage(content="Three claims decided. None left for a handler."))
    return messages


def _keep_waiting(api: TestClient, keep: set[str]) -> None:
    for claim in api.get("/api/claims").json():
        if claim["claim_id"] in keep or claim["status"] != "waiting":
            continue
        api.post(
            f"/api/claims/{claim['claim_id']}/decision",
            json={
                "decision": "decline",
                "payout": 0,
                "reason": "Out of this test.",
                "policy_section": "Section 9",
            },
        )


def test_queue_tools():
    assert [tool.name for tool in QUEUE_TOOLS] == [
        "list_claims",
        "write_todos",
        "work_claim",
    ]


def test_queue_run_of_three(api: TestClient):
    _keep_waiting(api, {"CLM-1001", "CLM-1002", "CLM-1003"})
    ids = ["CLM-1001", "CLM-1002", "CLM-1003"]
    queue, prompts = recording_stub(queue_messages_for(ids))
    claim_llm = StubModel(
        messages=iter(
            _approve_replies() + _approve_replies(1150.0, pay=True) + _approve_replies()
        )
    )
    summary = main.run_queue(cap=3, llm=queue, claim_llm=claim_llm)
    assert "decided" in summary.lower() or "Three" in summary
    for claim_id in ids:
        claim = api.get(f"/api/claims/{claim_id}").json()
        assert claim["decision"] is not None
        assert claim["status"] in {"decided", "waiting_for_sign_off"}
    run = api.get("/api/runs/latest").json()
    assert run["status"] == "finished"
    assert run["summary"] == summary
    assert all(
        item["status"] == "done"
        for item in run["todos"]
        if item["content"].startswith("CLM-")
    )
    first = " ".join(str(getattr(msg, "content", "")) for msg in prompts[0])
    assert "3" in first


def test_cap_refuses_a_third_new_claim(api: TestClient):
    _keep_waiting(api, {"CLM-1001", "CLM-1002", "CLM-1003", "CLM-1004"})
    messages = queue_messages_for(["CLM-1001", "CLM-1002"])[:-1] + [
        _tool("work_claim", {"claim_id": "CLM-1003"}, "over"),
        AIMessage(content="Stopped at the cap of 2."),
    ]
    summary = main.run_queue(
        cap=2,
        llm=StubModel(messages=iter(messages)),
        claim_llm=StubModel(messages=iter(_approve_replies() + _approve_replies())),
    )
    assert "cap" in summary.lower()
    assert api.get("/api/claims/CLM-1001").json()["decision"] is not None
    assert api.get("/api/claims/CLM-1002").json()["decision"] is not None
    assert api.get("/api/claims/CLM-1003").json()["status"] == "waiting"
    assert api.get("/api/claims/CLM-1003").json()["attempts"] == 0
    assert api.get("/api/claims/CLM-1004").json()["status"] == "waiting"
    assert api.get("/api/claims/CLM-1004").json()["attempts"] == 0


def test_first_claim_fails_others_still_decided(api: TestClient):
    _keep_waiting(api, {"CLM-1001", "CLM-1002", "CLM-1003"})
    ids = ["CLM-1001", "CLM-1002", "CLM-1003"]
    extra = [
        _tool("work_claim", {"claim_id": "CLM-1001"}, "retry"),
        _tool(
            "write_todos",
            {
                "todos": _todos(
                    ("CLM-1001", "done"),
                    ("CLM-1002", "done"),
                    ("CLM-1003", "done"),
                    ("Check for missed claims", "done"),
                    ("Write the summary", "done"),
                )
            },
            "all-done",
        ),
    ]
    messages = queue_messages_for(ids)
    messages = messages[:-1] + extra + [AIMessage(content="Two decided, one retried.")]
    summary = main.run_queue(
        cap=3,
        llm=StubModel(messages=iter(messages)),
        claim_llm=claim_script({"CLM-1001": ["fail", "approve"]}),
    )
    assert api.get("/api/claims/CLM-1001").json()["decision"] is not None
    assert api.get("/api/claims/CLM-1002").json()["decision"] is not None
    assert api.get("/api/claims/CLM-1003").json()["decision"] is not None
    assert api.get("/api/runs/latest").json()["status"] == "finished"
    assert summary


def test_retry_after_one_failure_is_decided(api: TestClient):
    _keep_waiting(api, {"CLM-1001", "CLM-1002", "CLM-1003"})
    extra = [_tool("work_claim", {"claim_id": "CLM-1001"}, "retry")]
    messages = queue_messages_for(["CLM-1001", "CLM-1002", "CLM-1003"])
    messages = messages[:-1] + extra + [AIMessage(content="Retried CLM-1001.")]
    main.run_queue(
        cap=3,
        llm=StubModel(messages=iter(messages)),
        claim_llm=claim_script({"CLM-1001": ["fail", "approve"]}),
    )
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["decision"] == "approve"
    kinds = [step["tool_name"] for step in claim["steps"]]
    assert kinds.count("error") == 1
    assert "record_decision" in kinds


def test_two_failures_left_for_handler(api: TestClient):
    _keep_waiting(api, {"CLM-1001", "CLM-1002", "CLM-1003"})
    extra = [
        _tool("work_claim", {"claim_id": "CLM-1001"}, "retry"),
        _tool(
            "write_todos",
            {
                "todos": _todos(
                    ("CLM-1001", "left_for_handler"),
                    ("CLM-1002", "done"),
                    ("CLM-1003", "done"),
                    ("Check for missed claims", "done"),
                    ("Write the summary", "done"),
                )
            },
            "left",
        ),
        AIMessage(content="CLM-1001 left for a handler. The others are decided."),
    ]
    messages = queue_messages_for(["CLM-1001", "CLM-1002", "CLM-1003"])
    messages = messages[:-1] + extra
    summary = main.run_queue(
        cap=3,
        llm=StubModel(messages=iter(messages)),
        claim_llm=claim_script({"CLM-1001": ["fail", "fail"]}),
    )
    assert (
        "left for a handler" in summary.lower()
        or api.get("/api/claims/CLM-1001").json()["status"] == "left_for_handler"
    )
    assert api.get("/api/claims/CLM-1001").json()["status"] == "left_for_handler"
    assert api.get("/api/claims/CLM-1002").json()["decision"] is not None
    assert api.get("/api/claims/CLM-1003").json()["decision"] is not None


def test_missed_claim_reminder_then_works_it(api: TestClient):
    _keep_waiting(api, {"CLM-1001", "CLM-1002", "CLM-1003"})
    first_pass = queue_messages_for(["CLM-1001", "CLM-1002", "CLM-1003"])
    # Finish after the first pass without retrying the failed first claim.
    # boom_then_approves fails 1001, then approves 1002 and 1003.
    messages = first_pass[:-1] + [
        AIMessage(content="I think we are done."),
        _tool("work_claim", {"claim_id": "CLM-1001"}, "after-nudge"),
        AIMessage(content="Worked the missed claim. All decided."),
    ]
    main.run_queue(
        cap=3,
        llm=StubModel(messages=iter(messages)),
        claim_llm=claim_script({"CLM-1001": ["fail", "approve"]}),
    )
    assert api.get("/api/claims/CLM-1001").json()["decision"] is not None
    assert api.get("/api/runs/latest").json()["status"] == "finished"


def test_ignored_reminder_finishes_after_two(api: TestClient):
    _keep_waiting(api, {"CLM-1001", "CLM-1002", "CLM-1003"})
    messages = queue_messages_for(["CLM-1001", "CLM-1002", "CLM-1003"])[:-1] + [
        AIMessage(content="Stopping now."),
        AIMessage(content="Still stopping."),
        AIMessage(content="Done anyway."),
    ]
    main.run_queue(
        cap=3,
        llm=StubModel(messages=iter(messages)),
        claim_llm=claim_script({"CLM-1001": ["fail"]}),
    )
    run = api.get("/api/runs/latest").json()
    assert run["status"] == "finished"
    assert api.get("/api/claims/CLM-1001").json()["status"] == "waiting"


def test_recovers_in_progress_before_run(api: TestClient):
    _keep_waiting(api, {"CLM-1001", "CLM-1002"})
    started = api.post("/api/claims/CLM-1001/start")
    assert started.status_code == 200
    messages = queue_messages_for(["CLM-1001", "CLM-1002"])
    main.run_queue(
        cap=2,
        llm=StubModel(messages=iter(messages)),
        claim_llm=StubModel(messages=iter(_approve_replies() + _approve_replies())),
    )
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["decision"] == "approve"
    details = [step["detail"] for step in claim["steps"]]
    assert any(
        "run stopped before this claim was finished" in detail.lower()
        for detail in details
    )


def test_queue_model_raise_finishes_run(api: TestClient):
    _keep_waiting(api, {"CLM-1001"})
    api.post("/api/claims/CLM-1001/start")

    class Boom(StubModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            raise RuntimeError("queue provider down")

    summary = main.run_queue(
        cap=1, llm=Boom(messages=iter([])), claim_llm=StubModel(messages=iter([]))
    )
    assert summary.startswith("The run stopped:")
    assert api.get("/api/runs/latest").json()["status"] == "finished"
    assert api.get("/api/claims/CLM-1001").json()["status"] == "waiting"
    assert api.get("/api/claims/CLM-1001").json()["decision"] is None


def test_nothing_waiting_starts_no_run(api: TestClient):
    _keep_waiting(api, set())
    summary = main.run_queue(cap=5, llm=StubModel(messages=iter([])), claim_llm=None)
    assert summary == "No claims are waiting"
    assert api.get("/api/runs/latest").json() is None


def test_cli_cap_and_one_claim(api: TestClient, monkeypatch: pytest.MonkeyPatch):
    caps: list[int | None] = []

    def fake_queue(cap: int | None = None, llm=None, claim_llm=None) -> str:
        caps.append(cap)
        return "queued"

    monkeypatch.setattr(main, "run_queue", fake_queue)
    monkeypatch.setattr(
        main, "work_claim", lambda claim_id, llm=None: f"one {claim_id}"
    )
    assert cli.main_cli([]) == 0
    assert cli.main_cli(["--cap", "5"]) == 0
    assert caps == [None, 5]
    assert cli.main_cli(["CLM-1001"]) == 0
