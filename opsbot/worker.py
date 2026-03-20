import json
import sqlite3
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone

from opsbot import settings
from opsbot.commands.handlers import build_direct_response, is_direct_task
from opsbot.commands.ops_parser import parse_command
from opsbot.db import get_connection, get_system_state, initialize_database, set_system_state
from opsbot.services import job_queue, slack_client, slack_ui
from opsbot.services.config_resolver import build_digest_config
from opsbot.services.profiles import get_user_profile
from opsbot.tasks.digest.formatter import compose_digest_blocks
from opsbot.tasks.digest.task import run_digest_task
from opsbot.tasks.platform_scan.task import run_platform_scan_task


initialize_database()


def log(message: str) -> None:
    print(f'[Worker] {message}', flush=True)


def _build_system_health_response() -> dict:
    with get_connection() as conn:
        worker_row = get_system_state(conn, 'worker_heartbeat')

    worker_status = 'missing'
    if worker_row:
        updated_at = datetime.fromisoformat(worker_row['updated_at'].replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - updated_at).total_seconds()
        max_age = settings.QUEUE_POLL_SECONDS * 4
        worker_status = f'alive ({age:.0f}s ago)' if age <= max_age else f'stale ({age:.0f}s ago)'

    from opsbot.commands.handlers import _safe_ollama_health

    ollama_ok, ollama_status = _safe_ollama_health()
    blocks = slack_ui.health_blocks(
        db_ok=True,
        worker_status=worker_status,
        ollama_ok=ollama_ok,
        ollama_status=ollama_status,
    )
    return {'text': 'System health', 'blocks': blocks}


def dispatch_job(job):
    with get_connection() as conn:
        profile = get_user_profile(conn, job['requested_by_slack_user_id'])
    flags = json.loads(job['args_json'] or '{}')

    if is_direct_task(job['job_type']):
        command = parse_command(job['command_text'])
        if command.task_name == 'system.health':
            response = _build_system_health_response()
        else:
            with get_connection() as conn:
                response = build_direct_response(conn, job['requested_by_slack_user_id'], command)
        return profile, response.get('text', job['command_text']), {}, response.get('blocks'), f"Completed {job['job_type']}"

    if job['job_type'] == 'digest.run':
        config = build_digest_config(profile, flags)
        result = run_digest_task(config)
        blocks = compose_digest_blocks(profile.profile_key, result)
        summary = f'Processed {result.emails_processed} email(s)'
        return profile, result.digest_text, asdict(result), blocks, summary

    if job['job_type'] == 'digest.test':
        flags.setdefault('max_emails', 5)
        config = build_digest_config(profile, flags)
        result = run_digest_task(config)
        blocks = compose_digest_blocks(profile.profile_key, result)
        summary = f'Test processed {result.emails_processed} email(s)'
        return profile, result.digest_text, asdict(result), blocks, summary

    if job['job_type'] == 'platform.scan':
        result = run_platform_scan_task()
        text = result['message']
        blocks = [
            {'type': 'header', 'text': {'type': 'plain_text', 'text': 'Platform scan'}},
            {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}},
        ]
        return profile, text, result, blocks, 'Platform scan placeholder completed'

    raise ValueError(f"Unsupported job type: {job['job_type']}")


def _resolve_result_channel(client, job, profile) -> str:
    if is_direct_task(job['job_type']) and job['requested_in_channel_id']:
        return job['requested_in_channel_id']
    return slack_client.ensure_dm_channel(client, profile.slack_user_id)


def main():
    client = slack_client.build_client(settings.SLACK_BOT_TOKEN)
    log('Started.')

    while True:
        sleep_seconds = settings.QUEUE_POLL_SECONDS
        job = None
        job_id = None

        try:
            with get_connection(begin_immediate=True) as conn:
                set_system_state(conn, 'worker_heartbeat', 'alive')
                job = job_queue.claim_next_queued_job(conn)

            if not job:
                log(f'No queued jobs found; sleeping {sleep_seconds}s.')
                time.sleep(sleep_seconds)
                continue

            job_id = int(job['id'])
            log(f'Claimed job #{job_id} ({job["job_type"]}); status=running.')

            try:
                profile, result_text, result_json, blocks, summary = dispatch_job(job)
                result_channel = _resolve_result_channel(client, job, profile)
                log(f'Starting job #{job_id} ({job["job_type"]}).')
                slack_client.post_blocks(client, result_channel, result_text, blocks)
                with get_connection(begin_immediate=True) as conn:
                    job_queue.set_job_dm_channel(conn, job_id, result_channel)
                    job_queue.store_job_result(conn, job_id, result_text, result_json, blocks)
                    job_queue.mark_job_done(conn, job_id, result_summary=summary)
                log(f'Job #{job_id} succeeded; status=done.')
            except Exception as ex:
                error_details = ''.join(traceback.format_exception(type(ex), ex, ex.__traceback__)).strip()
                log(f'Job #{job_id} failed: {ex!r}')
                with get_connection(begin_immediate=True) as conn:
                    job_queue.mark_job_failed(conn, job_id, error_details)
                try:
                    result_channel = job['requested_in_channel_id'] or slack_client.ensure_dm_channel(client, job['requested_by_slack_user_id'])
                    slack_client.post_text(client, result_channel, f'''Job #{job_id} failed:
{error_details}''')
                except Exception as notify_ex:
                    log(f'Failed to notify Slack for job #{job_id}: {notify_ex!r}')
                continue
        except sqlite3.OperationalError as ex:
            log(f'SQLite operational error while polling queue: {ex!r}')
            time.sleep(0.5)
            continue
        except Exception as ex:
            log(f'Unexpected worker loop error: {ex!r}')
            time.sleep(0.5)
            continue

        time.sleep(0.2)


if __name__ == '__main__':
    main()
