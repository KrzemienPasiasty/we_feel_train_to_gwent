import os
import datetime
from typing import List, Dict, Any, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

try:
    from task import Task
    from tag import Tag
    import data
except ImportError:
        Task = None
        Tag = None
        data = None

SCOPES = ["https://www.googleapis.com/auth/tasks.readonly"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")


def _get_token_path(user_id: Optional[str] = None) -> str:
    """Returns the token file path for a specific user or default."""
    filename = f"token_{user_id}.json" if user_id else "token.json"
    return os.path.join(BASE_DIR, filename)


def get_creds(
    user_id: Optional[str] = None,
    force_login: bool = False,
    token_path: Optional[str] = None,
    credentials_path: Optional[str] = None,
) -> Credentials:
    """
    Retrieves or generates valid Google OAuth credentials.
    
    :param user_id: Identifier for user (allows different users to have separate tokens).
    :param force_login: If True, forces the browser authentication flow with account picker.
    :param token_path: Optional custom path to token.json.
    :param credentials_path: Optional custom path to credentials.json.
    :return: Credentials instance.
    """
    if token_path is None:
        token_path = _get_token_path(user_id)
    if credentials_path is None:
        credentials_path = CREDENTIALS_FILE

    creds = None
    if not force_login and os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token and not force_login:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Credentials file not found at '{credentials_path}'. "
                    "Please download OAuth client credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            # prompt='select_account' allows the user to choose or log in with their own account
            creds = flow.run_local_server(port=0, prompt="select_account")

        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds


def logout(user_id: Optional[str] = None, token_path: Optional[str] = None) -> bool:
    """
    Logs out the user by removing their stored token file.
    
    :return: True if token was found and deleted, False otherwise.
    """
    if token_path is None:
        token_path = _get_token_path(user_id)
    if os.path.exists(token_path):
        os.remove(token_path)
        return True
    return False


def get_service(user_id: Optional[str] = None, force_login: bool = False):
    """Builds and returns the Google Tasks API service."""
    creds = get_creds(user_id=user_id, force_login=force_login)
    return build("tasks", "v1", credentials=creds)


def fetch_all_tasks(service) -> List[Dict[str, Any]]:
    """Fetches all tasks across all task lists for the authenticated service."""
    result = []
    lists = service.tasklists().list(maxResults=100).execute().get("items", [])
    for tl in lists:
        page_token = None
        while True:
            resp = service.tasks().list(
                tasklist=tl["id"],
                showCompleted=False,  # only open tasks
                showHidden=False,
                maxResults=100,
                pageToken=page_token,
            ).execute()
            for t in resp.get("items", []):
                result.append({
                    "id": t["id"],
                    "title": t.get("title", ""),
                    "notes": t.get("notes"),
                    "due": (
                        datetime.datetime.fromisoformat(t["due"].replace("Z", "+00:00"))
                        if t.get("due")
                        else None
                    ),
                    "list": tl.get("title", ""),
                    "parent": t.get("parent"),  # subtasks
                    "updated": t.get("updated"),
                })
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    return result


def convert_to_task(google_task: Dict[str, Any], task_id: Optional[int] = None) -> Optional[Any]:
    if Task is None:
        return None
    
    task = Task()
    task.id = task_id if task_id is not None else 1
    task.source = "google"
    task.external_id = google_task.get("id")
    
    title = google_task.get("title", "")
    notes = google_task.get("notes")
    task.description = f"{title}\n{notes}".strip() if notes else title
    task.deadline = google_task.get("due")
    
    # Uzupełnienie wymaganych i domyślnych pól
    task.time = None
    task.start = None
    task.focus = 0  
    task.priority = 1  # Wcześniej było None, zamieniamy na bezpieczne 1
    task.tags = []
    task.llm_metadata = "Zaimportowano z Google"
    
    return task

def download_tasks(
    user_id: Optional[str] = None,
    force_login: bool = False,
    as_objects: bool = True,
) -> List[Any]:
    """
    Logs in the user (if not already logged in or force_login=True) and downloads their tasks.
    
    :param user_id: Optional user identifier (e.g. username/email) to support multiple accounts.
    :param force_login: If True, opens the Google OAuth screen to select or switch accounts.
    :param as_objects: If True (default), returns tasks converted to Task model instances.
    :return: List of tasks (Task instances by default, or dictionaries if as_objects=False).
    """
    service = get_service(user_id=user_id, force_login=force_login)
    tasks = fetch_all_tasks(service)
    if as_objects:
        return [convert_to_task(t) for t in tasks]
    return tasks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Log in to Google and download Google Tasks")
    parser.add_argument("--login", action="store_true", help="Force new login / account selection")
    parser.add_argument("--logout", action="store_true", help="Log out (remove saved token)")
    parser.add_argument("--user", type=str, default=None, help="User ID or account identifier")
    parser.add_argument("--raw", action="store_true", help="Return raw dictionaries instead of Task objects")
    args = parser.parse_args()

    if args.logout:
        if logout(user_id=args.user):
            target = f"user '{args.user}'" if args.user else "default account"
            print(f"Logged out successfully for {target}.")
        else:
            print("No saved token found.")
    else:
        print("Fetching tasks...")
        tasks = download_tasks(user_id=args.user, force_login=args.login, as_objects=not args.raw)
        print(f"Downloaded {len(tasks)} tasks:")
        for task in tasks:
            print(task)
