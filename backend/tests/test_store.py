"""Tests for the SQLite store and seed."""

from pathlib import Path

from backend import store


def test_seed_lists_25_waiting_claims(tmp_path: Path):
    connection = store.init_db(tmp_path / "test.db")
    claims = store.list_claims(connection)
    assert len(claims) == 25
    assert all(claim["status"] == "waiting" for claim in claims)
    connection.close()


def test_seed_loads_clm_1001(tmp_path: Path):
    connection = store.init_db(tmp_path / "test.db")
    claim = store.get_claim(connection, "CLM-1001")
    assert claim is not None
    assert "Rome" in claim["story"] or "canceled" in claim["story"].lower()
    assert len(claim["items"]) == 3
    assert len(claim["documents"]) >= 1
    assert claim["policy"]["policy_id"] == "POL-2001"
    assert claim["policy"]["plan"] == "premium"
    assert claim["policy"]["trip"]["destination"] == "Rome, Italy"
    assert claim["customer"]["name"] == "Maya Patel"
    assert len(claim["customer"]["previous_claims"]) >= 1
    assert claim["plan"]["name"] == "UnderCover Premium"
    connection.close()


def test_policy_wording_and_limit(tmp_path: Path):
    connection = store.init_db(tmp_path / "test.db")
    wording = store.get_policy_wording(connection)
    assert wording.strip()
    assert "Trip Delay" in wording
    assert store.get_payout_approval_limit(connection) == 1000.0
    instructions = store.get_instructions(connection)
    assert "UnderCover Agent" in instructions
    connection.close()


def test_seed_twice_does_not_duplicate(tmp_path: Path):
    db = tmp_path / "test.db"
    first = store.init_db(db)
    assert len(store.list_claims(first)) == 25
    first.close()
    second = store.init_db(db)
    assert len(store.list_claims(second)) == 25
    second.close()
