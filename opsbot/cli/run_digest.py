import argparse

from opsbot.db import get_connection, initialize_database
from opsbot.services.config_resolver import build_digest_config
from opsbot.services.profiles import get_user_profile_by_key
from opsbot.tasks.digest.task import run_digest_task


def main():
    parser = argparse.ArgumentParser(description='Run digest locally without Slack.')
    parser.add_argument('--profile-key', required=True)
    parser.add_argument('--hours', type=int)
    parser.add_argument('--max-emails', dest='max_emails', type=int)
    args = parser.parse_args()

    initialize_database()
    with get_connection() as conn:
        profile = get_user_profile_by_key(conn, args.profile_key)
        flags = {}
        if args.hours is not None:
            flags['hours'] = args.hours
        if args.max_emails is not None:
            flags['max_emails'] = args.max_emails
        config = build_digest_config(profile, flags)

    result = run_digest_task(config)
    print(result.digest_text)


if __name__ == '__main__':
    main()
