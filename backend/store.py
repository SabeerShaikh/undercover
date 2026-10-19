"""SQLite store for UnderCover claims records."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def default_db_path() -> Path:
    """Return the SQLite path from UNDERCOVER_DB or undercover.db at the repo root."""
    return Path(os.environ.get("UNDERCOVER_DB", str(ROOT / "undercover.db")))


DEFAULT_INSTRUCTIONS = """\
You are the UnderCover Agent. You decide travel insurance claims.

For each claim you are given:
1. Read your instructions, the claim (story, items, documents), the customer's \
policy and claim history, the plan limits, and the policy wording.
2. Decide to approve, decline, or refer. Approve only when the policy wording \
covers the loss; decline when it does not; refer when you need judgment or more \
information the wording does not settle.
3. When you approve, work out the payout from the plan limits, deductibles, and \
wording (supplier refunds taken off first where the wording says so).
4. Record the decision with a payout (0 when not approving), a reason in two or \
three sentences, and the relevant section of the policy wording.
5. After an approve, call pay with that payout. If pay is refused because the \
claim is waiting for sign-off, leave it; a handler will finish payment.
6. Base decisions only on the policy wording and the records the API returns. \
Do not invent coverage. Amounts are in US dollars.
"""


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open the database with row access by column name."""
    connection = sqlite3.connect(
        str(db_path if db_path is not None else default_db_path()),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create tables if needed, seed once from data/, and return a connection."""
    connection = connect(db_path)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS company (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS plans (
            plan TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS policies (
            policy_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS claims (
            claim_id TEXT PRIMARY KEY,
            policy_id TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            amount_claimed REAL NOT NULL,
            status TEXT NOT NULL,
            decision TEXT,
            payout REAL,
            reason TEXT,
            policy_section TEXT,
            signed_off INTEGER NOT NULL DEFAULT 0,
            paid_amount REAL,
            data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS policy_wording (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            text TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS instructions (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            text TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            detail TEXT NOT NULL,
            FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
        );
        """
    )
    connection.commit()
    if not _seeded(connection):
        seed(connection)
    return connection


def _seeded(connection: sqlite3.Connection) -> bool:
    row = connection.execute("SELECT COUNT(*) AS n FROM claims").fetchone()
    return bool(row and row["n"] > 0)


def seed(connection: sqlite3.Connection, data_dir: Path = DATA) -> None:
    """Load seed files into an empty database."""
    company = json.loads((data_dir / "company.json").read_text(encoding="utf-8"))
    plans_doc = json.loads((data_dir / "plans.json").read_text(encoding="utf-8"))
    policies = json.loads((data_dir / "policies.json").read_text(encoding="utf-8"))
    customers = json.loads((data_dir / "customers.json").read_text(encoding="utf-8"))
    claims = json.loads((data_dir / "claims.json").read_text(encoding="utf-8"))
    wording = (data_dir / "policy_wording.md").read_text(encoding="utf-8")

    connection.execute(
        "INSERT INTO company (id, data) VALUES (1, ?)",
        (json.dumps(company),),
    )
    for plan in plans_doc["plans"]:
        connection.execute(
            "INSERT INTO plans (plan, data) VALUES (?, ?)",
            (plan["plan"], json.dumps(plan)),
        )
    for policy in policies:
        connection.execute(
            "INSERT INTO policies (policy_id, data) VALUES (?, ?)",
            (policy["policy_id"], json.dumps(policy)),
        )
    for customer in customers:
        connection.execute(
            "INSERT INTO customers (customer_id, data) VALUES (?, ?)",
            (customer["customer_id"], json.dumps(customer)),
        )
    for claim in claims:
        connection.execute(
            """
            INSERT INTO claims (
                claim_id, policy_id, customer_id, summary, amount_claimed,
                status, data
            ) VALUES (?, ?, ?, ?, ?, 'waiting', ?)
            """,
            (
                claim["claim_id"],
                claim["policy_id"],
                claim["customer_id"],
                claim["summary"],
                claim["amount_claimed"],
                json.dumps(claim),
            ),
        )
    connection.execute(
        "INSERT INTO policy_wording (id, text) VALUES (1, ?)",
        (wording,),
    )
    connection.execute(
        "INSERT INTO instructions (id, text) VALUES (1, ?)",
        (DEFAULT_INSTRUCTIONS,),
    )
    connection.commit()


def list_claims(connection: sqlite3.Connection) -> list[dict]:
    """Return queue rows with customer names."""
    rows = connection.execute(
        """
        SELECT c.claim_id, c.summary, c.amount_claimed, c.status, cu.data AS customer
        FROM claims c
        JOIN customers cu ON cu.customer_id = c.customer_id
        ORDER BY c.claim_id
        """
    ).fetchall()
    result = []
    for row in rows:
        customer = json.loads(row["customer"])
        result.append(
            {
                "claim_id": row["claim_id"],
                "summary": row["summary"],
                "amount_claimed": row["amount_claimed"],
                "status": row["status"],
                "customer_name": customer["name"],
            }
        )
    return result


def get_claim(connection: sqlite3.Connection, claim_id: str) -> dict | None:
    """Return one claim with policy, plan, customer, decision fields and steps."""
    row = connection.execute(
        "SELECT * FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return None
    claim = json.loads(row["data"])
    policy_row = connection.execute(
        "SELECT data FROM policies WHERE policy_id = ?",
        (row["policy_id"],),
    ).fetchone()
    customer_row = connection.execute(
        "SELECT data FROM customers WHERE customer_id = ?",
        (row["customer_id"],),
    ).fetchone()
    if policy_row is None or customer_row is None:
        return None
    policy = json.loads(policy_row["data"])
    customer = json.loads(customer_row["data"])
    plan_row = connection.execute(
        "SELECT data FROM plans WHERE plan = ?",
        (policy["plan"],),
    ).fetchone()
    plan = json.loads(plan_row["data"]) if plan_row else None
    steps = [
        {"tool_name": step["tool_name"], "detail": step["detail"]}
        for step in connection.execute(
            """
            SELECT tool_name, detail FROM steps
            WHERE claim_id = ? ORDER BY id
            """,
            (claim_id,),
        ).fetchall()
    ]
    return {
        **claim,
        "status": row["status"],
        "decision": row["decision"],
        "payout": row["payout"],
        "reason": row["reason"],
        "policy_section": row["policy_section"],
        "signed_off": bool(row["signed_off"]),
        "paid_amount": row["paid_amount"],
        "policy": policy,
        "plan": plan,
        "customer": customer,
        "steps": steps,
    }


def get_policy_wording(connection: sqlite3.Connection) -> str:
    """Return the policy wording markdown."""
    row = connection.execute("SELECT text FROM policy_wording WHERE id = 1").fetchone()
    return row["text"] if row else ""


def get_instructions(connection: sqlite3.Connection) -> str:
    """Return the agent's instructions."""
    row = connection.execute("SELECT text FROM instructions WHERE id = 1").fetchone()
    return row["text"] if row else ""


def get_payout_approval_limit(connection: sqlite3.Connection) -> float:
    """Return the company payout approval limit."""
    row = connection.execute("SELECT data FROM company WHERE id = 1").fetchone()
    if row is None:
        return 1000.0
    return float(json.loads(row["data"])["payout_approval_limit"])


def set_status(connection: sqlite3.Connection, claim_id: str, status: str) -> bool:
    """Set claim status. in_progress is allowed only from waiting."""
    row = connection.execute(
        "SELECT status FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return False
    if status == "in_progress" and row["status"] != "waiting":
        return False
    connection.execute(
        "UPDATE claims SET status = ? WHERE claim_id = ?",
        (status, claim_id),
    )
    connection.commit()
    return True


def record_decision(
    connection: sqlite3.Connection,
    claim_id: str,
    fields: dict,
) -> str | None:
    """Record a decision. Returns the new status, or None if the claim is missing."""
    row = connection.execute(
        "SELECT claim_id FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return None
    decision = fields["decision"]
    payout = float(fields["payout"])
    limit = get_payout_approval_limit(connection)
    if decision == "approve" and payout > limit:
        status = "waiting_for_sign_off"
    else:
        status = "decided"
    connection.execute(
        """
        UPDATE claims
        SET decision = ?, payout = ?, reason = ?, policy_section = ?,
            status = ?, signed_off = 0, paid_amount = NULL
        WHERE claim_id = ?
        """,
        (
            decision,
            payout,
            fields["reason"],
            fields["policy_section"],
            status,
            claim_id,
        ),
    )
    connection.commit()
    return status


def sign_off(connection: sqlite3.Connection, claim_id: str) -> bool:
    """Mark a claim waiting for sign-off as signed off."""
    row = connection.execute(
        "SELECT status FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None or row["status"] != "waiting_for_sign_off":
        return False
    connection.execute(
        "UPDATE claims SET signed_off = 1 WHERE claim_id = ?",
        (claim_id,),
    )
    connection.commit()
    return True


def pay(
    connection: sqlite3.Connection, claim_id: str, amount: float
) -> tuple[bool, str]:
    """Pay an approved claim. Fails when sign-off is still required or already paid."""
    row = connection.execute(
        """
        SELECT decision, status, signed_off, paid_amount
        FROM claims WHERE claim_id = ?
        """,
        (claim_id,),
    ).fetchone()
    if row is None:
        return False, "not_found"
    if row["decision"] != "approve":
        return False, "not_approved"
    if row["paid_amount"] is not None:
        return False, "already_paid"
    if row["status"] == "waiting_for_sign_off" and not row["signed_off"]:
        return False, "waiting_for_sign_off"
    connection.execute(
        """
        UPDATE claims
        SET paid_amount = ?, status = 'decided'
        WHERE claim_id = ?
        """,
        (amount, claim_id),
    )
    connection.commit()
    return True, "ok"


def add_step(
    connection: sqlite3.Connection, claim_id: str, tool_name: str, detail: str
) -> bool:
    """Append an agent step for a claim."""
    row = connection.execute(
        "SELECT claim_id FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return False
    connection.execute(
        "INSERT INTO steps (claim_id, tool_name, detail) VALUES (?, ?, ?)",
        (claim_id, tool_name, detail),
    )
    connection.commit()
    return True
