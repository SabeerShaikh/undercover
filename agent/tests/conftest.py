"""Shared fixtures: the agent talks to the backend only through agent.api."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent import api as agent_api
from backend import main as backend_main
from backend import store


class ReuseClient:
    """Reuse the fixture TestClient without closing it after each call."""

    def __init__(self, inner: TestClient) -> None:
        self._inner = inner

    def __enter__(self) -> TestClient:
        return self._inner

    def __exit__(self, *args: object) -> None:
        return None


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    connection = store.init_db(tmp_path / "agent.db")
    monkeypatch.setattr(backend_main, "db", connection)
    with TestClient(backend_main.app) as client:
        monkeypatch.setattr(agent_api, "client", lambda: ReuseClient(client))
        yield client
    connection.close()
