import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path


def load_seen_ids(seen_cache_file: str, lookback_hours: int) -> dict:
    try:
        with open(seen_cache_file, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            now = datetime.now(timezone.utc).timestamp()
            data = {key: now for key in data}
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp()
        return {k: v for k, v in data.items() if v >= cutoff}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen_ids(seen_cache_file: str, seen: dict) -> None:
    Path(seen_cache_file).parent.mkdir(parents=True, exist_ok=True)
    with open(seen_cache_file, 'w', encoding='utf-8') as f:
        json.dump(seen, f)


def msg_fingerprint(msg) -> str:
    message_id = msg.get('Message-ID', '').strip()
    if message_id:
        return message_id
    raw = f"{msg.get('Subject', '')}{msg.get('Date', '')}{msg.get('From', '')}".encode()
    return hashlib.sha1(raw).hexdigest()
