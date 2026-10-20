"""SQLite store for UnderCover claims records."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INSTRUCTIONS_DIR = Path(__file__).resolve().parent / "instructions"
_lock = threading.RLock()

MAX_ATTEMPTS = 2
TODO_STATUSES = ("to_do", "in_progress", "done", "left_for_handler")


def _synced[F: Callable[..., object]](fn: F) -> F:
    """Serialize access: one sqlite3 connection is shared across request threads."""

    @wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> object:
        with _lock:
            return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def default_db_path() -> Path:
    """Return the SQLite path from UNDERCOVER_DB or undercover.db at the repo root."""
    return Path(os.environ.get("UNDERCOVER_DB", str(ROOT / "undercover.db")))


def instruction_text(role: str) -> str:
    """Return the instruction file for the queue or claim agent."""
    return (INSTRUCTIONS_DIR / f"{role}.md").read_text(encoding="utf-8")


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open the database with row access by column name."""
    connection = sqlite3.connect(
        str(db_path if db_path is not None else default_db_path()),
        check_same_thread=False,
        timeout=30,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


@_synced
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
            attempts INTEGER NOT NULL DEFAULT 0,
            data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS policy_wording (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            text TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS claims_manual (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            text TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS instructions (
            role TEXT PRIMARY KEY,
            text TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            detail TEXT NOT NULL,
            FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
        );
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cap INTEGER NOT NULL,
            status TEXT NOT NULL,
            summary TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        );
        """
    )
    connection.commit()
    _migrate_schema(connection)
    if not _seeded(connection):
        seed(connection)
    _backfill_documents(connection)
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if table == "instructions":
        rows = connection.execute("PRAGMA table_info(instructions)").fetchall()
    elif table == "claims":
        rows = connection.execute("PRAGMA table_info(claims)").fetchall()
    else:
        raise ValueError(table)
    return {row[1] for row in rows}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _migrate_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS claims_manual (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            text TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cap INTEGER NOT NULL,
            status TEXT NOT NULL,
            summary TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        )
        """
    )
    columns = _table_columns(connection, "instructions")
    if "role" not in columns:
        connection.execute("DROP TABLE IF EXISTS instructions")
        connection.execute(
            """
            CREATE TABLE instructions (
                role TEXT PRIMARY KEY,
                text TEXT NOT NULL
            )
            """
        )
    claim_columns = _table_columns(connection, "claims")
    if "attempts" not in claim_columns:
        connection.execute(
            "ALTER TABLE claims ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"
        )
    connection.commit()


def _backfill_documents(connection: sqlite3.Connection, data_dir: Path = DATA) -> None:
    if connection.execute("SELECT 1 FROM claims_manual").fetchone() is None:
        manual = (data_dir / "claims_manual.md").read_text(encoding="utf-8")
        connection.execute(
            "INSERT INTO claims_manual (id, text) VALUES (1, ?)",
            (manual,),
        )
    if connection.execute("SELECT 1 FROM instructions").fetchone() is None:
        for role in ("queue", "claim"):
            connection.execute(
                "INSERT INTO instructions (role, text) VALUES (?, ?)",
                (role, instruction_text(role)),
            )
    connection.commit()


def _seeded(connection: sqlite3.Connection) -> bool:
    row = connection.execute("SELECT COUNT(*) AS n FROM claims").fetchone()
    return bool(row and row["n"] > 0)


@_synced
def seed(connection: sqlite3.Connection, data_dir: Path = DATA) -> None:
    """Load seed files into an empty database."""
    company = json.loads((data_dir / "company.json").read_text(encoding="utf-8"))
    plans_doc = json.loads((data_dir / "plans.json").read_text(encoding="utf-8"))
    policies = json.loads((data_dir / "policies.json").read_text(encoding="utf-8"))
    customers = json.loads((data_dir / "customers.json").read_text(encoding="utf-8"))
    claims = json.loads((data_dir / "claims.json").read_text(encoding="utf-8"))
    wording = (data_dir / "policy_wording.md").read_text(encoding="utf-8")
    manual = (data_dir / "claims_manual.md").read_text(encoding="utf-8")

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
        "INSERT INTO claims_manual (id, text) VALUES (1, ?)",
        (manual,),
    )
    for role in ("queue", "claim"):
        connection.execute(
            "INSERT INTO instructions (role, text) VALUES (?, ?)",
            (role, instruction_text(role)),
        )
    connection.commit()


@_synced
def list_claims(connection: sqlite3.Connection) -> list[dict]:
    """Return queue rows with customer names, decision and payout."""
    rows = connection.execute(
        """
        SELECT c.claim_id, c.summary, c.amount_claimed, c.status,
               c.decision, c.payout, cu.data AS customer
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
                "decision": row["decision"],
                "payout": row["payout"],
                "customer_name": customer["name"],
            }
        )
    return result


@_synced
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
        "attempts": row["attempts"],
        "policy": policy,
        "plan": plan,
        "customer": customer,
        "steps": steps,
    }


@_synced
def get_policy_wording(connection: sqlite3.Connection) -> str:
    """Return the policy wording markdown."""
    row = connection.execute("SELECT text FROM policy_wording WHERE id = 1").fetchone()
    return row["text"] if row else ""


@_synced
def get_claims_manual(connection: sqlite3.Connection) -> str:
    """Return the claims manual markdown."""
    row = connection.execute("SELECT text FROM claims_manual WHERE id = 1").fetchone()
    return row["text"] if row else ""


@_synced
def get_document(connection: sqlite3.Connection, name: str) -> str | None:
    """Return one stored document, or None if the name is unknown."""
    if name == "policy_wording":
        text = get_policy_wording(connection)
        return text or None
    if name == "claims_manual":
        text = get_claims_manual(connection)
        return text or None
    return None


@_synced
def get_instructions(connection: sqlite3.Connection) -> dict[str, str]:
    """Return the queue and claim instruction texts."""
    rows = connection.execute("SELECT role, text FROM instructions").fetchall()
    return {row["role"]: row["text"] for row in rows}


@_synced
def get_payout_approval_limit(connection: sqlite3.Connection) -> float:
    """Return the company payout approval limit."""
    row = connection.execute("SELECT data FROM company WHERE id = 1").fetchone()
    if row is None:
        return 1000.0
    return float(json.loads(row["data"])["payout_approval_limit"])


@_synced
def set_status(connection: sqlite3.Connection, claim_id: str, status: str) -> bool:
    """Set claim status. in_progress and waiting are allowed from either of those."""
    row = connection.execute(
        "SELECT status FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return False
    if status == "in_progress" and row["status"] not in ("waiting", "in_progress"):
        return False
    if status == "waiting" and row["status"] not in ("waiting", "in_progress"):
        return False
    connection.execute(
        "UPDATE claims SET status = ? WHERE claim_id = ?",
        (status, claim_id),
    )
    connection.commit()
    return True


@_synced
def record_decision(
    connection: sqlite3.Connection,
    claim_id: str,
    fields: dict,
) -> str | None:
    """Record a decision. Returns the new status, or None if the claim is missing."""
    row = connection.execute(
        "SELECT claim_id, decision FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return None
    if row["decision"] is not None:
        return "already_decided"
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


@_synced
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


@_synced
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


@_synced
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


@_synced
def start_claim(
    connection: sqlite3.Connection, claim_id: str
) -> tuple[bool, str | int]:
    """Move a waiting claim to in_progress and add one attempt."""
    row = connection.execute(
        "SELECT status, attempts FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return False, "not_found"
    if row["status"] != "waiting":
        return False, "not_waiting"
    attempts = int(row["attempts"]) + 1
    connection.execute(
        """
        UPDATE claims SET status = 'in_progress', attempts = ?
        WHERE claim_id = ?
        """,
        (attempts, claim_id),
    )
    connection.commit()
    return True, attempts


@_synced
def fail_claim(
    connection: sqlite3.Connection, claim_id: str, reason: str
) -> tuple[bool, str]:
    """Record a failed attempt and put the claim back, or leave it for a handler."""
    row = connection.execute(
        "SELECT status, decision, attempts FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return False, "not_found"
    if row["status"] != "in_progress" or row["decision"] is not None:
        return False, "not_in_progress"
    add_step(connection, claim_id, "error", reason)
    status = "left_for_handler" if int(row["attempts"]) >= MAX_ATTEMPTS else "waiting"
    connection.execute(
        "UPDATE claims SET status = ? WHERE claim_id = ?",
        (status, claim_id),
    )
    connection.commit()
    return True, status


def _todos_for(connection: sqlite3.Connection, run_id: int) -> list[dict]:
    rows = connection.execute(
        """
        SELECT content, status FROM todos
        WHERE run_id = ? ORDER BY position
        """,
        (run_id,),
    ).fetchall()
    return [{"content": row["content"], "status": row["status"]} for row in rows]


def _run_payload(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "cap": row["cap"],
        "status": row["status"],
        "summary": row["summary"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "todos": _todos_for(connection, row["id"]),
    }


@_synced
def get_latest_run(connection: sqlite3.Connection) -> dict | None:
    """Return the newest run with its to-do list, or None."""
    row = connection.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    return _run_payload(connection, row)


@_synced
def start_run(connection: sqlite3.Connection, cap: int) -> tuple[dict | None, str]:
    """Start a run with an empty to-do list."""
    if cap < 1:
        return None, "invalid_cap"
    running = connection.execute(
        "SELECT 1 FROM runs WHERE status = 'running'"
    ).fetchone()
    if running is not None:
        return None, "run_in_progress"
    cursor = connection.execute(
        "INSERT INTO runs (cap, status, started_at) VALUES (?, 'running', ?)",
        (cap, _now()),
    )
    connection.commit()
    row = connection.execute(
        "SELECT * FROM runs WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    if row is None:
        return None, "not_found"
    return _run_payload(connection, row), "ok"


@_synced
def write_todos(connection: sqlite3.Connection, run_id: int, todos: list[dict]) -> str:
    """Replace the to-do list of a running run."""
    row = connection.execute(
        "SELECT status FROM runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return "not_found"
    if row["status"] != "running":
        return "not_running"
    for item in todos:
        content = str(item.get("content", "")).strip()
        status = item.get("status")
        if not content or status not in TODO_STATUSES:
            return "invalid"
    connection.execute("DELETE FROM todos WHERE run_id = ?", (run_id,))
    for position, item in enumerate(todos):
        connection.execute(
            """
            INSERT INTO todos (run_id, position, content, status)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, position, item["content"], item["status"]),
        )
    connection.commit()
    return "ok"


@_synced
def finish_run(connection: sqlite3.Connection, run_id: int, summary: str) -> str:
    """Mark a running run finished with a handler summary."""
    if not summary.strip():
        return "invalid"
    row = connection.execute(
        "SELECT status FROM runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return "not_found"
    if row["status"] != "running":
        return "not_running"
    connection.execute(
        """
        UPDATE runs SET status = 'finished', summary = ?, finished_at = ?
        WHERE id = ?
        """,
        (summary, _now(), run_id),
    )
    connection.commit()
    return "ok"
