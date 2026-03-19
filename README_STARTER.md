# opsbot starter skeleton

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run DB init implicitly
The app and worker both call `initialize_database()` on startup.

## Seed a Slack user mapping
Insert a row into `slack_users` before testing digest commands.

## Run the worker
```bash
python -m opsbot.worker
```

## Run the Slack app (Socket Mode)
```bash
python -m opsbot.app
```

## Local manual digest test
```bash
python -m opsbot.cli.run_digest --profile-key domagoj --hours 6 --max-emails 10
```
