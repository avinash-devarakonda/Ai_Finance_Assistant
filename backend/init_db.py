"""Create the MySQL database/tables (or the SQLite test database)."""
from __future__ import annotations

from pathlib import Path

import pymysql

from config import Config, mysql_settings
from database import db


def _split_sql(script: str) -> list[str]:
    lines = []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or stripped.startswith("#"):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    return [statement.strip() for statement in cleaned.split(";") if statement.strip()]


def init_mysql() -> None:
    schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
    script = schema_path.read_text(encoding="utf-8")
    connection = pymysql.connect(**mysql_settings(include_database=False), autocommit=True)
    try:
        cursor = connection.cursor()
        for statement in _split_sql(script):
            cursor.execute(statement)
        cursor.close()
    finally:
        connection.close()


def main() -> None:
    if Config.DB_ENGINE == "sqlite":
        db.init_sqlite()
        print(f"SQLite schema initialized at {Config.SQLITE_PATH}")
        return
    init_mysql()
    print(f"MySQL database '{Config.DB_NAME}' and tables initialized")


if __name__ == "__main__":
    main()
