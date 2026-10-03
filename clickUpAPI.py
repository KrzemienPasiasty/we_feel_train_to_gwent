import os
import json
import datetime
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import List, Dict, Any, Optional
import requests

try:
    from task import Task
    from tag import Tag
    import data
except ImportError:
    Task = None
    Tag = None
    data = None

# Configuration variable: controls whether tags are read/created or left empty
INCLUDE_TAGS: bool = True
READ_TAGS: bool = True

CLICKUP_API_BASE = "https://api.clickup.com/api/v2"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "clickup_credentials.json")


def _get_token_path(user_id: Optional[str] = None) -> str:
    """Returns the token storage file path for a specific user or default."""
    filename = f"clickup_token_{user_id}.json" if user_id else "clickup_token.json"
    return os.path.join(BASE_DIR, filename)


def get_credentials(credentials_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieves ClickUp credentials from environment variables or credentials file.
    If neither exists, generates a template file with instructions.
    """
    if credentials_path is None:
        credentials_path = CREDENTIALS_FILE

    # 1. Environment variables check
    env_api_token = os.environ.get("CLICKUP_API_TOKEN")
    if env_api_token:
        return {"api_token": env_api_token.strip()}

    env_client_id = os.environ.get("CLICKUP_CLIENT_ID")
    env_client_secret = os.environ.get("CLICKUP_CLIENT_SECRET")
    if env_client_id and env_client_secret:
        return {
            "client_id": env_client_id.strip(),
            "client_secret": env_client_secret.strip(),
        }

    # 2. JSON credentials file check
    if os.path.exists(credentials_path):
        try:
            with open(credentials_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                api_token = cfg.get("api_token")
                if api_token and api_token != "YOUR_CLICKUP_PERSONAL_API_TOKEN":
                    return {"api_token": api_token.strip()}

                client_id = cfg.get("client_id")
                client_secret = cfg.get("client_secret")
                if (
                    client_id
                    and client_secret
                    and client_id != "YOUR_CLICKUP_CLIENT_ID"
                    and client_secret != "YOUR_CLICKUP_CLIENT_SECRET"
                ):
                    return {
                        "client_id": client_id.strip(),
                        "client_secret": client_secret.strip(),
                        "redirect_uri": cfg.get("redirect_uri", "http://localhost:8080/callback"),
                    }
        except Exception:
            pass

    # 3. Create template file if missing
    template = {
        "api_token": "YOUR_CLICKUP_PERSONAL_API_TOKEN",
        "client_id": "YOUR_CLICKUP_CLIENT_ID",
        "client_secret": "YOUR_CLICKUP_CLIENT_SECRET",
        "redirect_uri": "http://localhost:8080/callback",
        "note": (
            "OPTION 1 (Easiest): Put your Personal API Token in 'api_token' "
            "(ClickUp -> Settings -> Apps -> API Token -> Generate).\n"
            "OPTION 2 (OAuth flow): Fill 'client_id' and 'client_secret' from "
            "ClickUp -> Settings -> Integrations -> ClickUp API -> Create App."
        ),
    }
    if not os.path.exists(credentials_path):
        with open(credentials_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=4)

    raise FileNotFoundError(
        f"ClickUp credentials are not configured. A template was created at: {credentials_path}\n"
        "Either:\n"
        "  1) Paste your personal API token into 'api_token' in clickup_credentials.json,\n"
        "  2) Or configure client_id and client_secret for OAuth login."
    )


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    code: Optional[str] = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _OAuthCallbackHandler.code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this browser window.</p>")
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication failed.</h1>")

    def log_message(self, format, *args):
        # Silence local server request logs
        return


def _run_oauth_flow(client_id: str, client_secret: str, redirect_uri: str = "http://localhost:8080/callback") -> str:
    """Runs a local browser-based OAuth 2.0 flow to acquire an access token."""
    parsed_redirect = urllib.parse.urlparse(redirect_uri)
    port = parsed_redirect.port or 8080

    auth_url = (
        f"https://app.clickup.com/api?client_id={urllib.parse.quote(client_id)}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
    )

    print(f"Opening browser for ClickUp authentication: {auth_url}")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", port), _OAuthCallbackHandler)
    _OAuthCallbackHandler.code = None

    while _OAuthCallbackHandler.code is None:
        server.handle_request()

    server.server_close()
    code = _OAuthCallbackHandler.code

    token_url = f"{CLICKUP_API_BASE}/oauth/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }
    resp = requests.post(token_url, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to exchange OAuth code for token ({resp.status_code}): {resp.text}")

    token_data = resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError(f"Token response did not include access_token: {token_data}")
    return access_token


def get_auth_token(
    user_id: Optional[str] = None,
    force_login: bool = False,
    token_path: Optional[str] = None,
    credentials_path: Optional[str] = None,
) -> str:
    """
    Acquires a valid ClickUp access token.
    Supports cached personal API tokens and OAuth tokens per user.
    """
    creds = get_credentials(credentials_path)

    # If a personal API token is directly configured, use it
    if "api_token" in creds and not force_login:
        return creds["api_token"]

    if token_path is None:
        token_path = _get_token_path(user_id)

    # Check cached token
    if not force_login and os.path.exists(token_path):
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                data_json = json.load(f)
                access_token = data_json.get("access_token")
                if access_token:
                    return access_token
        except Exception:
            pass

    # If OAuth credentials exist, run OAuth flow
    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")
    redirect_uri = creds.get("redirect_uri", "http://localhost:8080/callback")

    if client_id and client_secret:
        access_token = _run_oauth_flow(client_id, client_secret, redirect_uri)
        with open(token_path, "w", encoding="utf-8") as f:
            json.dump({"access_token": access_token}, f, indent=4)
        return access_token

    if "api_token" in creds:
        return creds["api_token"]

    raise RuntimeError("No valid ClickUp authentication method found.")


def logout(user_id: Optional[str] = None, token_path: Optional[str] = None) -> bool:
    """
    Logs out the user by deleting their stored token file.
    
    :return: True if token was found and deleted, False otherwise.
    """
    if token_path is None:
        token_path = _get_token_path(user_id)
    if os.path.exists(token_path):
        os.remove(token_path)
        return True
    return False


def _get_headers(token: str) -> Dict[str, str]:
    """Generates ClickUp authorization headers."""
    return {"Authorization": token, "Content-Type": "application/json"}


def fetch_all_tasks(token: str, include_closed: bool = False) -> List[Dict[str, Any]]:
    """
    Fetches all tasks accessible by the user across all Workspaces (Teams).
    """
    headers = _get_headers(token)

    # 1. Fetch user's authorized workspaces (teams)
    teams_resp = requests.get(f"{CLICKUP_API_BASE}/team", headers=headers)
    if teams_resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch ClickUp teams ({teams_resp.status_code}): {teams_resp.text}")

    teams_data = teams_resp.json().get("teams", [])
    all_tasks: List[Dict[str, Any]] = []

    for team in teams_data:
        team_id = team["id"]
        team_name = team.get("name", "ClickUp")

        # 2. Fetch tasks for each team with pagination
        page = 0
        while True:
            params = {
                "page": page,
                "include_closed": "true" if include_closed else "false",
                "subtasks": "true",
            }
            tasks_resp = requests.get(f"{CLICKUP_API_BASE}/team/{team_id}/task", headers=headers, params=params)
            if tasks_resp.status_code != 200:
                print(f"Warning: Failed to fetch tasks for team {team_id} ({tasks_resp.status_code}): {tasks_resp.text}")
                break

            data_json = tasks_resp.json()
            tasks = data_json.get("tasks", [])
            if not tasks:
                break

            for t in tasks:
                # Parse due date (ClickUp provides Unix timestamp in milliseconds as string or int)
                due = None
                raw_due = t.get("due_date")
                if raw_due:
                    try:
                        due_ts = int(raw_due) / 1000.0
                        due = datetime.datetime.fromtimestamp(due_ts, tz=datetime.timezone.utc)
                    except Exception:
                        due = None

                # Parse priority: higher number = more urgent
                # ClickUp priority: 1=Urgent, 2=High, 3=Normal, 4=Low, None=No priority
                # Mapped to: 4=Urgent, 3=High, 2=Normal, 1=Low, 0=None
                p_obj = t.get("priority")
                if isinstance(p_obj, dict):
                    raw_p = p_obj.get("orderindex") or p_obj.get("id")
                    try:
                        raw_p = int(raw_p)
                    except (ValueError, TypeError):
                        raw_p = None
                else:
                    raw_p = None

                if raw_p == 1:
                    priority = 4  # Urgent
                elif raw_p == 2:
                    priority = 3  # High
                elif raw_p == 3:
                    priority = 2  # Normal
                elif raw_p == 4:
                    priority = 1  # Low
                else:
                    priority = 2  # Default normal

                # List / Folder / Space names
                list_name = t.get("list", {}).get("name", team_name)
                tags = [tag.get("name", "") for tag in t.get("tags", []) if isinstance(tag, dict)]

                all_tasks.append({
                    "id": t.get("id"),
                    "title": t.get("name", ""),
                    "notes": t.get("text_content") or t.get("description"),
                    "due": due,
                    "list": list_name,
                    "source": "ClickUp",
                    "priority": priority,
                    "status": t.get("status", {}).get("status"),
                    "tags": tags,
                    "url": t.get("url"),
                    "updated": t.get("date_updated"),
                })

            if data_json.get("last_page", False):
                break
            page += 1

    return all_tasks


def convert_to_task(
    cu_task: Dict[str, Any],
    task_id: Optional[int] = None,
    include_tags: Optional[bool] = None,
) -> Optional[Any]:
    """Converts a raw ClickUp task dictionary to the project's Task model."""
    if Task is None:
        return None

    if include_tags is None:
        include_tags = INCLUDE_TAGS and READ_TAGS

    task = Task()
    if task_id is not None:
        task.id = task_id
    elif data is not None and hasattr(data, "last_ID"):
        data.last_ID += 1
        task.id = data.last_ID
    else:
        task.id = 1

    title = cu_task.get("title", "")
    notes = cu_task.get("notes")
    task.description = f"{title}\n{notes}".strip() if notes else title
    task.deadline = cu_task.get("due")
    task.time = None
    task.priority = cu_task.get("priority", 2)
    task.tags = []

    # Tag with list name and ClickUp tags if enabled
    if include_tags and Tag is not None:
        list_name = cu_task.get("list")
        if list_name:
            try:
                t_list = Tag(list_name)
                t_list.title = list_name
                t_list.color = (123, 104, 238)  # ClickUp purple
                task.tags.append(t_list)
            except Exception:
                pass

        for tag_str in cu_task.get("tags", []):
            try:
                t_item = Tag(tag_str)
                t_item.title = tag_str
                t_item.color = (70, 70, 70)
                task.tags.append(t_item)
            except Exception:
                pass

    task.llm_metadata = ""
    return task


def download_tasks(
    user_id: Optional[str] = None,
    force_login: bool = False,
    as_objects: bool = True,
    include_closed: bool = False,
    include_tags: Optional[bool] = None,
) -> List[Any]:
    """
    Logs in or uses configured token and downloads tasks from ClickUp.
    
    :param user_id: Optional user identifier for separate token storage.
    :param force_login: If True, forces re-authentication.
    :param as_objects: If True (default), returns tasks converted to Task model instances.
    :param include_closed: Whether to include completed/closed tasks.
    :param include_tags: If True, populates task tags; if False, leaves tags empty. Defaults to INCLUDE_TAGS.
    :return: List of tasks (Task instances or dictionaries).
    """
    token = get_auth_token(user_id=user_id, force_login=force_login)
    tasks = fetch_all_tasks(token, include_closed=include_closed)
    if as_objects:
        return [convert_to_task(t, include_tags=include_tags) for t in tasks]
    return tasks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Log in to ClickUp and download tasks")
    parser.add_argument("--login", action="store_true", help="Force new login / token refresh")
    parser.add_argument("--logout", action="store_true", help="Log out (remove saved token)")
    parser.add_argument("--user", type=str, default=None, help="User ID or account identifier")
    parser.add_argument("--raw", action="store_true", help="Return raw dictionaries instead of Task objects")
    parser.add_argument("--include-closed", action="store_true", help="Include completed/closed tasks")
    parser.add_argument("--no-tags", action="store_true", help="Leave task tags empty")
    args = parser.parse_args()

    if args.logout:
        if logout(user_id=args.user):
            target = f"user '{args.user}'" if args.user else "default account"
            print(f"Logged out successfully for {target}.")
        else:
            print("No saved token found.")
    else:
        print("Fetching ClickUp tasks...")
        should_include_tags = False if args.no_tags else None
        tasks = download_tasks(
            user_id=args.user,
            force_login=args.login,
            as_objects=not args.raw,
            include_closed=args.include_closed,
            include_tags=should_include_tags,
        )
        print(f"Downloaded {len(tasks)} tasks:")
        for task in tasks:
            print(task)
