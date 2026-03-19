import time
from datetime import datetime, timezone

from opsbot.models.types import DigestEmailItem, DigestResult, DigestConfig
from opsbot.tasks.digest.cache import save_seen_ids
from opsbot.tasks.digest.fetcher import fetch_emails
from opsbot.tasks.digest.formatter import compose_digest_text
from opsbot.tasks.digest.summarizer import summarize_email


def run_digest_task(config: DigestConfig) -> DigestResult:
    started = time.monotonic()
    emails, seen_ids = fetch_emails(config)

    groups = {'high': [], 'medium': [], 'low': []}
    warnings = []
    successful_fingerprints = {}

    for email_item in emails:
        summary, urgency, ok = summarize_email(config, email_item)
        if urgency not in groups:
            urgency = 'medium'
        groups[urgency].append(
            DigestEmailItem(
                sender=email_item.sender,
                subject=email_item.subject,
                date=email_item.date,
                summary=summary,
                urgency=urgency,
            )
        )
        if ok:
            successful_fingerprints[email_item.fingerprint] = datetime.now(timezone.utc).timestamp()
        else:
            warnings.append(f"Fallback summary used for subject: {email_item.subject}")

    if successful_fingerprints:
        merged = {**seen_ids, **successful_fingerprints}
        save_seen_ids(config.seen_cache_file, merged)

    duration_sec = time.monotonic() - started
    result = DigestResult(
        ok=True,
        emails_processed=len(emails),
        duration_sec=duration_sec,
        digest_text='',
        groups=groups,
        warnings=warnings,
        error_text=None,
    )
    result.digest_text = compose_digest_text(config.imap_user, result)
    return result
