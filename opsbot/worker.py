import json
import sqlite3
import time
import traceback
from dataclasses import asdict

from opsbot import settings
from opsbot.db import get_connection, initialize_database, set_system_state
from opsbot.services import job_queue, slack_client
from opsbot.services.config_resolver import build_digest_config
from opsbot.services.profiles import get_user_profile
from opsbot.tasks.digest.formatter import compose_digest_blocks
from opsbot.tasks.digest.task import run_digest_task
from opsbot.tasks.platform_scan.task import run_platform_scan_task


initialize_database()


def dispatch_job(job):
    with get_connection() as conn:
        profile = get_user_profile(conn, job['requested_by_slack_user_id'])
    flags = json.loads(job['args_json'] or '{}')

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


def main():
    client = slack_client.build_client(settings.SLACK_BOT_TOKEN)
    print('[Worker] Started.')

    while True:
        try:
            with get_connection(begin_immediate=True) as conn:
                set_system_state(conn, 'worker_heartbeat', 'alive')
                job = job_queue.fetch_next_queued_job(conn)
                if not job:
                    sleep_seconds = settings.QUEUE_POLL_SECONDS
                else:
                    job_id = int(job['id'])
                    job_queue.mark_job_running(conn, job_id)
                    sleep_seconds = 0.2

            if not job:
                time.sleep(sleep_seconds)
                continue

            try:
                profile, result_text, result_json, blocks, summary = dispatch_job(job)
                dm_channel = slack_client.ensure_dm_channel(client, profile.slack_user_id)
                slack_client.post_blocks(client, dm_channel, result_text, blocks)
                with get_connection(begin_immediate=True) as conn:
                    job_queue.set_job_dm_channel(conn, job_id, dm_channel)
                    job_queue.store_job_result(conn, job_id, result_text, result_json, blocks)
                    job_queue.mark_job_succeeded(conn, job_id, result_summary=summary)
            except Exception as ex:
                error_text = ''.join(traceback.format_exception_only(type(ex), ex)).strip()
                with get_connection(begin_immediate=True) as conn:
                    job_queue.mark_job_failed(conn, job_id, error_text)
                try:
                    user_id = job['requested_by_slack_user_id']
                    dm_channel = slack_client.ensure_dm_channel(client, user_id)
                    slack_client.post_text(client, dm_channel, f'Job #{job_id} failed: {error_text}')
                except Exception:
                    pass

            time.sleep(sleep_seconds)
        except sqlite3.OperationalError:
            time.sleep(0.5)


if __name__ == '__main__':
    main()
