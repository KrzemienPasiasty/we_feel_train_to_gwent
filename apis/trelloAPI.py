import os
import json
import datetime
from typing import List, Dict, Any, Optional, Tuple
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

TRELLO_API_BASE = "https://api.trello.com/1"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIFIED_CREDENTIALS_FILE = os.path.join(BASE_DIR, "api_credentials.json")


def get_credentials(credentials_path: Optional[str] = None) -> Tuple[str, str]:
    """
    Retrieves Trello api_key and token from environment variables or credentials file.
    """
    env_key = os.environ.get("TRELLO_API_KEY")
    env_token = os.environ.get("TRELLO_TOKEN")
    if env_key and env_token:
        return env_key.strip(), env_token.strip()

    cred_file = credentials_path or UNIFIED_CREDENTIALS_FILE
    if os.path.exists(cred_file):
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                t_cfg = cfg.get("trello", {})
                key = t_cfg.get("api_key")
                token = t_cfg.get("token")
                if key and token and key != "YOUR_TRELLO_API_KEY" and token != "YOUR_TRELLO_TOKEN":
                    return key.strip(), token.strip()
        except Exception:
            pass

    raise FileNotFoundError(
        "Trello credentials not configured. Please fill 'api_key' and 'token' in "
        f"'{cred_file}' under the 'trello' section, or set TRELLO_API_KEY and TRELLO_TOKEN."
    )


def fetch_all_tasks(api_key: str, token: str) -> List[Dict[str, Any]]:
    """Fetches all open cards assigned to or visible to the user across Trello boards."""
    params = {
        "key": api_key,
        "token": token,
        "filter": "open",
        "fields": "id,name,desc,due,idList,idBoard,labels,url",
    }
    resp = requests.get(f"{TRELLO_API_BASE}/members/me/cards", params=params)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch Trello cards ({resp.status_code}): {resp.text}")

    cards = resp.json()
    list_cache: Dict[str, str] = {}
    board_cache: Dict[str, str] = {}
    all_tasks: List[Dict[str, Any]] = []

    for card in cards:
        due = None
        raw_due = card.get("due")
        if raw_due:
            try:
                due = datetime.datetime.fromisoformat(raw_due.replace("Z", "+00:00"))
            except Exception:
                due = None

        # Resolve list (column) name
        list_id = card.get("idList")
        list_name = "Trello"
        if list_id:
            if list_id not in list_cache:
                l_resp = requests.get(f"{TRELLO_API_BASE}/lists/{list_id}", params={"key": api_key, "token": token, "fields": "name"})
                if l_resp.status_code == 200:
                    list_cache[list_id] = l_resp.json().get("name", "Trello")
                else:
                    list_cache[list_id] = "Trello"
            list_name = list_cache[list_id]

        # Extract label names
        label_names = [lbl.get("name") for lbl in card.get("labels", []) if lbl.get("name")]

        # Determine priority: if labels mention urgent/high/low, map accordingly, else default to 2
        priority = 2
        labels_lower = [l.lower() for l in label_names]
        if any(w in labels_lower for w in ["urgent", "critical", "blocker"]):
            priority = 4
        elif any(w in labels_lower for w in ["high", "important"]):
            priority = 3
        elif any(w in labels_lower for w in ["low", "minor"]):
            priority = 1

        all_tasks.append({
            "id": card.get("id"),
            "title": card.get("name", ""),
            "notes": card.get("desc") or None,
            "due": due,
            "list": list_name,
            "source": "Trello",
            "priority": priority,
            "labels": label_names,
            "url": card.get("url"),
        })

    return all_tasks


def convert_to_task(
    tr_task: Dict[str, Any],
    task_id: Optional[int] = None,
    include_tags: Optional[bool] = None,
) -> Optional[Any]:
    """Converts a raw Trello card dictionary to the project's Task model."""
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

    title = tr_task.get("title", "")
    notes = tr_task.get("notes")
    task.description = f"{title}\n{notes}".strip() if notes else title
    task.deadline = tr_task.get("due")
    task.time = None
    task.priority = tr_task.get("priority", 2)
    task.tags = []

    if include_tags and Tag is not None:
        list_name = tr_task.get("list")
        if list_name:
            try:
                t_list = Tag(list_name)
                t_list.title = list_name
                t_list.color = (0, 121, 191)  # Trello blue
                task.tags.append(t_list)
            except Exception:
                pass

        for lbl in tr_task.get("labels", []):
            try:
                t_lbl = Tag(lbl)
                t_lbl.title = lbl
                t_lbl.color = (50, 150, 100)
                task.tags.append(t_lbl)
            except Exception:
                pass

    task.llm_metadata = ""
    return task


def download_tasks(
    api_key: Optional[str] = None,
    token: Optional[str] = None,
    credentials_path: Optional[str] = None,
    as_objects: bool = True,
    include_tags: Optional[bool] = None,
) -> List[Any]:
    """
    Downloads cards from Trello using API key and token.
    """
    if not api_key or not token:
        k, t = get_credentials(credentials_path)
        api_key = api_key or k
        token = token or t

    tasks = fetch_all_tasks(api_key, token)
    if as_objects:
        return [convert_to_task(c, include_tags=include_tags) for c in tasks]
    return tasks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download Trello cards using API Key and Token")
    parser.add_argument("--key", type=str, default=None, help="Trello API Key")
    parser.add_argument("--token", type=str, default=None, help="Trello Token")
    parser.add_argument("--raw", action="store_true", help="Return raw dictionaries instead of Task objects")
    parser.add_argument("--no-tags", action="store_true", help="Leave task tags empty")
    args = parser.parse_args()

    print("Fetching Trello cards...")
    should_include_tags = False if args.no_tags else None
    tasks = download_tasks(
        api_key=args.key,
        token=args.token,
        as_objects=not args.raw,
        include_tags=should_include_tags,
    )
    print(f"Downloaded {len(tasks)} tasks:")
    for task in tasks:
        print(task)
