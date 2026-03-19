from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UserProfile:
    slack_user_id: str
    slack_username: Optional[str]
    display_name: Optional[str]
    profile_key: str
    imap_host: str
    imap_port: int
    imap_user: str
    imap_mailbox: str
    imap_use_ssl: bool
    imap_password_env_key: str
    allowed_tasks: List[str]


@dataclass
class CommandRequest:
    raw_text: str
    domain: str
    action: str
    task_name: str
    flags: Dict[str, Any]


@dataclass
class DigestConfig:
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    imap_mailbox: str
    imap_use_ssl: bool
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_sec: int
    lookback_hours: int
    max_emails: int
    seen_cache_file: str


@dataclass
class RawEmail:
    id: str
    fingerprint: str
    sender: str
    subject: str
    date: str
    body: str


@dataclass
class DigestEmailItem:
    sender: str
    subject: str
    date: str
    summary: str
    urgency: str


@dataclass
class DigestResult:
    ok: bool
    emails_processed: int
    duration_sec: float
    digest_text: str
    groups: Dict[str, List[DigestEmailItem]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    error_text: Optional[str] = None
