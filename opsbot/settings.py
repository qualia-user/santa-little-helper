import os
from pathlib import Path


def load_dotenv(path: str | None = None) -> None:
    if path is None:
        path = str(Path(__file__).resolve().parent.parent / '.env')
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), value)
    except FileNotFoundError:
        pass


def get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == '':
        return default
    return int(raw)


load_dotenv()

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DATA_DIR = PROJECT_DIR / 'data'
LOG_DIR = PROJECT_DIR / 'logs'
MIGRATIONS_DIR = PROJECT_DIR / 'migrations'
CACHE_DIR = DATA_DIR / 'cache'

for directory in (DATA_DIR, LOG_DIR, CACHE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN', '')
SLACK_APP_TOKEN = os.getenv('SLACK_APP_TOKEN', '')
SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET', '')

DATABASE_URL = os.getenv('DATABASE_URL', '')

OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3')
OLLAMA_TIMEOUT_SEC = get_int('OLLAMA_TIMEOUT_SEC', 180)

DEFAULT_LOOKBACK_HOURS = get_int('DEFAULT_LOOKBACK_HOURS', 24)
DEFAULT_MAX_EMAILS = get_int('DEFAULT_MAX_EMAILS', 50)
QUEUE_POLL_SECONDS = get_int('QUEUE_POLL_SECONDS', 2)

APP_LOG_PATH = str(LOG_DIR / 'app.log')
WORKER_LOG_PATH = str(LOG_DIR / 'worker.log')
