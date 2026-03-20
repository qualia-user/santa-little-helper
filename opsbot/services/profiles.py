from opsbot.models.types import UserProfile


class ProfileNotFoundError(RuntimeError):
    pass


class ProfileInactiveError(RuntimeError):
    pass


DEFAULT_ALLOWED_TASKS = [
    'digest.run',
    'digest.test',
    'digest.last',
    'jobs.status',
    'jobs.queue',
    'system.health',
    'platform.scan',
]


def _row_to_profile(row) -> UserProfile:
    return UserProfile(
        slack_user_id=row['slack_user_id'],
        profile_key=row['profile_key'],
        slack_channel_id=row.get('slack_channel_id'),
        imap_host=row['imap_host'],
        imap_port=int(row['imap_port']),
        imap_user=row['imap_user'],
        imap_mailbox=row['imap_mailbox'],
        imap_use_ssl=bool(row['imap_use_ssl']),
        imap_password_env_key=row['imap_password_env_key'],
        lookback_hours=int(row['lookback_hours']),
        max_emails=int(row['max_emails']),
        is_active=bool(row['is_active']),
        allowed_tasks=list(DEFAULT_ALLOWED_TASKS),
    )


def get_user_profile(conn, slack_user_id: str) -> UserProfile:
    row = conn.execute(
        'SELECT * FROM slack_users WHERE slack_user_id = %s',
        (slack_user_id,),
    ).fetchone()
    if not row:
        raise ProfileNotFoundError('You are not mapped to a mailbox/profile yet.')
    if not row['is_active']:
        raise ProfileInactiveError('Your profile is currently inactive.')
    return _row_to_profile(row)


def get_user_profile_by_key(conn, profile_key: str) -> UserProfile:
    row = conn.execute(
        'SELECT * FROM slack_users WHERE profile_key = %s',
        (profile_key,),
    ).fetchone()
    if not row:
        raise ProfileNotFoundError(f'Profile not found: {profile_key}')
    if not row['is_active']:
        raise ProfileInactiveError(f'Profile inactive: {profile_key}')
    return _row_to_profile(row)


def user_can_run(profile: UserProfile, task_name: str) -> bool:
    return task_name in profile.allowed_tasks
