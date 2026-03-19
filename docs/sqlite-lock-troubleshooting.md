# SQLite lock troubleshooting

This runbook is for operators debugging queue stalls or Slack command failures caused by SQLite write contention in OpsBot.

## Scope

Use this document when you see any of the following:

- `sqlite3.OperationalError: database is locked`
- Slack slash commands acknowledge slowly, time out, or appear unhandled
- jobs remain stuck in `queued` or `running`

## Symptoms

### Application-level symptoms

- Worker logs show `sqlite3.OperationalError: database is locked` while polling or updating job state.
- Slash commands return the fallback message that the job could not be queued, or Slack reports an ack timeout / unhandled command.
- The queue grows, but no jobs move from `queued` to `done`.
- A job remains in `running` long after the worker should have completed it.

### Operational indicators

- `opsbot-slack.service` is up, but commands are not enqueued.
- `opsbot-worker.service` is up, but the worker heartbeat is stale or jobs are not advancing.
- A local `sqlite3` shell, DB browser, or admin tool is open against the same database file.

## Likely causes

Common causes in this repository:

1. **Long transaction**
   - A write transaction stays open too long and blocks other writers.
   - Risk areas are queue claiming, job status updates, and any manual SQL session left uncommitted.

2. **Shared connection across threads**
   - SQLite connections are not meant to be shared across unrelated threads or long-lived concurrent flows.
   - This codebase is designed around a fresh connection per operation.

3. **Multiple workers writing at once**
   - SQLite handles a single writer at a time.
   - Running more than one worker process can increase lock contention and leave jobs stuck.

4. **`sqlite3` shell or admin tool holding a lock**
   - An interactive shell, editor plugin, or GUI DB browser can keep a transaction open.
   - This is especially common after running ad hoc update statements without exiting cleanly.

5. **Worker crash mid-transaction**
   - A worker can claim a job, mark it `running`, then crash before marking it `done` or `failed`.
   - Recovery may require resetting stale `running` jobs.

6. **Missing or ineffective `busy_timeout` / WAL mode**
   - This project configures both, but a separate client or script that connects without those pragmas can still behave badly.
   - WAL mode reduces read/write blocking, but does not remove the single-writer limitation.

## Confirm current repo behavior

The application already includes some SQLite hardening:

- Connections are opened through `create_connection()` and configured with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`.【F:opsbot/db.py†L17-L27】
- The shared `get_connection()` helper can open transactions with `BEGIN IMMEDIATE` for write paths.【F:opsbot/db.py†L31-L41】
- The worker claims jobs and writes job state inside `begin_immediate=True` transactions, which is the intended pattern for serialized writes.【F:opsbot/worker.py†L79-L81】【F:opsbot/worker.py†L96-L100】【F:opsbot/worker.py†L103-L106】
- The Slack command handler sends `ack()` before later queue work, which helps avoid Slack timeouts when downstream DB work is slow.【F:opsbot/app.py†L35-L40】
- The default database path is `data/opsbot.sqlite` unless `DB_PATH` overrides it.【F:opsbot/settings.py†L51-L51】

## Debug commands

Run these from the repository root unless noted otherwise.

### 1) Find running Python processes

```bash
ps -ef | grep python | grep -E 'opsbot\\.(app|worker)' | grep -v grep
pgrep -af 'python.*opsbot\\.(app|worker)'
```

Use this to confirm whether you have:

- one Slack receiver process
- one worker process
- accidental duplicate workers

### 2) Check systemd service status

```bash
sudo systemctl status opsbot-slack.service --no-pager
sudo systemctl status opsbot-worker.service --no-pager
sudo journalctl -u opsbot-slack.service -n 100 --no-pager
sudo journalctl -u opsbot-worker.service -n 100 --no-pager
```

Look for:

- restart loops
- repeated `database is locked`
- worker crashes after claiming a job
- command handler errors immediately after Slack requests arrive

### 3) Inspect the SQLite DB path

Default path:

```bash
python - <<'PY'
from opsbot import settings
print(settings.DB_PATH)
PY
```

Check whether the DB file and WAL sidecars exist:

```bash
DB_PATH="$(python - <<'PY'
from opsbot import settings
print(settings.DB_PATH)
PY
)"
echo "$DB_PATH"
ls -l "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm" 2>/dev/null || true
```

Check who has the DB open:

```bash
lsof "$DB_PATH" 2>/dev/null || true
fuser "$DB_PATH" 2>/dev/null || true
```

### 4) Inspect queued and running jobs

```bash
python - <<'PY'
import sqlite3
from opsbot import settings
conn = sqlite3.connect(settings.DB_PATH)
conn.row_factory = sqlite3.Row
for row in conn.execute("""
    SELECT id, job_type, status, requested_by_slack_user_id, created_at, started_at, finished_at
    FROM jobs
    WHERE status IN ('queued', 'running')
    ORDER BY created_at ASC, id ASC
"""):
    print(dict(row))
conn.close()
PY
```

Quick counts by status:

```bash
python - <<'PY'
import sqlite3
from opsbot import settings
conn = sqlite3.connect(settings.DB_PATH)
for row in conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status ORDER BY status"):
    print(row)
conn.close()
PY
```

### 5) Identify stale running jobs

Use this to find jobs that are still `running` well past an expected threshold.

```bash
python - <<'PY'
import sqlite3
from datetime import datetime, timezone, timedelta
from opsbot import settings

STALE_AFTER_MINUTES = 15
now = datetime.now(timezone.utc)
conn = sqlite3.connect(settings.DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, job_type, started_at, requested_by_slack_user_id FROM jobs WHERE status = 'running' ORDER BY started_at ASC").fetchall()
for row in rows:
    started = datetime.fromisoformat(row['started_at'].replace('Z', '+00:00')) if row['started_at'] else None
    age = (now - started) if started else None
    if age and age > timedelta(minutes=STALE_AFTER_MINUTES):
        print({
            'id': row['id'],
            'job_type': row['job_type'],
            'requested_by_slack_user_id': row['requested_by_slack_user_id'],
            'started_at': row['started_at'],
            'age_minutes': round(age.total_seconds() / 60, 1),
        })
conn.close()
PY
```

### 6) Inspect worker heartbeat

```bash
python - <<'PY'
import sqlite3
from opsbot import settings
conn = sqlite3.connect(settings.DB_PATH)
row = conn.execute("SELECT key, value_text, updated_at FROM system_state WHERE key = 'worker_heartbeat'").fetchone()
print(row)
conn.close()
PY
```

If `updated_at` is old and jobs remain `running`, the worker may have crashed or become wedged.

## Safe recovery steps

Follow these steps in order.

### 1) Stop services

Stop both processes before making manual changes so they do not keep writing while you inspect the DB.

```bash
sudo systemctl stop opsbot-slack.service opsbot-worker.service
```

If running manually instead of systemd, terminate the `python -m opsbot.app` and `python -m opsbot.worker` processes.

### 2) Inspect the DB

Before changing anything, review the current queue state and confirm that no shell or admin tool still has the DB open.

```bash
python - <<'PY'
import sqlite3
from opsbot import settings
conn = sqlite3.connect(settings.DB_PATH)
conn.row_factory = sqlite3.Row
print('DB:', settings.DB_PATH)
print('Running jobs:')
for row in conn.execute("SELECT id, job_type, status, started_at, requested_by_slack_user_id FROM jobs WHERE status = 'running' ORDER BY started_at ASC"):
    print(dict(row))
print('Queued jobs:')
for row in conn.execute("SELECT id, job_type, status, created_at, requested_by_slack_user_id FROM jobs WHERE status = 'queued' ORDER BY created_at ASC"):
    print(dict(row))
conn.close()
PY
```

Optional consistency check:

```bash
sqlite3 "$(python - <<'PY'
from opsbot import settings
print(settings.DB_PATH)
PY
)" 'PRAGMA journal_mode; PRAGMA busy_timeout; PRAGMA integrity_check;'
```

Expected results:

- `journal_mode` should report `wal`
- `busy_timeout` should report `5000`
- `integrity_check` should report `ok`

### 3) Reset stale `running` jobs if appropriate

Only do this if you have stopped all services and are confident the job is not actively running.

Recommended approach: move stale `running` jobs back to `queued` so the worker can retry them after restart.

Preview the rows first:

```bash
sqlite3 "$(python - <<'PY'
from opsbot import settings
print(settings.DB_PATH)
PY
)" \
"SELECT id, job_type, status, started_at, finished_at FROM jobs WHERE status = 'running';"
```

Then reset them:

```bash
sqlite3 "$(python - <<'PY'
from opsbot import settings
print(settings.DB_PATH)
PY
)" \
"UPDATE jobs
SET status = 'queued',
    started_at = NULL,
    finished_at = NULL,
    error_text = NULL,
    last_error = COALESCE(last_error, 'Operator reset from stale running state')
WHERE status = 'running';"
```

If you need an audit trail, add a matching event entry manually after the reset:

```bash
sqlite3 "$(python - <<'PY'
from opsbot import settings
print(settings.DB_PATH)
PY
)" \
"INSERT INTO job_events (job_id, event_type, message, created_at)
SELECT id, 'operator_reset', 'Reset stale running job to queued', strftime('%Y-%m-%dT%H:%M:%SZ','now')
FROM jobs
WHERE status = 'queued' AND started_at IS NULL AND finished_at IS NULL;"
```

If a job is known to be unrecoverable, mark it `failed` instead of re-queuing it.

### 4) Restart services

```bash
sudo systemctl start opsbot-worker.service opsbot-slack.service
sudo systemctl status opsbot-worker.service --no-pager
sudo systemctl status opsbot-slack.service --no-pager
```

Then watch logs and submit a small test command.

```bash
sudo journalctl -u opsbot-worker.service -f
sudo journalctl -u opsbot-slack.service -f
```

## Prevention rules

Use these rules for any future queue or DB work in this repository.

1. **Single worker for SQLite**
   - Run exactly one background worker process against a SQLite DB.
   - Do not horizontally scale writers unless the backing database changes.

2. **Short transactions only**
   - Keep write transactions as small as possible.
   - Never perform network calls or slow computation while a DB write transaction is open.

3. **Ack Slack immediately**
   - Send Slack `ack()` before command parsing, queue writes, or any external work when possible.
   - Slow DB work after ack is still bad, but it is better than missing Slack's acknowledgement window.

4. **Use `BEGIN IMMEDIATE` for writes**
   - For write paths, acquire the write lock intentionally and early.
   - This codebase already supports that via `get_connection(begin_immediate=True)`.

5. **Set `busy_timeout`**
   - Every connection should set an appropriate busy timeout.
   - Avoid ad hoc scripts that connect without the same pragma configuration.

6. **Use WAL mode**
   - Keep `PRAGMA journal_mode=WAL` enabled.
   - WAL improves concurrency for readers, but still requires a single-writer operating model.

7. **Use a fresh connection per operation**
   - Do not reuse one global SQLite connection across threads or long-lived request handlers.
   - Prefer the existing `get_connection()` helper for isolated units of work.

## Notes for operators

- The application already follows several of these practices, so repeated lock incidents usually indicate an extra process, a manual DB session, or a stale `running` job after an abnormal stop.
- If lock incidents become frequent even with a single worker, consider moving from SQLite to a client/server database for queue state.
