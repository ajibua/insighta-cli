import json
import os
from pathlib import Path
from typing import Optional

CREDS_DIR = Path.home() / ".insighta"
CREDS_FILE = CREDS_DIR / "credentials.json"


def save_credentials(access_token: str, refresh_token: str, username: str, api_url: str) -> None:
    CREDS_DIR.mkdir(parents=True, exist_ok=True)
    CREDS_FILE.write_text(json.dumps({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "username": username,
        "api_url": api_url,
    }, indent=2))
    try:
        CREDS_FILE.chmod(0o600)
    except OSError:
        pass  # chmod may fail on Windows


def load_credentials() -> Optional[dict]:
    if not CREDS_FILE.exists():
        return None
    try:
        return json.loads(CREDS_FILE.read_text())
    except Exception:
        return None


def clear_credentials() -> None:
    if CREDS_FILE.exists():
        CREDS_FILE.unlink()


def get_api_url() -> str:
    creds = load_credentials()
    if creds:
        return creds.get("api_url", "").rstrip("/")
    return os.getenv("INSIGHTA_API_URL", "http://127.0.0.1:8000").rstrip("/")
