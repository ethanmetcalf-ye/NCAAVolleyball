"""SQLite connection helper."""

import sqlite3
from pathlib import Path

from src.config import DB_PATH


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open the database with foreign-key enforcement on (SQLite defaults it off)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
