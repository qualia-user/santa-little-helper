from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from opsbot import settings


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS slack_users (
        id BIGSERIAL PRIMARY KEY,
        slack_user_id TEXT NOT NULL UNIQUE,
        profile_key TEXT NOT NULL UNIQUE,
        slack_channel_id TEXT,
        imap_host TEXT NOT NULL,
        imap_port INTEGER NOT NULL DEFAULT 993,
        imap_use_ssl BOOLEAN NOT NULL DEFAULT TRUE,
        imap_user TEXT NOT NULL,
        imap_password_env_key TEXT NOT NULL,
        imap_mailbox TEXT NOT NULL DEFAULT 'INBOX',
        lookback_hours INTEGER NOT NULL DEFAULT 24,
        max_emails INTEGER NOT NULL DEFAULT 50,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id BIGSERIAL PRIMARY KEY,
        job_type TEXT NOT NULL,
        profile_key TEXT NOT NULL,
        requested_by_slack_user_id TEXT,
        requested_in_channel_id TEXT,
        command_text TEXT,
        status TEXT NOT NULL DEFAULT 'queued',
        retry_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        started_at TIMESTAMPTZ,
        finished_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_events (
        id BIGSERIAL PRIMARY KEY,
        job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        event_type TEXT NOT NULL,
        message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_results (
        id BIGSERIAL PRIMARY KEY,
        job_id BIGINT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
        slack_ts TEXT,
        output_text TEXT,
        digest_date TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS system_state (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    'CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at ON jobs(status, created_at)',
    'CREATE INDEX IF NOT EXISTS idx_jobs_profile_key ON jobs(profile_key)',
    'CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id)',
    'CREATE INDEX IF NOT EXISTS idx_job_results_job_id ON job_results(job_id)',
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


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
    with get_connection() as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)


def set_system_state(conn: psycopg.Connection, key: str, value: str) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO system_state (key, value, updated_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value,
            updated_at = EXCLUDED.updated_at
        """,
        (key, value, now),
    )


def get_system_state(conn: psycopg.Connection, key: str):
    return conn.execute(
        'SELECT key, value, updated_at FROM system_state WHERE key = %s',
        (key,),
    ).fetchone()
