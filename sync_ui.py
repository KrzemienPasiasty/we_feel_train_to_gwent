import customtkinter as ctk
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from apis import clickUpAPI, MicrosoftAPI
import datas
from tag import Tag


BASE_DIR = Path(__file__).resolve().parent
TASKS_FILE = BASE_DIR / "tasks_active.json"
ARCHIVED_TASKS_FILE = BASE_DIR / "tasks_archived.json"
TAGS_FILE = BASE_DIR / "tags.json"
SETTINGS_FILE = BASE_DIR / ".sync_settings.json"


def _read_json_list(filepath):
    if not filepath.exists():
        return []
    with filepath.open("r", encoding="utf-8") as file:
        records = json.load(file)
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise ValueError(f"Expected a JSON list of objects in {filepath}")
    return records


def _validate_google_credentials(credentials):
    installed = credentials.get("installed") if isinstance(credentials, dict) else None
    if not isinstance(installed, dict) or not installed.get("client_id"):
        raise ValueError(
            "Wybierz plik OAuth JSON klienta Desktop app. Plik typu Web application nie obsługuje tego logowania."
        )


def merge_downloaded_tasks(downloaded_tasks, tasks_path=TASKS_FILE, tags_path=TAGS_FILE):
    task_records = _read_json_list(Path(tasks_path))
    archived_records = _read_json_list(ARCHIVED_TASKS_FILE)
    tag_records = _read_json_list(Path(tags_path))

    tags_by_title = {}
    tag_objects = {}
    for record in tag_records:
        title = str(record.get("title", "")).strip()
        if not title:
            continue
        key = title.casefold()
        tags_by_title[key] = record
        tag_objects[key] = Tag(
            record.get("id", 0),
            title,
            tuple(record.get("color", (100, 100, 100))),
            record.get("is_interactive", False),
        )

    max_task_id = max(
        (int(record.get("id", 0)) for record in task_records + archived_records),
        default=0,
    )
    max_tag_id = max((int(record.get("id", 0)) for record in tag_records), default=0)
    existing_imports = {
        (str(record.get("source")), str(record.get("external_id")))
        for record in task_records + archived_records
        if record.get("source") and record.get("external_id")
    }

    added_tasks = []
    new_tag_count = 0
    duplicate_count = 0

    for task in downloaded_tasks:
        source = getattr(task, "source", None) or "import"
        external_id = getattr(task, "external_id", None)
        import_key = (str(source), str(external_id)) if external_id else None
        if import_key and import_key in existing_imports:
            duplicate_count += 1
            continue

        task.id = max_task_id + 1
        max_task_id = task.id
        task_tag_records = []
        canonical_task_tags = []
        for source_tag in getattr(task, "tags", []):
            title = str(getattr(source_tag, "title", "")).strip()
            if not title:
                continue
            key = title.casefold()
            if key not in tags_by_title:
                max_tag_id += 1
                color = tuple(getattr(source_tag, "color", (31, 83, 141)))
                record = {
                    "id": max_tag_id,
                    "title": title,
                    "color": color,
                    "is_interactive": False,
                }
                tags_by_title[key] = record
                tag_objects[key] = Tag(max_tag_id, title, color, False)
                new_tag_count += 1
            canonical_tag = tag_objects[key]
            canonical_task_tags.append(canonical_tag)
            task_tag_records.append({"id": canonical_tag.id, "name": canonical_tag.title})

        task.tags = canonical_task_tags
        added_tasks.append(task)
        task_records.append({
            "id": task.id,
            "description": getattr(task, "description", ""),
            "start": _json_value(getattr(task, "start", None)),
            "deadline": _json_value(getattr(task, "deadline", None)),
            "time": _json_value(getattr(task, "time", None)),
            "focus": getattr(task, "focus", 0),
            "priority": getattr(task, "priority", 1),
            "tags": task_tag_records,
            "llm_metadata": getattr(task, "llm_metadata", ""),
            "source": source,
            "external_id": str(external_id) if external_id else None,
            "status": "not_started",
        })
        if import_key:
            existing_imports.add(import_key)

    if added_tasks:
        with Path(tasks_path).open("w", encoding="utf-8") as file:
            json.dump(task_records, file, ensure_ascii=False, indent=4)
    if new_tag_count:
        with Path(tags_path).open("w", encoding="utf-8") as file:
            json.dump(list(tags_by_title.values()), file, ensure_ascii=False, indent=4)

    datas.tags_list[:] = list(tag_objects.values())
    datas.current_tasks_list.extend(added_tasks)
    return added_tasks, new_tag_count, duplicate_count


def _json_value(value):
    return value.isoformat() if isinstance(value, datetime) else value


class SyncFrame(ctk.CTkFrame):
    """Connect task services and import their tasks into FutureFlow."""
    def __init__(self, master, on_data_changed=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_data_changed = on_data_changed
        ctk.CTkLabel(self, text="Task integrations", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=24, pady=(20, 8))
        ctk.CTkLabel(self, text="Connect external task services and import your tasks.", text_color="gray").pack(anchor="w", padx=24, pady=(0, 14))

        self.clickup_token = ctk.CTkEntry(self, placeholder_text="ClickUp personal API token", show="?")
        self.clickup_token.pack(fill="x", padx=24, pady=6)
        self.microsoft_client_id = ctk.CTkEntry(self, placeholder_text="Microsoft app client ID")
        self.microsoft_client_id.pack(fill="x", padx=24, pady=6)
        self.save_button = ctk.CTkButton(self, text="Save connections", command=self._save_credentials)
        self.save_button.pack(anchor="e", padx=24, pady=8)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=8)
        self.clickup_btn = ctk.CTkButton(buttons, text="Connect ClickUp and import", command=lambda: self._start_import("clickup"))
        self.clickup_btn.pack(fill="x", pady=5)
        self.ms_btn = ctk.CTkButton(buttons, text="Connect Microsoft To Do and import", command=lambda: self._start_import("microsoft"))
        self.ms_btn.pack(fill="x", pady=5)
        self.status_label = ctk.CTkLabel(self, text="", text_color="gray", wraplength=900)
        self.status_label.pack(fill="x", padx=24, pady=10)
        self.imported_tasks_box = ctk.CTkTextbox(self, height=180)
        self.imported_tasks_box.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        self.imported_tasks_box.insert("1.0", "Imported tasks will appear here.")
        self.imported_tasks_box.configure(state="disabled")
        self._load_credentials()

    def _load_credentials(self):
        try:
            with Path(clickUpAPI.UNIFIED_CREDENTIALS_FILE).open("r", encoding="utf-8") as f:
                credentials = json.load(f)
            clickup = credentials.get("clickup", {}).get("api_token", "")
            microsoft = credentials.get("microsoft", {}).get("client_id", "")
            if clickup and clickup != "YOUR_CLICKUP_PERSONAL_API_TOKEN":
                self.clickup_token.insert(0, clickup)
            if microsoft and microsoft != "YOUR_MICROSOFT_CLIENT_ID":
                self.microsoft_client_id.insert(0, microsoft)
        except (OSError, json.JSONDecodeError, AttributeError):
            pass

    def _save_credentials(self):
        try:
            path = Path(clickUpAPI.UNIFIED_CREDENTIALS_FILE)
            credentials = {}
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    credentials = json.load(f)
            credentials.setdefault("clickup", {})["api_token"] = self.clickup_token.get().strip()
            credentials.setdefault("microsoft", {})["client_id"] = self.microsoft_client_id.get().strip()
            with path.open("w", encoding="utf-8") as f:
                json.dump(credentials, f, ensure_ascii=False, indent=2)
            self.status_label.configure(text="Service connections saved.", text_color="green")
            return True
        except (OSError, json.JSONDecodeError, TypeError) as error:
            self.status_label.configure(text=f"Could not save connections: {error}", text_color="red")
            return False

    def _start_import(self, source):
        if not self._save_credentials():
            return
        self.clickup_btn.configure(state="disabled")
        self.ms_btn.configure(state="disabled")
        self.status_label.configure(text="Authorizing and importing in the background?", text_color="yellow")
        threading.Thread(target=self._worker, args=(source,), daemon=True).start()

    def _worker(self, source):
        try:
            if source == "clickup":
                tasks = clickUpAPI.download_tasks(as_objects=True)
            else:
                raise NotImplementedError("Microsoft To Do task import is not implemented yet.")
            self.after(0, self._process_and_save, tasks)
        except Exception as error:
            self.after(0, self._show_error, str(error))

    def _process_and_save(self, downloaded_tasks):
        try:
            added, tag_count, duplicates = merge_downloaded_tasks(downloaded_tasks)
            titles = [str(getattr(task, "description", "")).splitlines()[0].strip() or f"Task {task.id}" for task in added]
            self.imported_tasks_box.configure(state="normal")
            self.imported_tasks_box.delete("1.0", "end")
            self.imported_tasks_box.insert("1.0", "\n".join(f"[{task.id}] {title}" for task, title in zip(added, titles)) or "No new tasks.")
            self.imported_tasks_box.configure(state="disabled")
            self.status_label.configure(text=f"Imported {len(added)} tasks and {tag_count} tags; skipped {duplicates} duplicates.", text_color="green")
            if self.on_data_changed:
                self.on_data_changed()
        except Exception as error:
            self._show_error(str(error))
            return
        self._set_buttons_enabled(True)

    def _set_buttons_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.clickup_btn.configure(state=state)
        self.ms_btn.configure(state=state)

    def _show_error(self, message):
        self.status_label.configure(text=f"Integration error: {message}", text_color="red")
        self._set_buttons_enabled(True)
