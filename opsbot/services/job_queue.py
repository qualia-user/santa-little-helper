import json

import psycopg

from opsbot.db import create_connection, utc_now_iso


TERMINAL_SUCCESS_STATUSES = ('done', 'succeeded')


def _status_placeholders(statuses: tuple[str, ...]) -> str:
    return ', '.join(['%s'] * len(statuses))


def write_event(conn: psycopg.Connection, job_id: int, event_type: str, message: str | None = None) -> None:
    conn.execute(
        'INSERT INTO job_events (job_id, event_type, message, created_at) VALUES (%s, %s, %s, %s)',
        (job_id, event_type, message, utc_now_iso()),
    )


def enqueue_job(job_type: str, slack_user_id: str, channel_id: str | None, channel_name: str | None, command_text: str, args: dict) -> int:
    conn = create_connection()
    try:
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
                created_at,
                retry_count,
                last_error
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
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
                0,
                None,
            ),
        )
        job_id = int(cursor.fetchone()['id'])
        write_event(conn, job_id, 'queued', 'Job queued')
        conn.commit()
        return job_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def count_jobs_ahead(conn: psycopg.Connection, job_id: int) -> int:
    job = conn.execute('SELECT id, created_at FROM jobs WHERE id = %s', (job_id,)).fetchone()
    if not job:
        return 0
    running = conn.execute("SELECT COUNT(*) AS c FROM jobs WHERE status = 'running'").fetchone()['c']
    queued_before = conn.execute(
        "SELECT COUNT(*) AS c FROM jobs WHERE status = 'queued' AND created_at < %s",
        (job['created_at'],),
    ).fetchone()['c']
    return int(running) + int(queued_before)



def fetch_next_queued_job(conn: psycopg.Connection):
    return conn.execute(
        "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC, id ASC LIMIT 1"
    ).fetchone()



def claim_next_queued_job(conn: psycopg.Connection):
    job = conn.execute(
        """
        WITH next_job AS (
            SELECT id
            FROM jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC, id ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE jobs
        SET status = 'running',
            started_at = %s,
            finished_at = NULL
        FROM next_job
        WHERE jobs.id = next_job.id
        RETURNING jobs.*
        """,
        (utc_now_iso(),),
    ).fetchone()
    if not job:
        return None
    write_event(conn, int(job['id']), 'running', 'Job claimed and started')
    return job



def get_running_job(conn: psycopg.Connection):
    return conn.execute(
        "SELECT * FROM jobs WHERE status = 'running' ORDER BY started_at DESC, id DESC LIMIT 1"
    ).fetchone()



def mark_job_done(conn: psycopg.Connection, job_id: int, result_summary: str | None = None) -> None:
    conn.execute(
        """
        UPDATE jobs
        SET status = 'done',
            result_summary = %s,
            last_error = NULL,
            error_text = NULL,
            finished_at = %s
        WHERE id = %s
        """,
        (result_summary, utc_now_iso(), job_id),
    )
    write_event(conn, job_id, 'done', 'Job completed successfully')



def mark_job_failed(conn: psycopg.Connection, job_id: int, error_text: str) -> None:
    conn.execute(
        """
        UPDATE jobs
        SET status = 'failed',
            error_text = %s,
            last_error = %s,
            retry_count = COALESCE(retry_count, 0) + 1,
            finished_at = %s
        WHERE id = %s
        """,
        (error_text, error_text, utc_now_iso(), job_id),
    )
    write_event(conn, job_id, 'failed', error_text)



def set_job_dm_channel(conn: psycopg.Connection, job_id: int, dm_channel_id: str) -> None:
    conn.execute('UPDATE jobs SET dm_channel_id = %s WHERE id = %s', (dm_channel_id, job_id))



def store_job_result(conn: psycopg.Connection, job_id: int, result_text: str, result_json: dict, slack_blocks_json: list | None) -> None:
    conn.execute(
        """
        INSERT INTO job_results (job_id, result_text, result_json, slack_blocks_json, created_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (job_id) DO UPDATE SET
            result_text = EXCLUDED.result_text,
            result_json = EXCLUDED.result_json,
            slack_blocks_json = EXCLUDED.slack_blocks_json,
            created_at = EXCLUDED.created_at
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



def get_last_result_for_user(conn: psycopg.Connection, slack_user_id: str, job_type_prefix: str | None = None):
    status_placeholders = _status_placeholders(TERMINAL_SUCCESS_STATUSES)
    if job_type_prefix:
        return conn.execute(
            f"""
            SELECT jr.*, j.job_type, j.finished_at
            FROM job_results jr
            JOIN jobs j ON j.id = jr.job_id
            WHERE j.requested_by_slack_user_id = %s
              AND j.status IN ({status_placeholders})
              AND j.job_type LIKE %s
            ORDER BY j.finished_at DESC, j.id DESC
            LIMIT 1
            """,
            (slack_user_id, *TERMINAL_SUCCESS_STATUSES, f'{job_type_prefix}%'),
        ).fetchone()
    return conn.execute(
        f"""
        SELECT jr.*, j.job_type, j.finished_at
        FROM job_results jr
        JOIN jobs j ON j.id = jr.job_id
        WHERE j.requested_by_slack_user_id = %s
          AND j.status IN ({status_placeholders})
        ORDER BY j.finished_at DESC, j.id DESC
        LIMIT 1
        """,
        (slack_user_id, *TERMINAL_SUCCESS_STATUSES),
    ).fetchone()



def list_recent_jobs_for_user(conn: psycopg.Connection, slack_user_id: str, limit: int = 5):
    return conn.execute(
        """
        SELECT id, job_type, status, created_at, started_at, finished_at, result_summary, error_text, retry_count, last_error
        FROM jobs
        WHERE requested_by_slack_user_id = %s
        ORDER BY id DESC
        LIMIT %s
        """,
        (slack_user_id, limit),
    ).fetchall()



def list_queue(conn: psycopg.Connection, limit: int = 10):
    return conn.execute(
        """
        SELECT id, job_type, requested_by_slack_user_id, created_at
        FROM jobs
        WHERE status = 'queued'
        ORDER BY created_at ASC, id ASC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()



def count_queue(conn: psycopg.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS c FROM jobs WHERE status = 'queued'").fetchone()
    return int(row['c'])
