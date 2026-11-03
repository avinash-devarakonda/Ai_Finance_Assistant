"""Database access layer supporting MySQL in production and SQLite for local tests.

The application defaults to MySQL. Setting DB_ENGINE=sqlite is an explicit
development-only convenience for automated smoke tests on machines without a
MySQL server; the MySQL schema in database/schema.sql remains the source of
truth for the delivered application.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import pymysql
from pymysql.cursors import DictCursor

from config import Config, mysql_settings

try:  # Python 3.11+
    from datetime import UTC  # type: ignore
except ImportError:  # pragma: no cover
    UTC = None

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('Income', 'Expense')),
    category TEXT NOT NULL,
    merchant TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date);
CREATE TABLE IF NOT EXISTS budgets (
    budget_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    month TEXT NOT NULL,
    category TEXT NOT NULL,
    limit_amount REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, month, category),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    transaction_id INTEGER,
    predicted_category TEXT NOT NULL,
    confidence REAL NOT NULL,
    corrected_category TEXT,
    was_corrected INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS insights (
    insight_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    insight_text TEXT NOT NULL,
    insight_type TEXT NOT NULL DEFAULT 'info',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
"""


def _is_sqlite() -> bool:
    return Config.DB_ENGINE == "sqlite"


def _sqlite_path() -> str:
    path = Path(Config.SQLITE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _translate(query: str) -> str:
    """Translate MySQL %s placeholders to SQLite qmark placeholders."""
    if _is_sqlite():
        return query.replace("%s", "?")
    return query


def _clean_row(row: Any) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return {key: _clean_row(value) for key, value in row.items()}
    if isinstance(row, (list, tuple)):
        return type(row)(_clean_row(value) for value in row)
    if hasattr(row, "isoformat") and not isinstance(row, str):
        return row.isoformat()
    if isinstance(row, bytes):
        return row.decode("utf-8", errors="ignore")
    return row


class Database:
    """Small connection-per-operation wrapper with dict rows."""

    def __init__(self) -> None:
        self.engine = Config.DB_ENGINE

    @contextmanager
    def connection(self) -> Iterable[Any]:
        if _is_sqlite():
            connection = sqlite3.connect(_sqlite_path(), timeout=30)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            try:
                yield connection
            finally:
                connection.close()
        else:
            connection = pymysql.connect(**mysql_settings(), cursorclass=DictCursor)
            try:
                yield connection
            finally:
                connection.close()

    def fetch_all(self, query: str, params: tuple | list | None = None) -> list[dict]:
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(_translate(query), params or ())
            rows = cursor.fetchall()
            cursor.close()
            result = [dict(row) for row in rows]
            return [_clean_row(row) for row in result]

    def fetch_one(self, query: str, params: tuple | list | None = None) -> dict | None:
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(_translate(query), params or ())
            row = cursor.fetchone()
            cursor.close()
            return _clean_row(dict(row)) if row else None

    def execute(
        self,
        query: str,
        params: tuple | list | None = None,
        *,
        commit: bool = True,
        return_id: bool = False,
    ) -> int | None:
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(_translate(query), params or ())
            inserted_id = cursor.lastrowid
            if commit:
                connection.commit()
            cursor.close()
            return int(inserted_id) if return_id and inserted_id is not None else None

    def execute_many(self, query: str, rows: Iterable[tuple]) -> None:
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.executemany(_translate(query), list(rows))
            connection.commit()
            cursor.close()

    def init_sqlite(self) -> None:
        if not _is_sqlite():
            return
        with self.connection() as connection:
            connection.executescript(SQLITE_SCHEMA)
            connection.commit()

    def healthcheck(self) -> bool:
        try:
            row = self.fetch_one("SELECT 1 AS ok")
            return bool(row and row.get("ok") == 1)
        except Exception:
            return False


db = Database()


def row_to_dict(row: Any) -> dict | None:
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(row)


def build_in_clause(count: int) -> str:
    if count < 1:
        raise ValueError("IN clause requires at least one value")
    return ",".join(["%s"] * count)


def normalize_date(value: str) -> str:
    """Validate and return YYYY-MM-DD."""
    if not value:
        raise ValueError("Date is required")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise ValueError("Date must use YYYY-MM-DD format")
    return value
