import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

from opsbot import settings


MIGRATION_FILES = ['001_init.sql']


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


@contextmanager
def get_connection():
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize_database() -> None:
    with get_connection() as conn:
        for filename in MIGRATION_FILES:
            path = settings.MIGRATIONS_DIR / filename
            with open(path, encoding='utf-8') as f:
                conn.executescript(f.read())


def set_system_state(conn: sqlite3.Connection, key: str, value_text: str) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO system_state (key, value_text, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value_text=excluded.value_text, updated_at=excluded.updated_at
        """,
        (key, value_text, now),
    )


def get_system_state(conn: sqlite3.Connection, key: str):
    row = conn.execute(
        'SELECT key, value_text, updated_at FROM system_state WHERE key = ?',
        (key,),
    ).fetchone()
    return row
