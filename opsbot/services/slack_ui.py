from typing import Iterable


ICONS = {
    'high': ':red_circle:',
    'medium': ':large_yellow_circle:',
    'low': ':large_blue_circle:',
}


def empty_state_blocks(message: str) -> list:
    return [
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': message}},
    ]


def queue_accepted_blocks(job_id: int, position_ahead: int, command_text: str) -> list:
    return [
        {'type': 'header', 'text': {'type': 'plain_text', 'text': 'Job accepted'}},
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': f'*Job:* #{job_id}\n*Queued behind:* {position_ahead}\n*Command:* `{command_text}`',
            },
        },
        {
            'type': 'context',
            'elements': [
                {'type': 'mrkdwn', 'text': 'I will DM you the final result.'},
            ],
        },
    ]


def digest_result_blocks(profile_name: str, result, include_actions: bool = True) -> list:
    blocks = [
        {'type': 'header', 'text': {'type': 'plain_text', 'text': 'Daily Email Digest'}},
        {
            'type': 'context',
            'elements': [
                {
                    'type': 'mrkdwn',
                    'text': (
                        f'*Profile:* {profile_name}  •  '
                        f'*Emails processed:* {result.emails_processed}  •  '
                        f'*Duration:* {result.duration_sec:.1f}s'
                    ),
                }
            ],
        },
    ]

    if result.warnings:
        blocks.append(
            {
                'type': 'section',
                'text': {'type': 'mrkdwn', 'text': '*Warnings:*\n' + '\n'.join(f'• {w}' for w in result.warnings[:5])},
            }
        )

    for level in ('high', 'medium', 'low'):
        items = result.groups.get(level, [])
        if not items:
            continue
        blocks.append(
            {
                'type': 'section',
                'text': {'type': 'mrkdwn', 'text': f"{ICONS[level]} *{level.capitalize()} Priority ({len(items)})*"},
            }
        )
        for item in items[:6]:
            blocks.append(
                {
                    'type': 'section',
                    'text': {
                        'type': 'mrkdwn',
                        'text': f"*{item.sender}* — _{item.subject}_\n{item.summary}",
                    },
                }
            )
        if len(items) > 6:
            blocks.append(
                {
                    'type': 'context',
                    'elements': [{'type': 'mrkdwn', 'text': f'...and {len(items) - 6} more {level} item(s).'}],
                }
            )

    if include_actions:
        blocks.append(
            {
                'type': 'actions',
                'elements': [
                    {
                        'type': 'button',
                        'text': {'type': 'plain_text', 'text': 'Run again'},
                        'action_id': 'digest_run_again',
                        'value': 'digest.run',
                    },
                    {
                        'type': 'button',
                        'text': {'type': 'plain_text', 'text': 'Last digest'},
                        'action_id': 'digest_show_last',
                        'value': 'digest.last',
                    },
                    {
                        'type': 'button',
                        'text': {'type': 'plain_text', 'text': 'Queue status'},
                        'action_id': 'jobs_queue_status',
                        'value': 'jobs.queue',
                    },
                ],
            }
        )

    return blocks[:50]


def jobs_status_blocks(jobs: Iterable, queue_len: int) -> list:
    blocks = [
        {'type': 'header', 'text': {'type': 'plain_text', 'text': 'Jobs status'}},
        {'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'*Queued jobs:* {queue_len}'}]},
    ]
    if not jobs:
        blocks.extend(empty_state_blocks('No jobs found yet.'))
        return blocks

    for job in jobs:
        line = (
            f"*#{job['id']}* — `{job['job_type']}` — *{job['status']}*\n"
            f"Created: {job['created_at']}"
        )
        if job['result_summary']:
            line += f"\nSummary: {job['result_summary']}"
        if job['error_text']:
            line += f"\nError: {job['error_text']}"
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': line}})
    return blocks[:50]


def queue_blocks(running, queued: Iterable) -> list:
    blocks = [
        {'type': 'header', 'text': {'type': 'plain_text', 'text': 'Queue status'}},
    ]
    if running:
        blocks.append(
            {
                'type': 'section',
                'text': {'type': 'mrkdwn', 'text': f"*Running:* #{running['id']} `{running['job_type']}` by `{running['requested_by_slack_user_id']}`"},
            }
        )
    else:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '*Running:* none'}})

    queued = list(queued)
    if not queued:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '*Queued:* none'}})
        return blocks

    lines = []
    for job in queued:
        lines.append(f"• #{job['id']} `{job['job_type']}` by `{job['requested_by_slack_user_id']}`")
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '*Queued:*\n' + '\n'.join(lines)}})
    return blocks[:50]


def health_blocks(db_ok: bool, worker_status: str, ollama_ok: bool, ollama_status: str) -> list:
    return [
        {'type': 'header', 'text': {'type': 'plain_text', 'text': 'System health'}},
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': (
                    f"*DB:* {'ok' if db_ok else 'fail'}\n"
                    f"*Worker:* {worker_status}\n"
                    f"*Ollama:* {'ok' if ollama_ok else 'fail'} ({ollama_status})"
                ),
            },
        },
    ]


def error_blocks(title: str, detail: str) -> list:
    return [
        {'type': 'header', 'text': {'type': 'plain_text', 'text': title}},
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': detail}},
    ]
