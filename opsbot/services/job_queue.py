import json
import sqlite3

from opsbot.db import utc_now_iso


def write_event(conn: sqlite3.Connection, job_id: int, event_type: str, message: str | None = None) -> None:
    conn.execute(
        'INSERT INTO job_events (job_id, event_type, message, created_at) VALUES (?, ?, ?, ?)',
        (job_id, event_type, message, utc_now_iso()),
    )


def enqueue_job(conn: sqlite3.Connection, job_type: str, slack_user_id: str, channel_id: str | None, channel_name: str | None, command_text: str, args: dict) -> int:
    now = utc_now_iso()
    cursor = conn.execute(
        """
        INSERT INTO jobs (
            job_type,
            requested_by_slack_user_id,
            requested_in_channel_id,
            requested_in_channel_name,
            command_text,
            args_json,
            status,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_type,
            slack_user_id,
            channel_id,
            channel_name,
            command_text,
            json.dumps(args),
            'queued',
            now,
        ),
    )
    job_id = int(cursor.lastrowid)
    write_event(conn, job_id, 'queued', 'Job queued')
    return job_id


def count_jobs_ahead(conn: sqlite3.Connection, job_id: int) -> int:
    job = conn.execute('SELECT id, created_at FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if not job:
        return 0
    running = conn.execute("SELECT COUNT(*) AS c FROM jobs WHERE status = 'running'").fetchone()['c']
    queued_before = conn.execute(
        "SELECT COUNT(*) AS c FROM jobs WHERE status = 'queued' AND created_at < ?",
        (job['created_at'],),
    ).fetchone()['c']
    return int(running) + int(queued_before)


def fetch_next_queued_job(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC, id ASC LIMIT 1"
    ).fetchone()


def get_running_job(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT * FROM jobs WHERE status = 'running' ORDER BY started_at DESC, id DESC LIMIT 1"
    ).fetchone()


def mark_job_running(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute(
        "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
        (utc_now_iso(), job_id),
    )
    write_event(conn, job_id, 'started', 'Job started')


def mark_job_succeeded(conn: sqlite3.Connection, job_id: int, result_summary: str | None = None) -> None:
    conn.execute(
        "UPDATE jobs SET status = 'succeeded', result_summary = ?, finished_at = ? WHERE id = ?",
        (result_summary, utc_now_iso(), job_id),
    )
    write_event(conn, job_id, 'completed', 'Job succeeded')


def mark_job_failed(conn: sqlite3.Connection, job_id: int, error_text: str) -> None:
    conn.execute(
        "UPDATE jobs SET status = 'failed', error_text = ?, finished_at = ? WHERE id = ?",
        (error_text, utc_now_iso(), job_id),
    )
    write_event(conn, job_id, 'failed', error_text)


def set_job_dm_channel(conn: sqlite3.Connection, job_id: int, dm_channel_id: str) -> None:
    conn.execute('UPDATE jobs SET dm_channel_id = ? WHERE id = ?', (dm_channel_id, job_id))


def store_job_result(conn: sqlite3.Connection, job_id: int, result_text: str, result_json: dict, slack_blocks_json: list | None) -> None:
    conn.execute(
        """
        INSERT INTO job_results (job_id, result_text, result_json, slack_blocks_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            result_text = excluded.result_text,
            result_json = excluded.result_json,
            slack_blocks_json = excluded.slack_blocks_json,
            created_at = excluded.created_at
        """,
        (
            job_id,
            result_text,
            json.dumps(result_json),
            json.dumps(slack_blocks_json) if slack_blocks_json is not None else None,
            utc_now_iso(),
        ),
    )
    write_event(conn, job_id, 'result_saved', 'Job result stored')


def get_last_result_for_user(conn: sqlite3.Connection, slack_user_id: str, job_type_prefix: str | None = None):
    if job_type_prefix:
        return conn.execute(
            """
            SELECT jr.*, j.job_type, j.finished_at
            FROM job_results jr
            JOIN jobs j ON j.id = jr.job_id
            WHERE j.requested_by_slack_user_id = ?
              AND j.status = 'succeeded'
              AND j.job_type LIKE ?
            ORDER BY j.finished_at DESC, j.id DESC
            LIMIT 1
            """,
            (slack_user_id, f'{job_type_prefix}%'),
        ).fetchone()
    return conn.execute(
        """
        SELECT jr.*, j.job_type, j.finished_at
        FROM job_results jr
        JOIN jobs j ON j.id = jr.job_id
        WHERE j.requested_by_slack_user_id = ?
          AND j.status = 'succeeded'
        ORDER BY j.finished_at DESC, j.id DESC
        LIMIT 1
        """,
        (slack_user_id,),
    ).fetchone()


def list_recent_jobs_for_user(conn: sqlite3.Connection, slack_user_id: str, limit: int = 5):
    return conn.execute(
        """
        SELECT id, job_type, status, created_at, started_at, finished_at, result_summary, error_text
        FROM jobs
        WHERE requested_by_slack_user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (slack_user_id, limit),
    ).fetchall()


def list_queue(conn: sqlite3.Connection, limit: int = 10):
    return conn.execute(
        """
        SELECT id, job_type, requested_by_slack_user_id, created_at
        FROM jobs
        WHERE status = 'queued'
        ORDER BY created_at ASC, id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def count_queue(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS c FROM jobs WHERE status = 'queued'").fetchone()
    return int(row['c'])
