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

TODOIST_API_BASE = "https://api.todoist.com/rest/v2"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIFIED_CREDENTIALS_FILE = os.path.join(BASE_DIR, "api_credentials.json")


def get_api_token(credentials_path: Optional[str] = None) -> str:
    """
    Retrieves Todoist API token from environment variable or credentials file.
    """
    # 1. Environment variable
    env_token = os.environ.get("TODOIST_API_TOKEN")
    if env_token:
        return env_token.strip()

    # 2. Unified credentials file
    cred_file = credentials_path or UNIFIED_CREDENTIALS_FILE
    if os.path.exists(cred_file):
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                td_cfg = cfg.get("todoist", {})
                token = td_cfg.get("api_token")
                if token and token != "YOUR_TODOIST_API_TOKEN":
                    return token.strip()
        except Exception:
            pass

    raise FileNotFoundError(
        "Todoist API token is not configured. Please fill 'api_token' in "
        f"'{cred_file}' under the 'todoist' section, or set TODOIST_API_TOKEN."
    )


def _get_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def fetch_projects_map(token: str) -> Dict[str, str]:
    """Fetches user projects to map project_id to project name."""
    headers = _get_headers(token)
    try:
        resp = requests.get(f"{TODOIST_API_BASE}/projects", headers=headers)
        if resp.status_code == 200:
            return {p["id"]: p.get("name", "Project") for p in resp.json()}
    except Exception:
        pass
    return {}


def fetch_all_tasks(token: str) -> List[Dict[str, Any]]:
    """Fetches all active tasks from Todoist."""
    headers = _get_headers(token)
    resp = requests.get(f"{TODOIST_API_BASE}/tasks", headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch Todoist tasks ({resp.status_code}): {resp.text}")

    projects_map = fetch_projects_map(token)
    raw_tasks = resp.json()
    all_tasks: List[Dict[str, Any]] = []

    for t in raw_tasks:
        due = None
        due_obj = t.get("due")
        if due_obj:
            raw_dt = due_obj.get("datetime") or due_obj.get("date")
            if raw_dt:
                try:
                    if "T" in raw_dt:
                        due = datetime.datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                    else:
                        due = datetime.datetime.fromisoformat(raw_dt).replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    due = None

        # Priority in Todoist API: 1=Normal, 2=Medium, 3=High, 4=Urgent (higher = more urgent)
        priority = t.get("priority", 1)

        project_name = projects_map.get(t.get("project_id"), "Todoist")
        labels = t.get("labels", [])

        all_tasks.append({
            "id": t.get("id"),
            "title": t.get("content", ""),
            "notes": t.get("description") or None,
            "due": due,
            "list": project_name,
            "source": "Todoist",
            "priority": priority,
            "labels": labels,
            "url": t.get("url"),
        })

    return all_tasks


def convert_to_task(
    td_task: Dict[str, Any],
    task_id: Optional[int] = None,
    include_tags: Optional[bool] = None,
) -> Optional[Any]:
    """Converts a raw Todoist task dictionary to the project's Task model."""
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

    title = td_task.get("title", "")
    notes = td_task.get("notes")
    task.description = f"{title}\n{notes}".strip() if notes else title
    task.deadline = td_task.get("due")
    task.time = None
    task.priority = td_task.get("priority", 1)
    task.tags = []

    if include_tags and Tag is not None:
        project_name = td_task.get("list")
        if project_name:
            try:
                t_proj = Tag(project_name)
                t_proj.title = project_name
                t_proj.color = (228, 66, 64)  # Todoist red
                task.tags.append(t_proj)
            except Exception:
                pass

        for lbl in td_task.get("labels", []):
            try:
                t_lbl = Tag(lbl)
                t_lbl.title = lbl
                t_lbl.color = (100, 100, 100)
                task.tags.append(t_lbl)
            except Exception:
                pass

    task.llm_metadata = ""
    return task


def download_tasks(
    api_token: Optional[str] = None,
    credentials_path: Optional[str] = None,
    as_objects: bool = True,
    include_tags: Optional[bool] = None,
) -> List[Any]:
    """
    Downloads tasks from Todoist using API token.
    
    :param api_token: Optional API token. If omitted, loaded from credentials file or env.
    :param credentials_path: Optional custom path to credentials file.
    :param as_objects: If True (default), returns Task objects.
    :param include_tags: If True, populates tags; if False, leaves tags empty. Defaults to INCLUDE_TAGS.
    """
    token = api_token if api_token else get_api_token(credentials_path)
    tasks = fetch_all_tasks(token)
    if as_objects:
        return [convert_to_task(t, include_tags=include_tags) for t in tasks]
    return tasks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download Todoist tasks using API Token")
    parser.add_argument("--token", type=str, default=None, help="Todoist API token")
    parser.add_argument("--raw", action="store_true", help="Return raw dictionaries instead of Task objects")
    parser.add_argument("--no-tags", action="store_true", help="Leave task tags empty")
    args = parser.parse_args()

    print("Fetching Todoist tasks...")
    should_include_tags = False if args.no_tags else None
    tasks = download_tasks(
        api_token=args.token,
        as_objects=not args.raw,
        include_tags=should_include_tags,
    )
    print(f"Downloaded {len(tasks)} tasks:")
    for task in tasks:
        print(task)
