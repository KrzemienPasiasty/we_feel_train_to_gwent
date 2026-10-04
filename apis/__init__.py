"""
APIs package: external integrations for task management and environmental data.
"""

from .common import BASE_DIR, PROJECT_ROOT, resolve_file

try:
    from .weatherAPI import (
        interpret_weather_code,
        interpret_european_aqi,
        interpret_us_aqi,
        geocode_location,
        fetch_weather,
        fetch_air_quality,
        download_weather_and_air_quality,
    )
except ImportError:
    pass

try:
    from .clickUpAPI import (
        fetch_clickup_tasks,
        fetch_clickup_folders,
        fetch_clickup_lists,
        fetch_clickup_spaces,
        fetch_clickup_teams,
    )
except ImportError:
    pass

try:
    from .googleAPI import (
        get_creds as get_google_creds,
        fetch_google_tasks,
        fetch_all_google_tasks,
        fetch_google_task_lists,
    )
except ImportError:
    pass

try:
    from .jiraAPI import (
        fetch_jira_issues,
        fetch_jira_projects,
    )
except ImportError:
    pass

try:
    from .MicrosoftAPI import (
        get_client_id as get_microsoft_client_id,
    )
except ImportError:
    pass

try:
    from .mondayAPI import (
        fetch_monday_boards,
        fetch_monday_items,
    )
except ImportError:
    pass

try:
    from .notionAPI import (
        fetch_notion_pages,
        fetch_notion_databases,
    )
except ImportError:
    pass

try:
    from .todoistAPI import (
        fetch_todoist_tasks,
        fetch_todoist_projects,
    )
except ImportError:
    pass

try:
    from .trelloAPI import (
        fetch_trello_boards,
        fetch_trello_cards,
        fetch_trello_lists,
    )
except ImportError:
    pass

__all__ = [
    "BASE_DIR",
    "PROJECT_ROOT",
    "resolve_file",
    "interpret_weather_code",
    "interpret_european_aqi",
    "interpret_us_aqi",
    "geocode_location",
    "fetch_weather",
    "fetch_air_quality",
    "download_weather_and_air_quality",
    "fetch_clickup_tasks",
    "fetch_google_tasks",
    "fetch_jira_issues",
    "fetch_monday_boards",
    "fetch_notion_pages",
    "fetch_todoist_tasks",
    "fetch_trello_boards",
]
