"""Agent tools. Run state comes from LangChain ToolRuntime, not closures."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus

from langchain.tools import ToolRuntime, tool
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from agent import api
from backend.documents import DOCUMENT_LABELS


@dataclass
class ClaimContext:
    claim_id: str


@dataclass
class RunContext:
    run_id: int
    cap: int
    started: set[str]
    work: Callable[[str, BaseChatModel | None], str]
    claim_llm: BaseChatModel | None = None


class TodoItem(BaseModel):
    content: str = Field(description="The item, naming the claim id when it is one")
    status: str = Field(description="to_do, in_progress, done, or left_for_handler")


@tool
def get_claim(runtime: ToolRuntime[ClaimContext]) -> str:
    """Read the full claim, policy, plan and customer history."""
    claim_id = runtime.context.claim_id
    api.add_step(claim_id, "get_claim", f"Read claim {claim_id}")
    return json.dumps(api.get_claim(claim_id))


@tool
def search_documents(query: str, runtime: ToolRuntime[ClaimContext]) -> str:
    """Search the policy wording and claims manual."""
    api.add_step(runtime.context.claim_id, "search_documents", query)
    return api.as_json(api.search_documents(query))


@tool
def read_section(document: str, number: int, runtime: ToolRuntime[ClaimContext]) -> str:
    """Read one numbered section of the wording or the manual."""
    claim_id = runtime.context.claim_id
    api.add_step(claim_id, "read_section", f"{document} {number}")
    response = api.read_section(document, number)
    if response.status_code >= HTTPStatus.BAD_REQUEST:
        return api.as_json(response)
    data = response.json()
    label = DOCUMENT_LABELS.get(document, document)
    api.add_step(
        claim_id,
        "reading",
        f"{label}, section {data['number']}: {data['title']}",
    )
    return json.dumps(data)


@tool
def record_decision(
    decision: str,
    payout: float,
    reason: str,
    policy_section: str,
    runtime: ToolRuntime[ClaimContext],
) -> str:
    """Record approve, decline or refer with payout and reason."""
    claim_id = runtime.context.claim_id
    api.add_step(claim_id, "record_decision", f"{decision} payout={payout}")
    return api.as_json(
        api.record_decision(claim_id, decision, payout, reason, policy_section)
    )


@tool
def pay_claim(amount: float, runtime: ToolRuntime[ClaimContext]) -> str:
    """Pay an approved claim. May be refused until sign-off."""
    claim_id = runtime.context.claim_id
    api.add_step(claim_id, "pay_claim", f"Pay {amount}")
    response = api.pay_claim(claim_id, amount)
    if response.status_code == HTTPStatus.CONFLICT:
        return json.dumps({"status": "refused", "detail": response.json()})
    response.raise_for_status()
    return json.dumps(response.json())


@tool
def list_claims() -> str:
    """List claims in the queue with their statuses."""
    return json.dumps(api.list_claims())


@tool
def write_todos(todos: list[TodoItem], runtime: ToolRuntime[RunContext]) -> str:
    """Replace this run's to-do list."""
    payload = [item.model_dump() for item in todos]
    return api.as_json(api.write_todos(runtime.context.run_id, payload))


@tool("work_claim")
def work_one(claim_id: str, runtime: ToolRuntime[RunContext]) -> str:
    """Hand one claim to a fresh claim agent and get its report."""
    context = runtime.context
    if claim_id not in context.started and len(context.started) >= context.cap:
        return f"{claim_id}  not started: this run's cap is {context.cap}"
    report = context.work(claim_id, context.claim_llm)
    if "not started" not in report:
        context.started.add(claim_id)
    print(report)
    return report


CLAIM_TOOLS = (
    get_claim,
    search_documents,
    read_section,
    record_decision,
    pay_claim,
)
QUEUE_TOOLS = (list_claims, write_todos, work_one)
