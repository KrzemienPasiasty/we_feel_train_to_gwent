import os
import re
import json
import datetime
from typing import List, Dict, Any, Optional
import requests
import msal

try:
    from task import Task
    from tag import Tag
    import data
except ImportError:
    try:
        from we_feel_train_to_gwent.task import Task
        from we_feel_train_to_gwent.tag import Tag
        from we_feel_train_to_gwent import data
    except ImportError:
        Task = None
        Tag = None
        data = None

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Tasks.Read", "User.Read"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "microsoft_credentials.json")


def _get_token_path(user_id: Optional[str] = None) -> str:
    """Returns the token cache file path for a specific user or default."""
    filename = f"ms_token_{user_id}.json" if user_id else "ms_token.json"
    return os.path.join(BASE_DIR, filename)


def get_client_id(credentials_path: Optional[str] = None) -> str:
    """
    Retrieves the Microsoft Application (client) ID from environment or credentials file.
    If the file does not exist, generates a template file with instructions.
    """
    if credentials_path is None:
        credentials_path = CREDENTIALS_FILE

    # 1. Environment variable check
    env_id = os.environ.get("MICROSOFT_CLIENT_ID")
    if env_id:
        return env_id.strip()

    # 2. JSON credentials file check
    if os.path.exists(credentials_path):
        try:
            with open(credentials_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                client_id = cfg.get("client_id")
                if client_id and client_id != "YOUR_MICROSOFT_CLIENT_ID":
                    return client_id.strip()
        except Exception:
            pass

    # 3. Create template file if missing
    template = {
        "client_id": "YOUR_MICROSOFT_CLIENT_ID",
        "tenant_id": "common",
        "note": "Get your client_id from Azure Portal -> App registrations -> Authentication -> Mobile and desktop applications (redirect URI: http://localhost)."
    }
    if not os.path.exists(credentials_path):
        with open(credentials_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=4)

    raise FileNotFoundError(
        f"Microsoft Client ID is not configured. A template was created at: {credentials_path}\n"
        "Please edit this file and enter your Azure Application (client) ID, "
        "or set the MICROSOFT_CLIENT_ID environment variable."
    )


def get_auth_token(
    user_id: Optional[str] = None,
    force_login: bool = False,
    use_device_code: bool = False,
    token_path: Optional[str] = None,
    credentials_path: Optional[str] = None,
) -> str:
    """
    Acquires a valid Microsoft Graph access token using MSAL.
    Supports token caching, account selection, and multi-user login.
    """
    client_id = get_client_id(credentials_path)
    if token_path is None:
        token_path = _get_token_path(user_id)

    cache = msal.SerializableTokenCache()
    if not force_login and os.path.exists(token_path):
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                cache.deserialize(f.read())
        except Exception:
            pass

    app = msal.PublicClientApplication(
        client_id=client_id,
        authority="https://login.microsoftonline.com/common",
        token_cache=cache,
    )

    accounts = app.get_accounts()
    result = None

    if accounts and not force_login:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        if use_device_code:
            flow = app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise RuntimeError(f"Failed to create device flow: {flow.get('error_description', flow)}")
            print("\n" + "=" * 60)
            print(flow["message"])
            print("=" * 60 + "\n")
            result = app.acquire_token_by_device_flow(flow)
        else:
            # Opens default web browser with account selection prompt
            try:
                result = app.acquire_token_interactive(
                    scopes=SCOPES,
                    prompt="select_account",
                )
            except Exception as e:
                result = {"error": str(e)}

    if cache.has_state_changed:
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(cache.serialize())

    if "access_token" in result:
        return result["access_token"]

    error_desc = result.get("error_description", result.get("error", "Unknown authorization error"))
    if "AADSTS90023" in error_desc or "Single-Page Application" in error_desc:
        raise RuntimeError(
            "\n" + "!" * 70 + "\n"
            "AZURE CONFIGURATION ERROR:\n"
            "In Azure Portal -> App registrations -> Authentication:\n"
            "1. You registered http://localhost under 'Single-page application' (SPA).\n"
            "2. Python desktop apps must use 'Mobile and desktop applications'!\n"
            "Fix:\n"
            "  - In Azure Portal, click 'Add a platform' -> 'Mobile and desktop applications'.\n"
            "  - Check 'http://localhost' and click Configure.\n"
            "  - Delete the 'Single-page application' platform.\n"
            "  - Under 'Advanced settings' -> 'Allow public client flows', select 'Yes'.\n"
            "  - Click Save.\n"
            "!" * 70
        )
    raise RuntimeError(f"Authentication failed: {error_desc}")


def logout(user_id: Optional[str] = None, token_path: Optional[str] = None) -> bool:
    """
    Logs out the user by removing their stored token cache file.
    
    :return: True if token was found and deleted, False otherwise.
    """
    if token_path is None:
        token_path = _get_token_path(user_id)
    if os.path.exists(token_path):
        os.remove(token_path)
        return True
    return False


def _clean_html(raw_html: str) -> str:
    """Helper to strip simple HTML tags from task body content."""
    clean = re.sub(r"<[^>]+>", "", raw_html)
    return clean.strip()


def fetch_todo_tasks(access_token: str) -> List[Dict[str, Any]]:
    """Fetches non-completed tasks from Microsoft To Do across all task lists."""
    headers = {"Authorization": f"Bearer {access_token}"}
    tasks = []

    # 1. Fetch all To Do task lists
    lists_url = f"{GRAPH_API_BASE}/me/todo/lists"
    while lists_url:
        resp = requests.get(lists_url, headers=headers)
        if resp.status_code != 200:
            print(f"Warning: Failed to fetch To Do lists ({resp.status_code}): {resp.text}")
            break
        data = resp.json()
        task_lists = data.get("value", [])

        for tl in task_lists:
            list_id = tl["id"]
            list_title = tl.get("displayName", "To Do")

            # 2. Fetch open tasks for list
            tasks_url = f"{GRAPH_API_BASE}/me/todo/lists/{list_id}/tasks?$filter=status ne 'completed'"
            while tasks_url:
                t_resp = requests.get(tasks_url, headers=headers)
                if t_resp.status_code != 200:
                    break
                t_data = t_resp.json()

                for t in t_data.get("value", []):
                    # Parse due datetime
                    due = None
                    due_obj = t.get("dueDateTime")
                    if due_obj and due_obj.get("dateTime"):
                        due_str = due_obj["dateTime"]
                        try:
                            # Graph API gives e.g. '2026-10-05T00:00:00.0000000'
                            due = datetime.datetime.fromisoformat(due_str.split(".")[0])
                        except Exception:
                            due = None

                    # Parse body content
                    body = t.get("body", {})
                    notes = body.get("content", "")
                    if body.get("contentType") == "html":
                        notes = _clean_html(notes)

                    # Map importance: higher number = more urgent
                    # low -> 1, normal (base) -> 2, high (urgent / starred) -> 3
                    importance = str(t.get("importance", "normal")).lower()
                    if importance == "high":
                        priority = 3
                    elif importance == "normal":
                        priority = 2
                    else:
                        priority = 1

                    tasks.append({
                        "id": t["id"],
                        "title": t.get("title", ""),
                        "notes": notes if notes else None,
                        "due": due,
                        "list": list_title,
                        "source": "Microsoft To Do",
                        "priority": priority,
                        "updated": t.get("lastModifiedDateTime"),
                    })

                tasks_url = t_data.get("@odata.nextLink")

        lists_url = data.get("@odata.nextLink")

    return tasks


def fetch_planner_tasks(access_token: str) -> List[Dict[str, Any]]:
    """
    Fetches tasks assigned to the current user in Microsoft Planner.
    Note: Requires an organizational/work Microsoft 365 account with Planner enabled.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    tasks = []
    plan_names_cache: Dict[str, str] = {}

    url = f"{GRAPH_API_BASE}/me/planner/tasks"
    while url:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 403 or resp.status_code == 400:
            # Personal Microsoft accounts do not support Planner
            print("Notice: Microsoft Planner is only available for work/school (M365) accounts. Skipping Planner.")
            return []
        if resp.status_code != 200:
            print(f"Warning: Failed to fetch Planner tasks ({resp.status_code}): {resp.text}")
            break

        data = resp.json()
        for t in data.get("value", []):
            if t.get("percentComplete", 0) == 100:
                continue  # Skip completed tasks

            # Resolve plan name
            plan_id = t.get("planId")
            plan_title = "Planner"
            if plan_id:
                if plan_id not in plan_names_cache:
                    p_resp = requests.get(f"{GRAPH_API_BASE}/planner/plans/{plan_id}", headers=headers)
                    if p_resp.status_code == 200:
                        plan_names_cache[plan_id] = p_resp.json().get("title", "Planner")
                    else:
                        plan_names_cache[plan_id] = "Planner"
                plan_title = plan_names_cache[plan_id]

            # Parse due date
            due = None
            due_str = t.get("dueDateTime")
            if due_str:
                try:
                    due = datetime.datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                except Exception:
                    due = None

            # Map Planner priority: higher number = more urgent
            # Graph API returns: 1=Urgent, 3=Important, 5=Medium, 9=Low
            # Mapped to: 4=Urgent, 3=Important, 2=Medium, 1=Low
            raw_priority = t.get("priority", 5)
            if raw_priority <= 1:
                priority = 4
            elif raw_priority <= 3:
                priority = 3
            elif raw_priority <= 5:
                priority = 2
            else:
                priority = 1

            tasks.append({
                "id": t["id"],
                "title": t.get("title", ""),
                "notes": None,
                "due": due,
                "list": plan_title,
                "source": "Microsoft Planner",
                "priority": priority,
                "updated": t.get("createdDateTime"),
            })

        url = data.get("@odata.nextLink")

    return tasks


def fetch_all_tasks(
    access_token: str,
    include_todo: bool = True,
    include_planner: bool = True,
) -> List[Dict[str, Any]]:
    """Fetches tasks from both Microsoft To Do and Microsoft Planner."""
    all_tasks = []
    if include_todo:
        all_tasks.extend(fetch_todo_tasks(access_token))
    if include_planner:
        all_tasks.extend(fetch_planner_tasks(access_token))
    return all_tasks


def convert_to_task(ms_task: Dict[str, Any], task_id: Optional[int] = None) -> Optional[Any]:
    if Task is None:
        return None
    
    task = Task()
    task.id = task_id if task_id is not None else 1
    task.source = f"microsoft:{ms_task.get('source') or 'todo'}"
    task.external_id = str(ms_task.get("id", "")) or None
    
    title = ms_task.get("title", "")
    notes = ms_task.get("notes")
    task.description = f"{title}\n{notes}".strip() if notes else title
    task.deadline = ms_task.get("due")
    
    # Uzupełnienie wymaganych i domyślnych pól
    task.time = None
    task.start = None
    task.focus = 0  # Domyślne skupienie
    task.priority = ms_task.get("priority", 2)
    task.tags = []
    
    list_name = ms_task.get("list")
    source = ms_task.get("source")
    
    if Tag is not None:
        if list_name:
            # Poprawna inicjalizacja: id, title, color, is_interactive
            t1 = Tag(0, list_name, (31, 83, 141), False)
            task.tags.append(t1)
            
        if source:
            t2 = Tag(0, source, (0, 120, 215), False)
            task.tags.append(t2)
            
    task.llm_metadata = "Zaimportowano z Microsoft"
    return task


def download_tasks(
    user_id: Optional[str] = None,
    force_login: bool = False,
    use_device_code: bool = False,
    as_objects: bool = True,
    include_todo: bool = True,
    include_planner: bool = True,
) -> List[Any]:
    """
    Logs in the user to their Microsoft account and downloads tasks from To Do and Planner.
    
    :param user_id: Optional user identifier for separate token storage.
    :param force_login: If True, opens the Microsoft login screen with account picker.
    :param use_device_code: If True, uses the device code login flow (URL + code).
    :param as_objects: If True (default), returns tasks converted to Task model instances.
    :param include_todo: Whether to fetch from Microsoft To Do.
    :param include_planner: Whether to fetch from Microsoft Planner.
    :return: List of tasks (Task instances or dictionaries).
    """
    token = get_auth_token(user_id=user_id, force_login=force_login, use_device_code=use_device_code)
    tasks = fetch_all_tasks(token, include_todo=include_todo, include_planner=include_planner)
    if as_objects:
        return [convert_to_task(t) for t in tasks]
    return tasks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Log in to Microsoft and download To Do & Planner tasks")
    parser.add_argument("--login", action="store_true", help="Force new login / account selection")
    parser.add_argument("--logout", action="store_true", help="Log out (remove saved token)")
    parser.add_argument("--device-code", action="store_true", help="Use device code flow (browser + code)")
    parser.add_argument("--user", type=str, default=None, help="User ID or account identifier")
    parser.add_argument("--raw", action="store_true", help="Return raw dictionaries instead of Task objects")
    parser.add_argument("--no-todo", action="store_true", help="Skip Microsoft To Do")
    parser.add_argument("--no-planner", action="store_true", help="Skip Microsoft Planner")
    args = parser.parse_args()

    if args.logout:
        if logout(user_id=args.user):
            target = f"user '{args.user}'" if args.user else "default account"
            print(f"Logged out successfully for {target}.")
        else:
            print("No saved token found.")
    else:
        print("Fetching Microsoft tasks...")
        tasks = download_tasks(
            user_id=args.user,
            force_login=args.login,
            use_device_code=args.device_code,
            as_objects=not args.raw,
            include_todo=not args.no_todo,
            include_planner=not args.no_planner,
        )
        print(f"Downloaded {len(tasks)} tasks:")
        for task in tasks:
            print(task)
