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

MONDAY_API_BASE = "https://api.monday.com/v2"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIFIED_CREDENTIALS_FILE = os.path.join(BASE_DIR, "api_credentials.json")


def get_api_token(credentials_path: Optional[str] = None) -> str:
    """
    Retrieves Monday.com personal API token from environment variable or credentials file.
    """
    env_token = os.environ.get("MONDAY_API_TOKEN")
    if env_token:
        return env_token.strip()

    cred_file = credentials_path or UNIFIED_CREDENTIALS_FILE
    if os.path.exists(cred_file):
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                m_cfg = cfg.get("monday", {})
                token = m_cfg.get("api_token")
                if token and token != "YOUR_MONDAY_API_TOKEN":
                    return token.strip()
        except Exception:
            pass

    raise FileNotFoundError(
        "Monday.com API token is not configured. Please fill 'api_token' in "
        f"'{cred_file}' under the 'monday' section, or set MONDAY_API_TOKEN."
    )


def fetch_all_tasks(token: str) -> List[Dict[str, Any]]:
    """Fetches items across all accessible Monday.com boards."""
    headers = {
        "Authorization": token,
        "API-Version": "2024-04",
        "Content-Type": "application/json",
    }
    query = """
    query {
        boards(limit: 50) {
            id
            name
            items_page(limit: 100) {
                items {
                    id
                    name
                    column_values {
                        id
                        text
                        type
                        value
                    }
                }
            }
        }
    }
    """
    resp = requests.post(MONDAY_API_BASE, json={"query": query}, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch Monday items ({resp.status_code}): {resp.text}")

    resp_json = resp.json()
    if "errors" in resp_json:
        raise RuntimeError(f"Monday API error: {resp_json['errors']}")

    boards = resp_json.get("data", {}).get("boards", [])
    all_tasks: List[Dict[str, Any]] = []

    for b in boards:
        board_name = b.get("name", "Monday")
        items = b.get("items_page", {}).get("items", [])

        for item in items:
            title = item.get("name", "")
            notes = None
            due = None
            priority = 2
            item_tags = []

            for col in item.get("column_values", []):
                c_id = col.get("id", "").lower()
                c_type = col.get("type", "").lower()
                c_text = col.get("text") or ""
                c_val = col.get("value")

                # Parse date column
                if "date" in c_type or "date" in c_id or "due" in c_id:
                    if c_val:
                        try:
                            val_dict = json.loads(c_val)
                            date_str = val_dict.get("date")
                            time_str = val_dict.get("time")
                            if date_str:
                                if time_str:
                                    due = datetime.datetime.fromisoformat(f"{date_str}T{time_str}").replace(tzinfo=datetime.timezone.utc)
                                else:
                                    due = datetime.datetime.fromisoformat(date_str).replace(tzinfo=datetime.timezone.utc)
                        except Exception:
                            pass
                    elif c_text:
                        try:
                            due = datetime.datetime.fromisoformat(c_text).replace(tzinfo=datetime.timezone.utc)
                        except Exception:
                            pass

                # Parse notes / description column
                if "notes" in c_id or "desc" in c_id or "text" in c_type or "long_text" in c_type:
                    if c_text and not notes:
                        notes = c_text

                # Parse priority
                if "priority" in c_id or "urgency" in c_id:
                    p_lower = c_text.lower()
                    if any(w in p_lower for w in ["critical", "urgent", "extreme"]):
                        priority = 4
                    elif any(w in p_lower for w in ["high", "important"]):
                        priority = 3
                    elif any(w in p_lower for w in ["medium", "normal", "moderate"]):
                        priority = 2
                    elif any(w in p_lower for w in ["low", "minor"]):
                        priority = 1

                # Parse tag column
                if "tag" in c_type and c_text:
                    item_tags.extend([t.strip() for t in c_text.split(",") if t.strip()])

            all_tasks.append({
                "id": item.get("id"),
                "title": title,
                "notes": notes,
                "due": due,
                "list": board_name,
                "source": "Monday",
                "priority": priority,
                "labels": item_tags,
            })

    return all_tasks


def convert_to_task(
    m_task: Dict[str, Any],
    task_id: Optional[int] = None,
    include_tags: Optional[bool] = None,
) -> Optional[Any]:
    """Converts a raw Monday.com item dictionary to the project's Task model."""
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

    title = m_task.get("title", "")
    notes = m_task.get("notes")
    task.description = f"{title}\n{notes}".strip() if notes else title
    task.deadline = m_task.get("due")
    task.time = None
    task.priority = m_task.get("priority", 2)
    task.tags = []

    if include_tags and Tag is not None:
        board_name = m_task.get("list")
        if board_name:
            try:
                t_board = Tag(board_name)
                t_board.title = board_name
                t_board.color = (255, 61, 100)  # Monday coral
                task.tags.append(t_board)
            except Exception:
                pass

        for lbl in m_task.get("labels", []):
            try:
                t_lbl = Tag(lbl)
                t_lbl.title = lbl
                t_lbl.color = (80, 80, 80)
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
    Downloads items from Monday.com using API token.
    """
    token = api_token if api_token else get_api_token(credentials_path)
    tasks = fetch_all_tasks(token)
    if as_objects:
        return [convert_to_task(t, include_tags=include_tags) for t in tasks]
    return tasks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download Monday.com items using API Token")
    parser.add_argument("--token", type=str, default=None, help="Monday.com personal API token")
    parser.add_argument("--raw", action="store_true", help="Return raw dictionaries instead of Task objects")
    parser.add_argument("--no-tags", action="store_true", help="Leave task tags empty")
    args = parser.parse_args()

    print("Fetching Monday.com items...")
    should_include_tags = False if args.no_tags else None
    tasks = download_tasks(
        api_token=args.token,
        as_objects=not args.raw,
        include_tags=should_include_tags,
    )
    print(f"Downloaded {len(tasks)} tasks:")
    for task in tasks:
        print(task)
