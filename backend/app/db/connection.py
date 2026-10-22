"""Open the built SQLite file in read-only mode."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from backend.app.config import get_settings


class DatabaseNotReady(RuntimeError):
    """The ingest script has not created the SQLite file yet."""


def database_path() -> Path:
    return Path(get_settings().database_path)


def database_ready() -> bool:
    return database_path().exists()


@contextmanager
def read_connection():
    path = database_path()
    if not path.exists():
        raise DatabaseNotReady(str(path))
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA busy_timeout = 3000")
        yield conn
    finally:
        conn.close()
