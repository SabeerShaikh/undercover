"""Tests for splitting, searching and reading the wording and the manual."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import documents, main, store


def test_split_counts_and_titles(tmp_path: Path):
    connection = store.init_db(tmp_path / "docs.db")
    wording = documents.split_sections(store.get_policy_wording(connection))
    manual = documents.split_sections(store.get_claims_manual(connection))
    assert len(wording) == 12
    assert wording[2]["number"] == 3
    assert wording[2]["title"] == "Trip Delay"
    assert len(manual) == 14
    assert manual[8]["number"] == 9
    assert manual[8]["title"] == "Repeat claims"
    connection.close()


def test_read_and_search_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    connection = store.init_db(tmp_path / "docs-api.db")
    monkeypatch.setattr(main, "db", connection)
    with TestClient(main.app) as client:
        manual_9 = client.get("/api/documents/claims_manual/sections/9")
        assert manual_9.status_code == 200
        body = manual_9.json()
        assert body["number"] == 9
        assert body["title"] == "Repeat claims"
        assert body["text"].startswith("Before deciding any claim")

        delay = client.get("/api/documents/policy_wording/sections/3")
        assert delay.status_code == 200
        assert delay.json()["title"] == "Trip Delay"
        assert "Baggage Delay" not in delay.json()["text"]

        wording_13 = client.get("/api/documents/policy_wording/sections/13")
        assert wording_13.status_code == 404
        manual_15 = client.get("/api/documents/claims_manual/sections/15")
        assert manual_15.status_code == 404
        handbook = client.get("/api/documents/handbook/sections/1")
        assert handbook.status_code == 422

        wild = client.get("/api/documents/search", params={"query": "wild animal"})
        assert wild.status_code == 200
        hits = wild.json()
        assert len(hits) == 1
        assert hits[0]["document"] == "claims_manual"
        assert hits[0]["number"] == 7
        assert hits[0]["title"] == "Interpretation notes"
        assert any(p.startswith("**Wild animals.**") for p in hits[0]["paragraphs"])

        giraffe = client.get("/api/documents/search", params={"query": "GIRAFFE"})
        assert giraffe.json()[0]["number"] == 7

        empty = client.get("/api/documents/search", params={"query": "zeppelin"})
        assert empty.json() == []

        missing = client.get("/api/documents/search", params={"query": ""})
        assert missing.status_code == 422

        instructions = client.get("/api/instructions")
        assert instructions.status_code == 200
        payload = instructions.json()
        assert "queue" in payload
        assert "claim" in payload
        assert "3. Trip Delay" in payload["claim"]
        assert "9. Repeat claims" in payload["claim"]
        assert "Unattended means out of your sight" not in payload["claim"]
        assert "Monkeys, gulls, bears, giraffes" not in payload["claim"]
    connection.close()
