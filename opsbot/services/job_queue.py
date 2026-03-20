import psycopg

from opsbot.db import create_connection, utc_now


TERMINAL_SUCCESS_STATUSES = ('done',)


def _job_summary_message(job_type: str, output_text: str | None) -> str:
    if output_text:
        return output_text[:500]
    return f'Completed {job_type}'


def write_event(conn: psycopg.Connection, job_id: int, event_type: str, message: str | None = None) -> None:
    conn.execute(
        'INSERT INTO job_events (job_id, event_type, message, created_at) VALUES (%s, %s, %s, %s)',
        (job_id, event_type, message, utc_now()),
    )


def enqueue_job(profile_key: str, job_type: str, slack_user_id: str, channel_id: str | None, command_text: str) -> int:
    conn = create_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO jobs (
                job_type,
                profile_key,
                requested_by_slack_user_id,
                requested_in_channel_id,
                command_text,
                status,
                retry_count,
                last_error,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                job_type,
                profile_key,
                slack_user_id,
                channel_id,
                command_text,
                'queued',
                0,
                None,
                utc_now(),
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
            finished_at = NULL,
            last_error = NULL
        FROM next_job
        WHERE jobs.id = next_job.id
        RETURNING jobs.*
        """,
        (utc_now(),),
    ).fetchone()
    if not job:
        return None
    write_event(conn, int(job['id']), 'running', 'Job claimed and started')
    return job


def get_running_job(conn: psycopg.Connection):
    return conn.execute(
        "SELECT * FROM jobs WHERE status = 'running' ORDER BY started_at DESC, id DESC LIMIT 1"
    ).fetchone()


def mark_job_done(conn: psycopg.Connection, job_id: int, result_message: str | None = None) -> None:
    conn.execute(
        """
        UPDATE jobs
        SET status = 'done',
            last_error = NULL,
            finished_at = %s
        WHERE id = %s
        """,
        (utc_now(), job_id),
    )
    write_event(conn, job_id, 'done', result_message or 'Job completed successfully')


def mark_job_failed(conn: psycopg.Connection, job_id: int, error_text: str) -> None:
    conn.execute(
        """
        UPDATE jobs
        SET status = 'failed',
            last_error = %s,
            retry_count = COALESCE(retry_count, 0) + 1,
            finished_at = %s
        WHERE id = %s
        """,
        (error_text, utc_now(), job_id),
    )
    write_event(conn, job_id, 'failed', error_text)


def set_job_dm_channel(conn: psycopg.Connection, job_id: int, dm_channel_id: str) -> None:
    write_event(conn, job_id, 'result_channel', f'Result sent to {dm_channel_id}')


def store_job_result(
    conn: psycopg.Connection,
    job_id: int,
    job_type: str,
    output_text: str,
    slack_ts: str | None = None,
) -> None:
    digest_date = utc_now() if job_type.startswith('digest.') else None
    conn.execute(
        """
        INSERT INTO job_results (job_id, slack_ts, output_text, digest_date, created_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (job_id) DO UPDATE SET
            slack_ts = EXCLUDED.slack_ts,
            output_text = EXCLUDED.output_text,
            digest_date = EXCLUDED.digest_date,
            created_at = EXCLUDED.created_at
        """,
        (job_id, slack_ts, output_text, digest_date, utc_now()),
    )
    write_event(conn, job_id, 'result_saved', _job_summary_message(job_type, output_text))


def get_last_result_for_user(conn: psycopg.Connection, slack_user_id: str, job_type_prefix: str | None = None):
    if job_type_prefix:
        return conn.execute(
            """
            SELECT jr.*, j.job_type, j.finished_at
            FROM job_results jr
            JOIN jobs j ON j.id = jr.job_id
            WHERE j.requested_by_slack_user_id = %s
              AND j.status = 'done'
              AND j.job_type LIKE %s
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
        WHERE j.requested_by_slack_user_id = %s
          AND j.status = 'done'
        ORDER BY j.finished_at DESC, j.id DESC
        LIMIT 1
        """,
        (slack_user_id,),
    ).fetchone()


def list_recent_jobs_for_user(conn: psycopg.Connection, slack_user_id: str, limit: int = 5):
    rows = conn.execute(
        """
        SELECT id, job_type, status, created_at, started_at, finished_at, retry_count, last_error
        FROM jobs
        WHERE requested_by_slack_user_id = %s
        ORDER BY id DESC
        LIMIT %s
        """,
        (slack_user_id, limit),
    ).fetchall()

    recent_results = {
        row['job_id']: row['output_text']
        for row in conn.execute(
            """
            SELECT job_id, output_text
            FROM job_results
            WHERE job_id = ANY(%s)
            """,
            ([row['id'] for row in rows] or [0],),
        ).fetchall()
    }

    normalized = []
    for row in rows:
        item = dict(row)
        item['result_summary'] = recent_results.get(row['id'])
        item['error_text'] = row['last_error']
        normalized.append(item)
    return normalized


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
