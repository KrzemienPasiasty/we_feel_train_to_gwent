from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
import datetime

SCOPES = ["https://www.googleapis.com/auth/tasks.readonly"]

def get_creds():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return creds

def fetch_all_tasks(service):
    result = []
    lists = service.tasklists().list(maxResults=100).execute().get("items", [])
    for tl in lists:
        page_token = None
        while True:
            resp = service.tasks().list(
                tasklist=tl["id"],
                showCompleted=False,     # only open tasks
                showHidden=False,
                maxResults=100,
                pageToken=page_token,
            ).execute()
            for t in resp.get("items", []):
                result.append({
                    "id": t["id"],
                    "title": t.get("title", ""),
                    "notes": t.get("notes"),
                    "due": datetime.datetime.fromisoformat(t["due"].replace("Z", "+00:00")) if t.get("due") else None,
                    #"status": t["status"],        # needsAction / completed
                    "list": tl["title"],
                    "parent": t.get("parent"),    # subtasks
                    "updated": t["updated"],
                })
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    return result

service = build("tasks", "v1", credentials=get_creds())
for task in fetch_all_tasks(service):
    print(task)
