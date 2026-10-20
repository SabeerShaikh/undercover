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


def test_main_cli_runs_the_queue(api: TestClient, monkeypatch: pytest.MonkeyPatch):
    caps: list[int | None] = []

    def fake_queue(cap: int | None = None, llm=None, claim_llm=None) -> str:
        caps.append(cap)
        return "queued"

    monkeypatch.setattr(main, "run_queue", fake_queue)
    assert cli.main_cli([]) == 0
    assert caps == [None]
