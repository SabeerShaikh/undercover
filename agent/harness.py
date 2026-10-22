"""The agent harness: cap, retries, missed claims, and failure handling."""

from __future__ import annotations

import os
import uuid
from http import HTTPStatus
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agent import api
from agent.tools import CLAIM_TOOLS, QUEUE_TOOLS, ClaimContext, RunContext

load_dotenv(override=True)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
MODEL_TIMEOUT = 120
MODEL_RETRIES = 5
STEP_LIMIT = 60
MISSED_REMINDERS = 2
STUCK_REASON = "The run stopped before this claim was finished"


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
    claim = api.get_claim(claim_id)
    if claim["decision"] is not None or claim["status"] != "in_progress":
        return
    api.fail_claim(claim_id, reason)


def work_claim(claim_id: str, llm: BaseChatModel | None = None) -> str:
    """Work one claim on a new thread and return a one-line report."""
    started = api.start_claim(claim_id)
    if started.status_code >= HTTPStatus.BAD_REQUEST:
        detail = started.json().get("detail", started.text)
        return f"{claim_id}  not started: {started.status_code}: {detail}"
    agent = create_agent(
        llm or model(),
        tools=list(CLAIM_TOOLS),
        system_prompt=api.claim_instructions(),
        context_schema=ClaimContext,
    )
    thread_id = f"claim-{claim_id}-{uuid.uuid4()}"
    try:
        agent.invoke(
            {"messages": [{"role": "user", "content": f"Work claim {claim_id}."}]},
            context=ClaimContext(claim_id=claim_id),
            config={
                "recursion_limit": STEP_LIMIT,
                "configurable": {"thread_id": thread_id},
            },
        )
    except Exception as exc:
        _fail_if_undecided(claim_id, str(exc))
        return format_report(api.get_claim(claim_id))
    _fail_if_undecided(claim_id, "The agent finished without recording a decision")
    return format_report(api.get_claim(claim_id))


def recover_stuck_claims(reason: str = STUCK_REASON) -> None:
    """Put claims left in_progress back in the queue, or leave them for a handler."""
    for claim in api.list_claims():
        if claim["status"] != "in_progress":
            continue
        api.fail_claim(claim["claim_id"], reason)


def waiting_ids() -> list[str]:
    """Return claim ids that are still waiting in the queue."""
    return [
        claim["claim_id"] for claim in api.list_claims() if claim["status"] == "waiting"
    ]


def _missed_inside_cap(started: set[str], cap: int) -> list[str]:
    waiting = waiting_ids()
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


def _run_until_done(agent: Any, messages: list[Any], context: RunContext) -> str:
    reminders = 0
    pending = messages
    summary = "Run finished."
    while True:
        result = agent.invoke(
            {"messages": pending},
            context=context,
            config={"recursion_limit": STEP_LIMIT},
        )
        summary = _last_ai_text(result)
        leftover = _missed_inside_cap(context.started, context.cap)
        if not leftover or reminders >= MISSED_REMINDERS:
            return summary
        reminders += 1
        named = ", ".join(leftover)
        pending = list(result["messages"]) + [
            {
                "role": "user",
                "content": (
                    "These claims are still waiting and fit in the cap: "
                    f"{named}. Work them before you finish."
                ),
            }
        ]


def run_queue(
    cap: int | None = None,
    llm: BaseChatModel | None = None,
    claim_llm: BaseChatModel | None = None,
) -> str:
    """Work waiting claims through a queue agent, up to cap, and return the summary."""
    recover_stuck_claims()
    waiting = waiting_ids()
    if not waiting:
        print("No claims are waiting")
        return "No claims are waiting"
    limit = cap if cap is not None else max(len(waiting), 1)
    run = api.start_run(limit)
    run_id = int(run["id"])
    context = RunContext(
        run_id=run_id,
        cap=limit,
        started=set(),
        work=work_claim,
        claim_llm=claim_llm,
    )
    agent = create_agent(
        llm or model(),
        tools=list(QUEUE_TOOLS),
        system_prompt=api.queue_instructions(),
        context_schema=RunContext,
    )
    messages: list[Any] = [
        {
            "role": "user",
            "content": (
                f"Work the queue. You may start at most {limit} claims this run."
            ),
        }
    ]
    try:
        summary = _run_until_done(agent, messages, context)
    except Exception as exc:
        recover_stuck_claims()
        summary = f"The run stopped: {exc}"
    api.finish_run(run_id, summary)
    print(summary)
    return summary


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Backward-compatible entry: work one claim and return the report."""
    _ = thread_id
    return work_claim(claim_id, llm)
