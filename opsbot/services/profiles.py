import json

from opsbot.models.types import UserProfile


class ProfileNotFoundError(RuntimeError):
    pass


class ProfileInactiveError(RuntimeError):
    pass


def _row_to_profile(row) -> UserProfile:
    return UserProfile(
        slack_user_id=row['slack_user_id'],
        slack_username=row['slack_username'],
        display_name=row['display_name'],
        profile_key=row['profile_key'],
        imap_host=row['imap_host'],
        imap_port=int(row['imap_port']),
        imap_user=row['imap_user'],
        imap_mailbox=row['imap_mailbox'],
        imap_use_ssl=bool(row['imap_use_ssl']),
        imap_password_env_key=row['imap_password_env_key'],
        allowed_tasks=json.loads(row['allowed_tasks_json']),
    )


def get_user_profile(conn, slack_user_id: str) -> UserProfile:
    row = conn.execute(
        'SELECT * FROM slack_users WHERE slack_user_id = ?',
        (slack_user_id,),
    ).fetchone()
    if not row:
        raise ProfileNotFoundError('You are not mapped to a mailbox/profile yet.')
    if not row['is_active']:
        raise ProfileInactiveError('Your profile is currently inactive.')
    return _row_to_profile(row)


def get_user_profile_by_key(conn, profile_key: str) -> UserProfile:
    row = conn.execute(
        'SELECT * FROM slack_users WHERE profile_key = ?',
        (profile_key,),
    ).fetchone()
    if not row:
        raise ProfileNotFoundError(f'Profile not found: {profile_key}')
    if not row['is_active']:
        raise ProfileInactiveError(f'Profile inactive: {profile_key}')
    return _row_to_profile(row)


def user_can_run(profile: UserProfile, task_name: str) -> bool:
    return task_name in profile.allowed_tasks
