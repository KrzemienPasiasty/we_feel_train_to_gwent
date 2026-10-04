import os
import json
import datetime
from typing import List, Dict, Any, Optional, Tuple
import requests
from requests.auth import HTTPBasicAuth

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIFIED_CREDENTIALS_FILE = os.path.join(BASE_DIR, "api_credentials.json")


def get_credentials(credentials_path: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Retrieves Jira domain, email, and api_token from environment variables or credentials file.
    """
    env_domain = os.environ.get("JIRA_DOMAIN")
    env_email = os.environ.get("JIRA_EMAIL")
    env_token = os.environ.get("JIRA_API_TOKEN")
    if env_domain and env_email and env_token:
        return env_domain.strip(), env_email.strip(), env_token.strip()

    cred_file = credentials_path or UNIFIED_CREDENTIALS_FILE
    if os.path.exists(cred_file):
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                j_cfg = cfg.get("jira", {})
                domain = j_cfg.get("domain")
                email = j_cfg.get("email")
                token = j_cfg.get("api_token")
                if (
                    domain
                    and email
                    and token
                    and token != "YOUR_JIRA_API_TOKEN"
                    and not domain.startswith("your-domain")
                ):
                    return domain.strip(), email.strip(), token.strip()
        except Exception:
            pass

    raise FileNotFoundError(
        "Jira credentials not configured. Please fill 'domain', 'email', and 'api_token' in "
        f"'{cred_file}' under the 'jira' section, or set JIRA_DOMAIN, JIRA_EMAIL, and JIRA_API_TOKEN."
    )


def _format_domain(domain: str) -> str:
    domain = domain.strip().replace("https://", "").replace("http://", "").rstrip("/")
    if "." not in domain:
        domain = f"{domain}.atlassian.net"
    return domain


def _extract_adf_text(node: Any) -> str:
    """Recursively extracts plain text from Atlassian Document Format (ADF) json."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    content = node.get("content", [])
    parts = [_extract_adf_text(c) for c in content]
    return " ".join(p for p in parts if p).strip()


def fetch_all_tasks(domain: str, email: str, token: str) -> List[Dict[str, Any]]:
    """Fetches unresolved Jira issues assigned to the current user."""
    domain = _format_domain(domain)
    auth = HTTPBasicAuth(email, token)
    headers = {"Accept": "application/json"}

    url = f"https://{domain}/rest/api/3/search"
    jql = "assignee = currentUser() AND resolution = Unresolved order by updated DESC"
    params = {
        "jql": jql,
        "maxResults": 100,
        "fields": "summary,description,duedate,priority,labels,status,project",
    }

    resp = requests.get(url, headers=headers, auth=auth, params=params)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch Jira issues ({resp.status_code}): {resp.text}")

    data_json = resp.json()
    issues = data_json.get("issues", [])
    all_tasks: List[Dict[str, Any]] = []

    for issue in issues:
        fields = issue.get("fields", {})

        # Parse due date
        due = None
        raw_due = fields.get("duedate")
        if raw_due:
            try:
                due = datetime.datetime.fromisoformat(raw_due).replace(tzinfo=datetime.timezone.utc)
            except Exception:
                due = None

        # Parse description
        desc_node = fields.get("description")
        notes = _extract_adf_text(desc_node) if desc_node else None

        # Map priority: higher number = more urgent
        p_name = (fields.get("priority") or {}).get("name", "Medium").lower()
        if any(w in p_name for w in ["highest", "blocker"]):
            priority = 4
        elif any(w in p_name for w in ["high", "critical"]):
            priority = 3
        elif any(w in p_name for w in ["medium", "major", "normal"]):
            priority = 2
        else:
            priority = 1

        project_name = (fields.get("project") or {}).get("name", "Jira")
        status_name = (fields.get("status") or {}).get("name", "")
        labels = fields.get("labels", [])

        all_tasks.append({
            "id": issue.get("key") or issue.get("id"),
            "title": fields.get("summary", ""),
            "notes": notes if notes else None,
            "due": due,
            "list": project_name,
            "status": status_name,
            "source": "Jira",
            "priority": priority,
            "labels": labels,
            "url": f"https://{domain}/browse/{issue.get('key')}",
        })

    return all_tasks


def convert_to_task(
    jira_task: Dict[str, Any],
    task_id: Optional[int] = None,
    include_tags: Optional[bool] = None,
) -> Optional[Any]:
    """Converts a raw Jira issue dictionary to the project's Task model."""
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

    title = jira_task.get("title", "")
    notes = jira_task.get("notes")
    task.description = f"{title}\n{notes}".strip() if notes else title
    task.deadline = jira_task.get("due")
    task.time = None
    task.priority = jira_task.get("priority", 2)
    task.tags = []

    if include_tags and Tag is not None:
        project_name = jira_task.get("list")
        if project_name:
            try:
                t_proj = Tag(project_name)
                t_proj.title = project_name
                t_proj.color = (0, 82, 204)  # Jira blue
                task.tags.append(t_proj)
            except Exception:
                pass

        status_name = jira_task.get("status")
        if status_name:
            try:
                t_status = Tag(status_name)
                t_status.title = status_name
                t_status.color = (255, 171, 0)  # Jira status yellow/orange
                task.tags.append(t_status)
            except Exception:
                pass

        for lbl in jira_task.get("labels", []):
            try:
                t_lbl = Tag(lbl)
                t_lbl.title = lbl
                t_lbl.color = (60, 60, 60)
                task.tags.append(t_lbl)
            except Exception:
                pass

    task.llm_metadata = ""
    return task


def download_tasks(
    domain: Optional[str] = None,
    email: Optional[str] = None,
    api_token: Optional[str] = None,
    credentials_path: Optional[str] = None,
    as_objects: bool = True,
    include_tags: Optional[bool] = None,
) -> List[Any]:
    """
    Downloads assigned Jira issues using email and API token.
    """
    if not domain or not email or not api_token:
        d, e, t = get_credentials(credentials_path)
        domain = domain or d
        email = email or e
        api_token = api_token or t

    tasks = fetch_all_tasks(domain, email, api_token)
    if as_objects:
        return [convert_to_task(i, include_tags=include_tags) for i in tasks]
    return tasks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download Jira assigned issues using API Token")
    parser.add_argument("--domain", type=str, default=None, help="Jira domain (e.g. company.atlassian.net)")
    parser.add_argument("--email", type=str, default=None, help="Jira account email")
    parser.add_argument("--token", type=str, default=None, help="Jira API token")
    parser.add_argument("--raw", action="store_true", help="Return raw dictionaries instead of Task objects")
    parser.add_argument("--no-tags", action="store_true", help="Leave task tags empty")
    args = parser.parse_args()

    print("Fetching Jira issues...")
    should_include_tags = False if args.no_tags else None
    tasks = download_tasks(
        domain=args.domain,
        email=args.email,
        api_token=args.token,
        as_objects=not args.raw,
        include_tags=should_include_tags,
    )
    print(f"Downloaded {len(tasks)} tasks:")
    for task in tasks:
        print(task)
