CREATE TABLE IF NOT EXISTS slack_users (
    id BIGSERIAL PRIMARY KEY,
    slack_user_id TEXT NOT NULL UNIQUE,
    profile_key TEXT NOT NULL UNIQUE,
    slack_channel_id TEXT,
    imap_host TEXT NOT NULL,
    imap_port INTEGER NOT NULL DEFAULT 993,
    imap_use_ssl BOOLEAN NOT NULL DEFAULT TRUE,
    imap_user TEXT NOT NULL,
    imap_password_env_key TEXT NOT NULL,
    imap_mailbox TEXT NOT NULL DEFAULT 'INBOX',
    lookback_hours INTEGER NOT NULL DEFAULT 24,
    max_emails INTEGER NOT NULL DEFAULT 50,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id BIGSERIAL PRIMARY KEY,
    job_type TEXT NOT NULL,
    profile_key TEXT NOT NULL,
    requested_by_slack_user_id TEXT,
    requested_in_channel_id TEXT,
    command_text TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS job_events (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS job_results (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    slack_ts TEXT,
    output_text TEXT,
    digest_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_profile_key ON jobs(profile_key);
CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_job_results_job_id ON job_results(job_id);
