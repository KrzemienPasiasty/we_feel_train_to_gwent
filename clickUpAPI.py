import os
import json
import datetime
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


def get_api_token(credentials_path: Optional[str] = None) -> str:
    """
    Retrieves the ClickUp personal API token from environment variable or credentials file.
    If the file does not exist, generates a template file with instructions.
    """
    if credentials_path is None:
        credentials_path = CREDENTIALS_FILE

    # 1. Check environment variable
    env_token = os.environ.get("CLICKUP_API_TOKEN")
    if env_token:
        return env_token.strip()

    # 2. Check JSON credentials file
    if os.path.exists(credentials_path):
        try:
            with open(credentials_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                api_token = cfg.get("api_token")
                if api_token and api_token != "YOUR_CLICKUP_PERSONAL_API_TOKEN":
                    return api_token.strip()
        except Exception:
            pass

    # 3. Create template if missing
    template = {
        "api_token": "YOUR_CLICKUP_PERSONAL_API_TOKEN",
        "note": "Get your token from ClickUp -> Settings -> Apps -> API Token -> Generate."
    }
    if not os.path.exists(credentials_path):
        with open(credentials_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=4)

    raise FileNotFoundError(
        f"ClickUp API token is not configured. A template was created at: {credentials_path}\n"
        "Please paste your personal API token into 'api_token' in clickup_credentials.json, "
        "or set the CLICKUP_API_TOKEN environment variable."
    )


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
                # Parse due date (ClickUp provides Unix timestamp in milliseconds)
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
                # Mapped to: 4=Urgent, 3=High, 2=Normal, 1=Low
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
    api_token: Optional[str] = None,
    credentials_path: Optional[str] = None,
    as_objects: bool = True,
    include_closed: bool = False,
    include_tags: Optional[bool] = None,
) -> List[Any]:
    """
    Downloads tasks from ClickUp using personal API token.
    
    :param api_token: Optional personal API token. If omitted, loaded from credentials file or env.
    :param credentials_path: Optional custom path to clickup_credentials.json.
    :param as_objects: If True (default), returns tasks converted to Task model instances.
    :param include_closed: Whether to include completed/closed tasks.
    :param include_tags: If True, populates task tags; if False, leaves tags empty. Defaults to INCLUDE_TAGS.
    :return: List of tasks (Task instances or dictionaries).
    """
    token = api_token if api_token else get_api_token(credentials_path)
    tasks = fetch_all_tasks(token, include_closed=include_closed)
    if as_objects:
        return [convert_to_task(t, include_tags=include_tags) for t in tasks]
    return tasks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download ClickUp tasks using Personal API Token")
    parser.add_argument("--token", type=str, default=None, help="ClickUp personal API token")
    parser.add_argument("--raw", action="store_true", help="Return raw dictionaries instead of Task objects")
    parser.add_argument("--include-closed", action="store_true", help="Include completed/closed tasks")
    parser.add_argument("--no-tags", action="store_true", help="Leave task tags empty")
    args = parser.parse_args()

    print("Fetching ClickUp tasks...")
    should_include_tags = False if args.no_tags else None
    tasks = download_tasks(
        api_token=args.token,
        as_objects=not args.raw,
        include_closed=args.include_closed,
        include_tags=should_include_tags,
    )
    print(f"Downloaded {len(tasks)} tasks:")
    for task in tasks:
        print(task)
