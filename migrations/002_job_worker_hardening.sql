-- Manual migration for existing databases that predate retry_count / last_error support.
ALTER TABLE jobs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN last_error TEXT;

UPDATE jobs
SET status = 'done'
WHERE status = 'succeeded';
