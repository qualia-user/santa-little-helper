import urllib.request
from datetime import datetime, timezone

from opsbot import settings
from opsbot.db import get_system_state
from opsbot.services import job_queue, slack_ui


HEAVY_TASKS = {'digest.run', 'digest.test', 'platform.scan'}
DIRECT_TASKS = {'digest.last', 'jobs.status', 'jobs.queue', 'system.health'}


def is_heavy_task(task_name: str) -> bool:
    return task_name in HEAVY_TASKS


def is_direct_task(task_name: str) -> bool:
    return task_name in DIRECT_TASKS


def _safe_ollama_health() -> tuple[bool, str]:
    try:
        req = urllib.request.Request(f"{settings.OLLAMA_BASE_URL}/api/tags", method='GET')
        with urllib.request.urlopen(req, timeout=3) as resp:
            if 200 <= resp.status < 300:
                return True, 'reachable'
        return False, 'unexpected HTTP status'
    except Exception as ex:
        return False, str(ex)


def _coerce_timestamp(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace('Z', '+00:00'))


def build_direct_response(conn, slack_user_id: str, command) -> dict:
    if command.task_name == 'digest.last':
        row = job_queue.get_last_result_for_user(conn, slack_user_id, job_type_prefix='digest.')
        if not row:
            blocks = slack_ui.empty_state_blocks('No previous digest found yet.')
            return {'response_type': 'ephemeral', 'text': 'No previous digest found.', 'blocks': blocks}

        text = row['output_text'] or 'Last digest exists but has no rendered text.'
        blocks = slack_ui.empty_state_blocks(text)
        return {'response_type': 'ephemeral', 'text': text, 'blocks': blocks}

    if command.task_name == 'jobs.status':
        jobs = job_queue.list_recent_jobs_for_user(conn, slack_user_id, limit=5)
        queue_len = job_queue.count_queue(conn)
        blocks = slack_ui.jobs_status_blocks(jobs, queue_len)
        return {'response_type': 'ephemeral', 'text': 'Jobs status', 'blocks': blocks}

    if command.task_name == 'jobs.queue':
        queued = job_queue.list_queue(conn, limit=10)
        running = job_queue.get_running_job(conn)
        blocks = slack_ui.queue_blocks(running, queued)
        return {'response_type': 'ephemeral', 'text': 'Queue status', 'blocks': blocks}

    if command.task_name == 'system.health':
        db_ok = True
        worker_row = get_system_state(conn, 'worker_heartbeat')
        worker_status = 'missing'
        if worker_row:
            updated_at = _coerce_timestamp(worker_row['updated_at'])
            age = (datetime.now(timezone.utc) - updated_at).total_seconds()
            worker_status = f'alive ({age:.0f}s ago)' if age <= settings.QUEUE_POLL_SECONDS * 4 else f'stale ({age:.0f}s ago)'
        ollama_ok, ollama_status = _safe_ollama_health()
        blocks = slack_ui.health_blocks(db_ok=db_ok, worker_status=worker_status, ollama_ok=ollama_ok, ollama_status=ollama_status)
        return {'response_type': 'ephemeral', 'text': 'System health', 'blocks': blocks}

    raise ValueError(f'Unsupported direct task: {command.task_name}')
