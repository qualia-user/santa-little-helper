import imaplib
import email
from datetime import datetime, timedelta

from opsbot.models.types import DigestConfig, RawEmail
from opsbot.tasks.digest.cache import load_seen_ids, msg_fingerprint
from opsbot.tasks.digest.mail_utils import decode_str, get_plain_body


def fetch_emails(config: DigestConfig) -> tuple[list[RawEmail], dict]:
    print(f"[IMAP] Connecting to {config.imap_host}:{config.imap_port} (SSL={config.imap_use_ssl})...")
    seen_ids = load_seen_ids(config.seen_cache_file, config.lookback_hours)
    conn = None
    try:
        if config.imap_use_ssl:
            conn = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
        else:
            conn = imaplib.IMAP4(config.imap_host, config.imap_port)

        conn.login(config.imap_user, config.imap_password)
        conn.select(config.imap_mailbox)

        since_date = (datetime.now() - timedelta(hours=config.lookback_hours)).strftime('%d-%b-%Y')
        status, data = conn.search(None, f'SINCE {since_date}')
        if status != 'OK':
            print('[IMAP] Search failed.')
            try:
                conn.logout()
            except Exception:
                pass
            return [], seen_ids

        msg_ids = data[0].split()
        msg_ids = msg_ids[-config.max_emails:]
        print(f"[IMAP] Found {len(msg_ids)} email(s) in the last {config.lookback_hours}h.")

        emails = []
        for mid in msg_ids:
            status, msg_data = conn.fetch(mid, '(BODY.PEEK[])')
            if status != 'OK' or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            fingerprint = msg_fingerprint(msg)
            if fingerprint in seen_ids:
                print(f"  [skip] Already processed: {decode_str(msg.get('Subject', ''))[:60]}")
                continue
            emails.append(
                RawEmail(
                    id=mid.decode(),
                    fingerprint=fingerprint,
                    sender=decode_str(msg.get('From', '')),
                    subject=decode_str(msg.get('Subject', '(no subject)')),
                    date=decode_str(msg.get('Date', '')),
                    body=get_plain_body(msg),
                )
            )

        conn.logout()
        print(f"[IMAP] {len(emails)} new email(s) to process.")
        return emails, seen_ids

    except Exception as ex:
        print(f'[IMAP] Error: {ex}')
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                pass
        return [], seen_ids
