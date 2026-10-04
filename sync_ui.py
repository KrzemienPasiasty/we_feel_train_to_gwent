import customtkinter as ctk
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import googleAPI
import MicrosoftAPI
import datas
from tag import Tag


BASE_DIR = Path(__file__).resolve().parent
TASKS_FILE = BASE_DIR / "tasks_active.json"
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

    max_task_id = max((int(record.get("id", 0)) for record in task_records), default=0)
    max_tag_id = max((int(record.get("id", 0)) for record in tag_records), default=0)
    existing_imports = {
        (str(record.get("source")), str(record.get("external_id")))
        for record in task_records
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
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.title_label = ctk.CTkLabel(self, text="Integracje i Import", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=(10, 12))

        settings_frame = ctk.CTkFrame(self)
        settings_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(settings_frame, text="Google OAuth credentials.json (Desktop app)").pack(anchor="w", padx=12, pady=(10, 2))
        google_row = ctk.CTkFrame(settings_frame, fg_color="transparent")
        google_row.pack(fill="x", padx=12, pady=(0, 8))
        self.google_credentials_entry = ctk.CTkEntry(
            google_row,
            placeholder_text="Wklej ścieżkę do pliku credentials.json lub wybierz plik",
        )
        self.google_credentials_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(google_row, text="Przeglądaj...", width=110, command=self._browse_google_credentials).pack(side="right")

        ctk.CTkLabel(settings_frame, text="Microsoft Application (client) ID").pack(anchor="w", padx=12, pady=(2, 2))
        self.microsoft_client_id_entry = ctk.CTkEntry(
            settings_frame,
            placeholder_text="Wklej client ID z Azure App registrations",
        )
        self.microsoft_client_id_entry.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkButton(settings_frame, text="Zapisz ustawienia API", command=self._save_api_settings).pack(
            anchor="e", padx=12, pady=(0, 10)
        )

        self.google_btn = ctk.CTkButton(self, text="Pobierz z Google Tasks", command=lambda: self._start_import("google"))
        self.google_btn.pack(pady=8, fill="x", padx=40)

        self.ms_btn = ctk.CTkButton(self, text="Pobierz z Microsoft", command=lambda: self._start_import("microsoft"))
        self.ms_btn.pack(pady=8, fill="x", padx=40)

        self.status_label = ctk.CTkLabel(self, text="", text_color="gray", wraplength=1000, justify="left")
        self.status_label.pack(pady=12, padx=12, fill="x")

        self.imported_tasks_label = ctk.CTkLabel(self, text="Ostatnio dodane zadania")
        self.imported_tasks_label.pack(anchor="w", padx=40, pady=(0, 4))
        self.imported_tasks_box = ctk.CTkTextbox(self, height=90, wrap="word")
        self.imported_tasks_box.pack(fill="both", expand=True, padx=40, pady=(0, 10))
        self.imported_tasks_box.configure(state="disabled")
        self._load_api_settings()

    def _load_api_settings(self):
        try:
            settings = {}
            if SETTINGS_FILE.exists():
                with SETTINGS_FILE.open("r", encoding="utf-8") as file:
                    settings = json.load(file)

            default_google_path = str(googleAPI.CREDENTIALS_FILE) if Path(googleAPI.CREDENTIALS_FILE).is_file() else ""
            google_path = settings.get("google_credentials_path", default_google_path)
            if google_path:
                self.google_credentials_entry.insert(0, google_path)
                googleAPI.CREDENTIALS_FILE = str(Path(google_path).expanduser())

            microsoft_id = os.environ.get("MICROSOFT_CLIENT_ID", "").strip()
            if not microsoft_id and Path(MicrosoftAPI.CREDENTIALS_FILE).exists():
                with Path(MicrosoftAPI.CREDENTIALS_FILE).open("r", encoding="utf-8") as file:
                    microsoft_id = json.load(file).get("client_id", "")
            if microsoft_id and microsoft_id != "YOUR_MICROSOFT_CLIENT_ID":
                self.microsoft_client_id_entry.insert(0, microsoft_id)
        except (OSError, json.JSONDecodeError, AttributeError, TypeError) as error:
            self.status_label.configure(text=f"Nie można wczytać ustawień API: {error}", text_color="red")

    def _browse_google_credentials(self):
        selected_path = filedialog.askopenfilename(
            title="Wybierz Google OAuth credentials.json",
            initialdir=str(BASE_DIR),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if selected_path:
            self.google_credentials_entry.delete(0, "end")
            self.google_credentials_entry.insert(0, selected_path)

    def _save_api_settings(self, show_success=True, for_source=None):
        try:
            settings = {}
            if SETTINGS_FILE.exists():
                with SETTINGS_FILE.open("r", encoding="utf-8") as file:
                    settings = json.load(file)

            google_path = self.google_credentials_entry.get().strip()
            if google_path and for_source in (None, "google"):
                credentials_path = Path(google_path).expanduser().resolve()
                if not credentials_path.is_file():
                    raise FileNotFoundError(f"Nie znaleziono pliku: {credentials_path}")
                with credentials_path.open("r", encoding="utf-8") as file:
                    google_credentials = json.load(file)
                _validate_google_credentials(google_credentials)
                settings["google_credentials_path"] = str(credentials_path)
                googleAPI.CREDENTIALS_FILE = str(credentials_path)

            microsoft_id = self.microsoft_client_id_entry.get().strip()
            environment_id = os.environ.get("MICROSOFT_CLIENT_ID", "").strip()
            if for_source in (None, "microsoft") and microsoft_id and environment_id and microsoft_id != environment_id:
                raise ValueError("Zmienna MICROSOFT_CLIENT_ID ma pierwszeństwo. Zmień ją albo wklej tę samą wartość.")
            if microsoft_id and for_source in (None, "microsoft"):
                microsoft_path = Path(MicrosoftAPI.CREDENTIALS_FILE)
                with microsoft_path.open("w", encoding="utf-8") as file:
                    json.dump({"client_id": microsoft_id, "tenant_id": "common"}, file, indent=4)

            with SETTINGS_FILE.open("w", encoding="utf-8") as file:
                json.dump(settings, file, ensure_ascii=False, indent=4)
            if show_success:
                self.status_label.configure(text="Ustawienia API zapisane.", text_color="green")
            return True
        except (OSError, json.JSONDecodeError, ValueError) as error:
            self.status_label.configure(text=f"Błąd ustawień API: {error}", text_color="red")
            return False

    def _start_import(self, source):
        if not self._save_api_settings(show_success=False, for_source=source):
            return
        self.status_label.configure(text="Autoryzacja i pobieranie danych w tle...", text_color="yellow")
        self.google_btn.configure(state="disabled")
        self.ms_btn.configure(state="disabled")
        threading.Thread(target=self._worker, args=(source,), daemon=True).start()

    def _worker(self, source):
        try:
            if source == "google":
                tasks = googleAPI.download_tasks(as_objects=True)
            elif source == "microsoft":
                tasks = MicrosoftAPI.download_tasks(as_objects=True)
            else:
                raise ValueError(f"Unknown import source: {source}")
            self.after(0, self._process_and_save, tasks)
        except Exception as error:
            self.after(0, self._show_error, str(error))

    def _process_and_save(self, downloaded_tasks):
        try:
            added_tasks, tag_count, duplicate_count = merge_downloaded_tasks(downloaded_tasks)
            task_count = len(added_tasks)
            task_titles = [
                str(getattr(task, "description", "")).splitlines()[0].strip() or f"Zadanie {task.id}"
                for task in added_tasks
            ]
            print("Zaimportowane zadania:")
            if task_titles:
                for task, title in zip(added_tasks, task_titles):
                    print(f"  [{task.id}] {title}")
            else:
                print("  Brak nowych zadań.")

            self.imported_tasks_box.configure(state="normal")
            self.imported_tasks_box.delete("1.0", "end")
            self.imported_tasks_box.insert(
                "1.0",
                "\n".join(f"[{task.id}] {title}" for task, title in zip(added_tasks, task_titles))
                or "Brak nowych zadań.",
            )
            self.imported_tasks_box.configure(state="disabled")

            message = f"Gotowe! Zaimportowano {task_count} zadań i {tag_count} nowych tagów."
            if duplicate_count:
                message += f" Pominięto {duplicate_count} już zaimportowanych."
            self.status_label.configure(text=message, text_color="green")
        except Exception as error:
            self._show_error(str(error))
            return
        self.google_btn.configure(state="normal")
        self.ms_btn.configure(state="normal")

    def _show_error(self, error_msg):
        self.status_label.configure(text=f"Błąd: {error_msg}", text_color="red")
        self.google_btn.configure(state="normal")
        self.ms_btn.configure(state="normal")