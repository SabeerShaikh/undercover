"""Tests for uv run -m agent."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent import __main__ as cli
from agent import main
from backend import main as backend_main
from backend import store


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    connection = store.init_db(tmp_path / "cli.db")
    monkeypatch.setattr(backend_main, "db", connection)
    monkeypatch.setattr(main, "backend", lambda: TestClient(backend_main.app))
    with TestClient(backend_main.app) as client:
        yield client
    connection.close()


def test_waiting_claim_ids(api: TestClient):
    ids = cli.waiting_claim_ids()
    assert "CLM-1001" in ids
    assert len(ids) == 25


def test_main_cli_runs_waiting_claims(api: TestClient, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def fake_run(claim_id: str, thread_id: str, llm=None) -> str:
        calls.append(claim_id)
        api.post(
            f"/api/claims/{claim_id}/decision",
            json={
                "decision": "decline",
                "payout": 0,
                "reason": "CLI stub.",
                "policy_section": "Section 1",
            },
        )
        return f"done {claim_id}"

    monkeypatch.setattr(main, "run", fake_run)
    # Only process the first two waiting claims for a fast test.
    monkeypatch.setattr(cli, "waiting_claim_ids", lambda: ["CLM-1001", "CLM-1002"])
    assert cli.main_cli() == 0
    assert calls == ["CLM-1001", "CLM-1002"]
