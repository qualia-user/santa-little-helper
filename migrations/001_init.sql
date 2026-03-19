CREATE TABLE IF NOT EXISTS slack_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slack_user_id TEXT NOT NULL UNIQUE,
    slack_username TEXT,
    display_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    profile_key TEXT NOT NULL UNIQUE,
    imap_host TEXT NOT NULL,
    imap_port INTEGER NOT NULL,
    imap_user TEXT NOT NULL,
    imap_mailbox TEXT NOT NULL DEFAULT 'INBOX',
    imap_use_ssl INTEGER NOT NULL DEFAULT 0,
    imap_password_env_key TEXT NOT NULL,
    allowed_tasks_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    requested_by_slack_user_id TEXT NOT NULL,
    requested_in_channel_id TEXT,
    requested_in_channel_name TEXT,
    command_text TEXT NOT NULL,
    args_json TEXT NOT NULL,
    status TEXT NOT NULL,
    result_summary TEXT,
    error_text TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    dm_channel_id TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS job_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL UNIQUE,
    result_text TEXT,
    result_json TEXT,
    slack_blocks_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value_text TEXT,
    updated_at TEXT NOT NULL
);
