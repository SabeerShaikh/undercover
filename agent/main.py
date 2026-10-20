"""The UnderCover Agent."""

from __future__ import annotations

import json
import os
import uuid
from http import HTTPStatus
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from backend.documents import DOCUMENT_LABELS

load_dotenv(override=True)

BACKEND_URL = "http://localhost:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
MODEL_TIMEOUT = 120
MODEL_RETRIES = 5
STEP_LIMIT = 60


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or DeepSeek V4.1 Flash by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
        timeout=MODEL_TIMEOUT,
        max_retries=MODEL_RETRIES,
    )


def _add_step(claim_id: str, tool_name: str, detail: str) -> None:
    with backend() as client:
        client.post(
            f"/api/claims/{claim_id}/steps",
            json={"tool_name": tool_name, "detail": detail},
        ).raise_for_status()


def _tools_for(claim_id: str) -> list[StructuredTool]:
    class DecisionArgs(BaseModel):
        decision: str = Field(description="approve, decline, or refer")
        payout: float = Field(description="Payout in US dollars, 0 if not approving")
        reason: str = Field(
            description="Two or three sentences explaining the decision"
        )
        policy_section: str = Field(
            description="Sections of the wording and manual relied on"
        )

    class PayArgs(BaseModel):
        amount: float = Field(description="Amount to pay in US dollars")

    class SearchArgs(BaseModel):
        query: str = Field(description="Word or phrase to find in the documents")

    class ReadArgs(BaseModel):
        document: str = Field(description="policy_wording or claims_manual")
        number: int = Field(description="Section number")

    def get_claim() -> str:
        _add_step(claim_id, "get_claim", f"Read claim {claim_id}")
        with backend() as client:
            response = client.get(f"/api/claims/{claim_id}")
        response.raise_for_status()
        return json.dumps(response.json())

    def search_documents(query: str) -> str:
        _add_step(claim_id, "search_documents", query)
        with backend() as client:
            response = client.get("/api/documents/search", params={"query": query})
        if response.status_code >= HTTPStatus.BAD_REQUEST:
            return json.dumps({"status": "refused", "detail": response.json()})
        return json.dumps(response.json())

    def read_section(document: str, number: int) -> str:
        _add_step(claim_id, "read_section", f"{document} {number}")
        with backend() as client:
            response = client.get(f"/api/documents/{document}/sections/{number}")
        if response.status_code >= HTTPStatus.BAD_REQUEST:
            return json.dumps({"status": "refused", "detail": response.json()})
        data = response.json()
        label = DOCUMENT_LABELS.get(document, document)
        _add_step(
            claim_id,
            "reading",
            f"{label}, section {data['number']}: {data['title']}",
        )
        return json.dumps(data)

    def record_decision(
        decision: str, payout: float, reason: str, policy_section: str
    ) -> str:
        _add_step(
            claim_id,
            "record_decision",
            f"{decision} payout={payout}",
        )
        with backend() as client:
            response = client.post(
                f"/api/claims/{claim_id}/decision",
                json={
                    "decision": decision,
                    "payout": payout,
                    "reason": reason,
                    "policy_section": policy_section,
                },
            )
        if response.status_code >= HTTPStatus.BAD_REQUEST:
            return json.dumps({"status": "refused", "detail": response.json()})
        return json.dumps(response.json())

    def pay_claim(amount: float) -> str:
        _add_step(claim_id, "pay_claim", f"Pay {amount}")
        with backend() as client:
            response = client.post(
                f"/api/claims/{claim_id}/pay",
                json={"amount": amount},
            )
        if response.status_code == HTTPStatus.CONFLICT:
            return json.dumps({"status": "refused", "detail": response.json()})
        response.raise_for_status()
        return json.dumps(response.json())

    return [
        StructuredTool.from_function(
            get_claim,
            name="get_claim",
            description="Read the full claim, policy, plan and customer history.",
        ),
        StructuredTool.from_function(
            search_documents,
            name="search_documents",
            description="Search the policy wording and claims manual.",
            args_schema=SearchArgs,
        ),
        StructuredTool.from_function(
            read_section,
            name="read_section",
            description="Read one numbered section of the wording or the manual.",
            args_schema=ReadArgs,
        ),
        StructuredTool.from_function(
            record_decision,
            name="record_decision",
            description="Record approve, decline or refer with payout and reason.",
            args_schema=DecisionArgs,
        ),
        StructuredTool.from_function(
            pay_claim,
            name="pay_claim",
            description="Pay an approved claim. May be refused until sign-off.",
            args_schema=PayArgs,
        ),
    ]


CLAIM_TOOLS = (
    "get_claim",
    "search_documents",
    "read_section",
    "record_decision",
    "pay_claim",
)

QUEUE_TOOLS = ("list_claims", "write_todos", "work_claim")
MISSED_REMINDERS = 2
STUCK_REASON = "The run stopped before this claim was finished"


def fetch_instructions() -> str:
    """Load the claim agent's instructions from the backend API."""
    with backend() as client:
        response = client.get("/api/instructions")
    response.raise_for_status()
    return response.json()["claim"]


def fetch_queue_instructions() -> str:
    """Load the queue agent's instructions from the backend API."""
    with backend() as client:
        response = client.get("/api/instructions")
    response.raise_for_status()
    return response.json()["queue"]


def _load_claim(claim_id: str) -> dict[str, Any]:
    with backend() as client:
        response = client.get(f"/api/claims/{claim_id}")
    response.raise_for_status()
    return response.json()


def _usd(amount: float) -> str:
    return f"${amount:,.2f}"


def format_report(claim: dict[str, Any]) -> str:
    """Build the one-line report from the claim record, not the model's reply."""
    claim_id = claim["claim_id"]
    decision = claim["decision"]
    if decision:
        payout = float(claim["payout"] or 0)
        line = f"{claim_id}  {decision}  {_usd(payout)}"
        if claim["status"] == "waiting_for_sign_off":
            return f"{line}, waiting for sign-off"
        if decision == "approve" and claim["paid_amount"] is None:
            return f"{line}, not paid"
        return line
    errors = [step["detail"] for step in claim["steps"] if step["tool_name"] == "error"]
    reason = errors[-1] if errors else "The agent finished without recording a decision"
    ending = (
        "left for a handler"
        if claim["status"] == "left_for_handler"
        else "back in the queue"
    )
    return f"{claim_id}  failed: {reason}, {ending}"


def _fail_if_undecided(claim_id: str, reason: str) -> None:
    claim = _load_claim(claim_id)
    if claim["decision"] is not None or claim["status"] != "in_progress":
        return
    with backend() as client:
        client.post(
            f"/api/claims/{claim_id}/failure",
            json={"reason": reason},
        )


def work_claim(claim_id: str, llm: BaseChatModel | None = None) -> str:
    """Work one claim on a new thread and return a one-line report."""
    with backend() as client:
        started = client.post(f"/api/claims/{claim_id}/start")
    if started.status_code >= HTTPStatus.BAD_REQUEST:
        detail = started.json().get("detail", started.text)
        return f"{claim_id}  not started: {started.status_code}: {detail}"
    instructions = fetch_instructions()
    agent = create_agent(
        llm or model(), tools=_tools_for(claim_id), system_prompt=instructions
    )
    thread_id = f"claim-{claim_id}-{uuid.uuid4()}"
    try:
        agent.invoke(
            {"messages": [{"role": "user", "content": f"Work claim {claim_id}."}]},
            config={
                "recursion_limit": STEP_LIMIT,
                "configurable": {"thread_id": thread_id},
            },
        )
    except Exception as exc:
        _fail_if_undecided(claim_id, str(exc))
        return format_report(_load_claim(claim_id))
    _fail_if_undecided(claim_id, "The agent finished without recording a decision")
    return format_report(_load_claim(claim_id))


def _list_queue() -> list[dict[str, Any]]:
    with backend() as client:
        response = client.get("/api/claims")
    response.raise_for_status()
    return response.json()


def recover_stuck_claims(reason: str = STUCK_REASON) -> None:
    """Put claims left in_progress back in the queue, or leave them for a handler."""
    for claim in _list_queue():
        if claim["status"] != "in_progress":
            continue
        with backend() as client:
            client.post(
                f"/api/claims/{claim['claim_id']}/failure",
                json={"reason": reason},
            )


def _waiting_ids() -> list[str]:
    return [
        claim["claim_id"] for claim in _list_queue() if claim["status"] == "waiting"
    ]


def _missed_inside_cap(started: set[str], cap: int) -> list[str]:
    waiting = _waiting_ids()
    if len(started) < cap:
        return waiting
    return [claim_id for claim_id in waiting if claim_id in started]


def _last_ai_text(result: dict[str, Any]) -> str:
    for message in reversed(result.get("messages", [])):
        if getattr(message, "type", None) != "ai":
            continue
        text = getattr(message, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        content = getattr(message, "content", "")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return "Run finished."


def _finish_run(run_id: int, summary: str) -> None:
    with backend() as client:
        client.post(f"/api/runs/{run_id}/finish", json={"summary": summary})


def _queue_tools(
    run_id: int,
    cap: int,
    started: set[str],
    claim_llm: BaseChatModel | None,
) -> list[StructuredTool]:
    class TodoItem(BaseModel):
        content: str = Field(description="The item, naming the claim id when it is one")
        status: str = Field(description="to_do, in_progress, done, or left_for_handler")

    class TodosArgs(BaseModel):
        todos: list[TodoItem]

    class WorkArgs(BaseModel):
        claim_id: str = Field(description="The claim to work, such as CLM-1001")

    def list_claims() -> str:
        return json.dumps(_list_queue())

    def write_todos(todos: list[Any]) -> str:
        payload = []
        for item in todos:
            if isinstance(item, dict):
                payload.append(
                    {
                        "content": item.get("content", ""),
                        "status": item.get("status", ""),
                    }
                )
            else:
                payload.append(item.model_dump())
        with backend() as client:
            response = client.put(
                f"/api/runs/{run_id}/todos",
                json={"todos": payload},
            )
        if response.status_code >= HTTPStatus.BAD_REQUEST:
            return json.dumps({"status": "refused", "detail": response.json()})
        return json.dumps(response.json())

    def work_one(claim_id: str) -> str:
        if claim_id not in started and len(started) >= cap:
            return f"{claim_id}  not started: this run's cap is {cap}"
        report = work_claim(claim_id, claim_llm)
        if "not started" not in report:
            started.add(claim_id)
        print(report)
        return report

    return [
        StructuredTool.from_function(
            list_claims,
            name="list_claims",
            description="List claims in the queue with their statuses.",
        ),
        StructuredTool.from_function(
            write_todos,
            name="write_todos",
            description="Replace this run's to-do list.",
            args_schema=TodosArgs,
        ),
        StructuredTool.from_function(
            work_one,
            name="work_claim",
            description="Hand one claim to a fresh claim agent and get its report.",
            args_schema=WorkArgs,
        ),
    ]


def run_queue(
    cap: int | None = None,
    llm: BaseChatModel | None = None,
    claim_llm: BaseChatModel | None = None,
) -> str:
    """Work waiting claims through a queue agent, up to cap, and return the summary."""
    recover_stuck_claims()
    waiting = _waiting_ids()
    if not waiting:
        print("No claims are waiting")
        return "No claims are waiting"
    limit = cap if cap is not None else max(len(waiting), 1)
    with backend() as client:
        started_run = client.post("/api/runs", json={"cap": limit})
    started_run.raise_for_status()
    run = started_run.json()
    run_id = int(run["id"])
    started: set[str] = set()
    agent = create_agent(
        llm or model(),
        tools=_queue_tools(run_id, limit, started, claim_llm),
        system_prompt=fetch_queue_instructions(),
    )
    messages: list[Any] = [
        {
            "role": "user",
            "content": (
                f"Work the queue. You may start at most {limit} claims this run."
            ),
        }
    ]
    summary = "Run finished."
    reminders = 0
    try:
        while True:
            result = agent.invoke(
                {"messages": messages},
                config={"recursion_limit": STEP_LIMIT},
            )
            summary = _last_ai_text(result)
            leftover = _missed_inside_cap(started, limit)
            if not leftover or reminders >= MISSED_REMINDERS:
                break
            reminders += 1
            named = ", ".join(leftover)
            messages = list(result["messages"]) + [
                {
                    "role": "user",
                    "content": (
                        "These claims are still waiting and fit in the cap: "
                        f"{named}. Work them before you finish."
                    ),
                }
            ]
    except Exception as exc:
        recover_stuck_claims()
        summary = f"The run stopped: {exc}"
    _finish_run(run_id, summary)
    print(summary)
    return summary


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Backward-compatible entry: work one claim and return the report."""
    _ = thread_id
    return work_claim(claim_id, llm)
