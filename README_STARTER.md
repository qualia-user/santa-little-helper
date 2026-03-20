# opsbot starter skeleton

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Database setup
Set `DATABASE_URL` in `.env` before starting the app or worker. The PostgreSQL schema is expected to be created manually before first use.

## Seed a Slack user mapping
Insert a row into `slack_users` before testing digest commands.

## Run the worker
```bash
python -m opsbot.worker
```

## Run the Slack app (Socket Mode / command receiver)
```bash
python -m opsbot.app
```

## systemd on Raspberry Pi / Linux
Service files live in `deploy/systemd/`:

- `opsbot-slack.service` runs the Slack Socket Mode receiver.
- `opsbot-worker.service` runs the background job processor.

Install them with:

```bash
sudo cp deploy/systemd/opsbot-slack.service /etc/systemd/system/
sudo cp deploy/systemd/opsbot-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now opsbot-slack.service opsbot-worker.service
```

Debug with:

```bash
sudo journalctl -u opsbot-slack.service -f
sudo journalctl -u opsbot-worker.service -f
```

## Local manual digest test
```bash
python -m opsbot.cli.run_digest --profile-key domagoj --hours 6 --max-emails 10
```
