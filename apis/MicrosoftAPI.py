import os
import sys
import json
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _resolve_file(filename: str) -> str:
    root_path = os.path.join(PROJECT_ROOT, filename)
    if os.path.exists(root_path):
        return root_path
    return os.path.join(BASE_DIR, filename)


UNIFIED_CREDENTIALS_FILE = _resolve_file("api_credentials.json")
CREDENTIALS_FILE = _resolve_file("microsoft_credentials.json")


def _get_token_path(user_id: Optional[str] = None) -> str:
    """Returns the token cache file path for a specific user or default."""
    filename = f"ms_token_{user_id}.json" if user_id else "ms_token.json"
    return _resolve_file(filename)


def get_client_id(credentials_path: Optional[str] = None) -> str:
    """
    Retrieves the Microsoft Application (client) ID from environment or credentials file.
    Checks unified api_credentials.json first, then microsoft_credentials.json.
    """
    # 1. Environment variable check
    env_id = os.environ.get("MICROSOFT_CLIENT_ID")
    if env_id:
        return env_id.strip()

    # 2. Check unified api_credentials.json
    if os.path.exists(UNIFIED_CREDENTIALS_FILE):
        try:
            with open(UNIFIED_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                ms_cfg = cfg.get("microsoft", {})
                client_id = ms_cfg.get("client_id")
                if client_id and client_id != "YOUR_MICROSOFT_CLIENT_ID":
                    return client_id.strip()
        except Exception:
            pass

    # 3. Check standalone JSON credentials file
    if credentials_path is None:
        credentials_path = CREDENTIALS_FILE

    if os.path.exists(credentials_path):
        try:
            with open(credentials_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                client_id = cfg.get("client_id")
                if client_id and client_id != "YOUR_MICROSOFT_CLIENT_ID":
                    return client_id.strip()
        except Exception:
            pass

    raise FileNotFoundError(
        f"Microsoft Client ID is not configured. Please fill 'client_id' in "
        f"'{UNIFIED_CREDENTIALS_FILE}' under the 'microsoft' section, or set MICROSOFT_CLIENT_ID."
    )
