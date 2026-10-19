"""Regression: concurrent step writes must not raise sqlite InterfaceError."""

import concurrent.futures
from pathlib import Path

from backend import store


def test_concurrent_add_step(tmp_path: Path):
    connection = store.init_db(tmp_path / "concurrent.db")

    def write(index: int) -> bool:
        return store.add_step(connection, "CLM-1001", "get_claim", f"step-{index}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(write, range(40)))

    assert all(results)
    claim = store.get_claim(connection, "CLM-1001")
    assert claim is not None
    assert len(claim["steps"]) == 40
    connection.close()
