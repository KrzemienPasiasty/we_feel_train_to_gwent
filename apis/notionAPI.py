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

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIFIED_CREDENTIALS_FILE = os.path.join(BASE_DIR, "api_credentials.json")


def get_credentials(credentials_path: Optional[str] = None) -> tuple[str, Optional[str]]:
    """
    Retrieves Notion integration token and optional database_id from environment or credentials file.
    """
    env_token = os.environ.get("NOTION_API_TOKEN")
    env_db = os.environ.get("NOTION_DATABASE_ID")
    if env_token:
        return env_token.strip(), (env_db.strip() if env_db else None)

    cred_file = credentials_path or UNIFIED_CREDENTIALS_FILE
    if os.path.exists(cred_file):
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                n_cfg = cfg.get("notion", {})
                token = n_cfg.get("api_token")
                db_id = n_cfg.get("database_id")
                if token and token != "YOUR_NOTION_INTEGRATION_TOKEN":
                    return token.strip(), (db_id.strip() if db_id else None)
        except Exception:
            pass

    raise FileNotFoundError(
        "Notion credentials not configured. Please fill 'api_token' in "
        f"'{cred_file}' under the 'notion' section, or set NOTION_API_TOKEN."
    )


def _get_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _clean_rich_text(rich_text_list: List[Dict[str, Any]]) -> str:
    """Helper to concatenate rich text elements into plain text."""
    return "".join(t.get("plain_text", "") for t in rich_text_list).strip()


def _parse_page_task(page: Dict[str, Any], default_list: str = "Notion") -> Optional[Dict[str, Any]]:
    """Parses a Notion page dictionary into standard task dictionary."""
    props = page.get("properties", {})
    title = ""
    due = None
    priority = 2
    tags = []
    notes = None

    for prop_name, prop_data in props.items():
        p_type = prop_data.get("type")

        # 1. Extract title
        if p_type == "title":
            title = _clean_rich_text(prop_data.get("title", []))

        # 2. Extract date / due date
        elif p_type == "date":
            date_obj = prop_data.get("date")
            if date_obj and date_obj.get("start"):
                try:
                    start_str = date_obj["start"]
                    if "T" in start_str:
                        due = datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    else:
                        due = datetime.datetime.fromisoformat(start_str).replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    due = None

        # 3. Extract priority
        elif p_type == "select" and "priority" in prop_name.lower():
            sel = prop_data.get("select")
            if sel and sel.get("name"):
                name_lower = sel["name"].lower()
                if any(w in name_lower for w in ["urgent", "critical"]):
                    priority = 4
                elif any(w in name_lower for w in ["high", "important"]):
                    priority = 3
                elif any(w in name_lower for w in ["medium", "normal"]):
                    priority = 2
                else:
                    priority = 1

        # 4. Extract tags / multi-select
        elif p_type == "multi_select":
            for item in prop_data.get("multi_select", []):
                if item.get("name"):
                    tags.append(item["name"])

        # 5. Extract status (skip completed if status is done)
        elif p_type == "status":
            stat = prop_data.get("status")
            if stat and stat.get("name", "").lower() in ["done", "completed", "closed"]:
                return None  # Skip completed tasks

        # 6. Extract notes / rich text description
        elif p_type == "rich_text" and ("desc" in prop_name.lower() or "notes" in prop_name.lower()):
            notes = _clean_rich_text(prop_data.get("rich_text", []))

    if not title:
        return None

    return {
        "id": page.get("id"),
        "title": title,
        "notes": notes,
        "due": due,
        "list": default_list,
        "source": "Notion",
        "priority": priority,
        "labels": tags,
        "url": page.get("url"),
    }


def fetch_all_tasks(token: str, database_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches tasks from specified database or searches all shared task databases/pages."""
    headers = _get_headers(token)
    all_tasks: List[Dict[str, Any]] = []

    # If database_id is specified, query it directly
    if database_id:
        url = f"{NOTION_API_BASE}/databases/{database_id}/query"
        has_more = True
        start_cursor = None
        while has_more:
            payload = {}
            if start_cursor:
                payload["start_cursor"] = start_cursor
            resp = requests.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to query Notion database ({resp.status_code}): {resp.text}")
            data_json = resp.json()
            for page in data_json.get("results", []):
                t = _parse_page_task(page)
                if t:
                    all_tasks.append(t)
            has_more = data_json.get("has_more", False)
            start_cursor = data_json.get("next_cursor")
        return all_tasks

    # If no database_id, search for databases shared with integration
    search_url = f"{NOTION_API_BASE}/search"
    search_resp = requests.post(search_url, headers=headers, json={"filter": {"value": "database", "property": "object"}})
    if search_resp.status_code == 200:
        dbs = search_resp.json().get("results", [])
        for db in dbs:
            db_id = db["id"]
            db_title_arr = db.get("title", [])
            db_name = _clean_rich_text(db_title_arr) or "Notion"
            
            q_resp = requests.post(f"{NOTION_API_BASE}/databases/{db_id}/query", headers=headers, json={})
            if q_resp.status_code == 200:
                for page in q_resp.json().get("results", []):
                    t = _parse_page_task(page, default_list=db_name)
                    if t:
                        all_tasks.append(t)

    # If still no databases found, search pages directly
    if not all_tasks:
        page_search = requests.post(search_url, headers=headers, json={"filter": {"value": "page", "property": "object"}})
        if page_search.status_code == 200:
            for page in page_search.json().get("results", []):
                t = _parse_page_task(page)
                if t:
                    all_tasks.append(t)

    return all_tasks


def convert_to_task(
    notion_task: Dict[str, Any],
    task_id: Optional[int] = None,
    include_tags: Optional[bool] = None,
) -> Optional[Any]:
    """Converts a raw Notion task dictionary to the project's Task model."""
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

    title = notion_task.get("title", "")
    notes = notion_task.get("notes")
    task.description = f"{title}\n{notes}".strip() if notes else title
    task.deadline = notion_task.get("due")
    task.time = None
    task.priority = notion_task.get("priority", 2)
    task.tags = []

    if include_tags and Tag is not None:
        db_name = notion_task.get("list")
        if db_name:
            try:
                t_db = Tag(db_name)
                t_db.title = db_name
                t_db.color = (0, 0, 0)  # Notion black
                task.tags.append(t_db)
            except Exception:
                pass

        for lbl in notion_task.get("labels", []):
            try:
                t_lbl = Tag(lbl)
                t_lbl.title = lbl
                t_lbl.color = (120, 120, 120)
                task.tags.append(t_lbl)
            except Exception:
                pass

    task.llm_metadata = ""
    return task


def download_tasks(
    api_token: Optional[str] = None,
    database_id: Optional[str] = None,
    credentials_path: Optional[str] = None,
    as_objects: bool = True,
    include_tags: Optional[bool] = None,
) -> List[Any]:
    """
    Downloads tasks from Notion using API token.
    """
    if not api_token:
        tok, db = get_credentials(credentials_path)
        api_token = tok
        database_id = database_id or db

    tasks = fetch_all_tasks(api_token, database_id=database_id)
    if as_objects:
        return [convert_to_task(t, include_tags=include_tags) for t in tasks]
    return tasks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download Notion tasks using API Token")
    parser.add_argument("--token", type=str, default=None, help="Notion Integration Secret / API Token")
    parser.add_argument("--database", type=str, default=None, help="Notion Database ID (optional)")
    parser.add_argument("--raw", action="store_true", help="Return raw dictionaries instead of Task objects")
    parser.add_argument("--no-tags", action="store_true", help="Leave task tags empty")
    args = parser.parse_args()

    print("Fetching Notion tasks...")
    should_include_tags = False if args.no_tags else None
    tasks = download_tasks(
        api_token=args.token,
        database_id=args.database,
        as_objects=not args.raw,
        include_tags=should_include_tags,
    )
    print(f"Downloaded {len(tasks)} tasks:")
    for task in tasks:
        print(task)
