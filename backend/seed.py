"""Rebuild the SQLite database from data/: uv run -m backend.seed."""

from __future__ import annotations

from pathlib import Path

from backend import store


def reseed(db_path: Path | str | None = None) -> Path:
    """Delete the database file and seed it again."""
    path = Path(db_path) if db_path is not None else store.default_db_path()
    path.unlink(missing_ok=True)
    wal = path.with_suffix(path.suffix + "-wal")
    shm = path.with_suffix(path.suffix + "-shm")
    wal.unlink(missing_ok=True)
    shm.unlink(missing_ok=True)
    connection = store.init_db(path)
    connection.close()
    return path


def main() -> None:
    path = reseed()
    print(f"Seeded {path}")


if __name__ == "__main__":
    main()
