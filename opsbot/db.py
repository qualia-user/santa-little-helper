import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

from opsbot import settings


MIGRATION_FILES = ['001_init.sql']
DB_BUSY_TIMEOUT_MS = 30000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute(f'PRAGMA busy_timeout = {DB_BUSY_TIMEOUT_MS}')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')


def create_connection() -> sqlite3.Connection:
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH, timeout=30)
    _configure_connection(conn)
    return conn


@contextmanager
def get_connection(begin_immediate: bool = False):
    conn = create_connection()
    if begin_immediate:
        conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f'PRAGMA table_info({table_name})').fetchall()
    return any(row['name'] == column_name for row in rows)


def _apply_job_worker_hardening_migration(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, 'jobs', 'retry_count'):
        conn.execute('ALTER TABLE jobs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0')
    if not _column_exists(conn, 'jobs', 'last_error'):
        conn.execute('ALTER TABLE jobs ADD COLUMN last_error TEXT')
    conn.execute("UPDATE jobs SET status = 'done' WHERE status = 'succeeded'")


def initialize_database() -> None:
    with get_connection(begin_immediate=True) as conn:
        for filename in MIGRATION_FILES:
            path = settings.MIGRATIONS_DIR / filename
            with open(path, encoding='utf-8') as f:
                conn.executescript(f.read())
        _apply_job_worker_hardening_migration(conn)


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
