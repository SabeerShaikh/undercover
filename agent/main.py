"""The UnderCover Agent."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

load_dotenv(override=True)

BACKEND_URL = "http://localhost:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-luna"


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or GPT-6 Luna by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
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
            description="Relevant section of the policy wording"
        )

    class PayArgs(BaseModel):
        amount: float = Field(description="Amount to pay in US dollars")

    def get_instructions() -> str:
        _add_step(claim_id, "get_instructions", "Read agent instructions")
        with backend() as client:
            response = client.get("/api/instructions")
        response.raise_for_status()
        return response.json()["text"]

    def get_claim() -> str:
        _add_step(claim_id, "get_claim", f"Read claim {claim_id}")
        with backend() as client:
            response = client.get(f"/api/claims/{claim_id}")
        response.raise_for_status()
        return json.dumps(response.json())

    def get_policy_wording() -> str:
        _add_step(claim_id, "get_policy_wording", "Read policy wording")
        with backend() as client:
            response = client.get("/api/policy-wording")
        response.raise_for_status()
        return response.json()["text"]

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
        response.raise_for_status()
        return json.dumps(response.json())

    def pay(amount: float) -> str:
        _add_step(claim_id, "pay", f"Pay {amount}")
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
            get_instructions,
            name="get_instructions",
            description="Read the agent's instructions.",
        ),
        StructuredTool.from_function(
            get_claim,
            name="get_claim",
            description="Read the full claim, policy, plan and customer history.",
        ),
        StructuredTool.from_function(
            get_policy_wording,
            name="get_policy_wording",
            description="Read the policy wording contract.",
        ),
        StructuredTool.from_function(
            record_decision,
            name="record_decision",
            description="Record approve, decline or refer with payout and reason.",
            args_schema=DecisionArgs,
        ),
        StructuredTool.from_function(
            pay,
            name="pay",
            description="Pay an approved claim. May be refused until sign-off.",
            args_schema=PayArgs,
        ),
    ]


def fetch_instructions() -> str:
    """Load instructions from the backend API."""
    with backend() as client:
        response = client.get("/api/instructions")
    response.raise_for_status()
    return response.json()["text"]


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Run the agent on one claim and return its final reply."""
    with backend() as client:
        client.post(
            f"/api/claims/{claim_id}/status",
            json={"status": "in_progress"},
        ).raise_for_status()
    instructions = fetch_instructions()
    agent = create_agent(
        llm or model(), tools=_tools_for(claim_id), system_prompt=instructions
    )
    result: dict[str, Any] = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Work claim {claim_id}. Read the claim and policy wording, "
                        "decide, record the decision, and pay if you approve."
                    ),
                }
            ]
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].text
