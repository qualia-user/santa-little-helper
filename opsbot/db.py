from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from opsbot import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def create_connection() -> psycopg.Connection:
    if not settings.DATABASE_URL:
        raise RuntimeError('DATABASE_URL must be set.')
    return psycopg.connect(settings.DATABASE_URL, row_factory=dict_row)


@contextmanager
def get_connection():
    conn = create_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database() -> None:
    """PostgreSQL schema is expected to be created outside the application."""
    return None


def set_system_state(conn: psycopg.Connection, key: str, value_text: str) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO system_state (key, value_text, updated_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (key) DO UPDATE
        SET value_text = EXCLUDED.value_text,
            updated_at = EXCLUDED.updated_at
        """,
        (key, value_text, now),
    )



def get_system_state(conn: psycopg.Connection, key: str):
    return conn.execute(
        'SELECT key, value_text, updated_at FROM system_state WHERE key = %s',
        (key,),
    ).fetchone()
