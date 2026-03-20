import os
from pathlib import Path

from opsbot import settings
from opsbot.models.types import DigestConfig, UserProfile


class ConfigError(RuntimeError):
    pass


def build_digest_config(profile: UserProfile, flags: dict) -> DigestConfig:
    imap_password = os.getenv(profile.imap_password_env_key, '')
    if not imap_password:
        raise ConfigError(
            f'Missing IMAP password in environment for key: {profile.imap_password_env_key}'
        )

    seen_cache_file = Path(settings.CACHE_DIR) / f'seen_{profile.profile_key}.json'

    return DigestConfig(
        imap_host=profile.imap_host or 'localhost',
        imap_port=profile.imap_port,
        imap_user=profile.imap_user,
        imap_password=imap_password,
        imap_mailbox=profile.imap_mailbox or 'INBOX',
        imap_use_ssl=profile.imap_use_ssl,
        ollama_base_url=settings.OLLAMA_BASE_URL,
        ollama_model=settings.OLLAMA_MODEL,
        ollama_timeout_sec=settings.OLLAMA_TIMEOUT_SEC,
        lookback_hours=int(flags.get('hours', profile.lookback_hours or settings.DEFAULT_LOOKBACK_HOURS)),
        max_emails=int(flags.get('max_emails', profile.max_emails or settings.DEFAULT_MAX_EMAILS)),
        seen_cache_file=str(seen_cache_file),
    )
