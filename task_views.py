import json
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

import datas
from tag_calendar import load_tags
from task_lifecycle import ACTIVE_TASKS_FILE, complete_task, delete_task, read_task_records, start_task, update_task


def _task_title(record):
    description = str(record.get("description", "")).strip()
    return description.splitlines()[0] if description else f"Zadanie {record.get('id', '')}"


def _planned_minutes(value):
    if not value:
        return ""
    try:
        if "T" in str(value):
            planned_time = datetime.fromisoformat(str(value)).time()
            return str(planned_time.hour * 60 + planned_time.minute)
        hours, minutes = str(value).split(":")[-2:]
        return str(int(hours) * 60 + int(minutes))
    except (TypeError, ValueError):
        return ""


class ActiveTasksFrame(ctk.CTkFrame):
    def __init__(self, master, on_data_changed=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_data_changed = on_data_changed

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))
        ctk.CTkLabel(header, text="Aktywne zadania", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.count_label = ctk.CTkLabel(header, text="")
        self.count_label.pack(side="right")

        self.task_list = ctk.CTkScrollableFrame(self)
        self.task_list.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.refresh()

    def refresh(self):
        for child in self.task_list.winfo_children():
            child.destroy()
        try:
            records = read_task_records(ACTIVE_TASKS_FILE)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            self.count_label.configure(text="Błąd odczytu")
            ctk.CTkLabel(self.task_list, text=f"Nie można wczytać zadań: {error}").pack(anchor="w", padx=12, pady=12)
            return

        self.count_label.configure(text=f"{len(records)} aktywnych")
        if not records:
            ctk.CTkLabel(self.task_list, text="Brak aktywnych zadań.").pack(anchor="w", padx=12, pady=12)
            return

        for record in records:
            row = ctk.CTkFrame(self.task_list, corner_radius=4)
            row.pack(fill="x", padx=4, pady=4)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                row,
                text=_task_title(record),
                anchor="w",
                font=ctk.CTkFont(size=14, weight="bold"),
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))

            details = [f"ID {record.get('id', '?')}"]
            in_progress = record.get("status") == "in_progress"
            details.append("W trakcie" if in_progress else "Nie rozpoczęte")
            if record.get("deadline"):
                details.append(f"Termin: {record['deadline']}")
            tag_names = [tag.get("name", "") for tag in record.get("tags", []) if tag.get("name")]
            if tag_names:
                details.append(", ".join(tag_names))
            ctk.CTkLabel(row, text="  ·  ".join(details), anchor="w", text_color="gray70").grid(
                row=1, column=0, sticky="ew", padx=12, pady=(0, 8)
            )
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=0, column=1, rowspan=2, padx=10, pady=6)
            ctk.CTkButton(
                actions,
                text="Edytuj",
                width=72,
                command=lambda task_record=record: self._edit_task(task_record),
            ).pack(side="left", padx=3)
            ctk.CTkButton(
                actions,
                text="Usuń",
                width=64,
                fg_color="#963b3b",
                hover_color="#b34848",
                command=lambda task_record=record: self._delete_task(task_record),
            ).pack(side="left", padx=3)
            ctk.CTkButton(
                actions,
                text="Zakończ" if in_progress else "Rozpocznij",
                width=100,
                command=lambda task_record=record, started=in_progress: self._open_survey(task_record)
                if started
                else lambda task_record=record: self._start_task(task_record),
            ).pack(side="left", padx=3)

    def _edit_task(self, task_record):
        TaskEditDialog(self.winfo_toplevel(), task_record, self._after_task_change)

    def _delete_task(self, task_record):
        title = _task_title(task_record)
        if not messagebox.askyesno("Usuń task", f"Usunąć task „{title}”?", parent=self.winfo_toplevel()):
            return
        try:
            delete_task(task_record["id"])
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
            self.count_label.configure(text=f"Nie usunięto: {error}")
            return
        datas.current_tasks_list[:] = [
            task for task in datas.current_tasks_list if str(getattr(task, "id", "")) != str(task_record["id"])
        ]
        self._after_task_change()

    def _start_task(self, task_record):
        try:
            start_task(task_record["id"])
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
            self.count_label.configure(text=f"Nie rozpoczęto: {error}")
            return
        self.refresh()

    def _open_survey(self, task_record):
        TaskSurveyDialog(self.winfo_toplevel(), task_record, self._after_completion)

    def _after_completion(self):
        self.refresh()
        if self.on_data_changed:
            self.on_data_changed()

    def _after_task_change(self):
        self.refresh()
        if self.on_data_changed:
            self.on_data_changed()


class TaskEditDialog(ctk.CTkToplevel):
    def __init__(self, master, task_record, on_saved, **kwargs):
        super().__init__(master, **kwargs)
        self.task_record = task_record
        self.on_saved = on_saved
        self.tags = load_tags()
        self.tag_checks = {}

        self.title("Edytuj task")
        self.geometry("560x650")
        self.minsize(500, 560)
        self.transient(master)
        self.grab_set()

        content = ctk.CTkScrollableFrame(self)
        content.pack(fill="both", expand=True, padx=14, pady=(14, 0))

        ctk.CTkLabel(content, text="Opis", anchor="w").pack(fill="x", pady=(4, 3))
        self.description = ctk.CTkTextbox(content, height=90, wrap="word")
        self.description.pack(fill="x", pady=(0, 10))
        self.description.insert("1.0", str(task_record.get("description", "")))

        ctk.CTkLabel(content, text="Termin (ISO, np. 2026-10-04T12:00:00)", anchor="w").pack(fill="x", pady=(2, 3))
        self.deadline = ctk.CTkEntry(content, placeholder_text="Termin opcjonalny")
        self.deadline.pack(fill="x", pady=(0, 10))
        if task_record.get("deadline"):
            self.deadline.insert(0, str(task_record["deadline"]))

        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(row, text="Planowany czas (HH:MM)").pack(side="left")
        self.planned_time = ctk.CTkEntry(row, width=110, placeholder_text="opcjonalnie")
        self.planned_time.pack(side="right")
        formatted_time = self._format_time(task_record.get("time"))
        if formatted_time:
            self.planned_time.insert(0, formatted_time)

        priority_row = ctk.CTkFrame(content, fg_color="transparent")
        priority_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(priority_row, text="Priorytet").pack(side="left")
        self.priority = ctk.CTkOptionMenu(priority_row, values=["1", "2", "3", "4"], width=90)
        self.priority.set(str(task_record.get("priority", 1)))
        self.priority.pack(side="right")

        focus_row = ctk.CTkFrame(content, fg_color="transparent")
        focus_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(focus_row, text="Skupienie").pack(side="left")
        self.focus = ctk.CTkEntry(focus_row, width=110, placeholder_text="np. 2.5")
        self.focus.pack(side="right")
        self.focus.insert(0, str(task_record.get("focus", 0)))

        ctk.CTkLabel(content, text="Tagi").pack(anchor="w", pady=(2, 4))
        selected_tag_ids = {str(tag.get("id")) for tag in task_record.get("tags", [])}
        selected_tag_names = {str(tag.get("name", "")).casefold() for tag in task_record.get("tags", [])}
        for tag in self.tags:
            check = ctk.CTkCheckBox(content, text=tag.title)
            check.pack(anchor="w", pady=2)
            if str(tag.id) in selected_tag_ids or tag.title.casefold() in selected_tag_names:
                check.select()
            self.tag_checks[tag.id] = (tag, check)

        self.error_label = ctk.CTkLabel(self, text="", text_color="#ef6461", anchor="w", wraplength=520)
        self.error_label.pack(fill="x", padx=18, pady=6)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(buttons, text="Anuluj", fg_color="gray", command=self.destroy).pack(side="left")
        ctk.CTkButton(buttons, text="Zapisz zmiany", command=self._save).pack(side="right")

    @staticmethod
    def _format_time(value):
        if not value:
            return ""
        try:
            if "T" in str(value):
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return f"{parsed.hour:02d}:{parsed.minute:02d}"
            hours, minutes = str(value).split(":")[-2:]
            return f"{int(hours):02d}:{int(minutes):02d}"
        except (TypeError, ValueError):
            return str(value)

    def _save(self):
        description = self.description.get("1.0", "end").strip()
        deadline = self.deadline.get().strip() or None
        planned_time = self.planned_time.get().strip()
        if deadline:
            try:
                datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            except ValueError:
                self.error_label.configure(text="Wpisz termin w formacie ISO albo zostaw pole puste.")
                return

        if planned_time:
            try:
                hours, minutes = (int(part) for part in planned_time.split(":"))
                if hours < 0 or not 0 <= minutes < 60:
                    raise ValueError
                if "T" in str(self.task_record.get("time", "")):
                    planned_time = f"1970-01-01T{hours:02d}:{minutes:02d}:00"
                else:
                    planned_time = f"{hours:02d}:{minutes:02d}"
            except ValueError:
                self.error_label.configure(text="Planowany czas podaj jako HH:MM.")
                return
        else:
            planned_time = None

        try:
            updates = {
                "description": description,
                "deadline": deadline,
                "time": planned_time,
                "focus": float(self.focus.get().strip()),
                "priority": int(self.priority.get()),
                "tags": [
                    {"id": tag.id, "name": tag.title}
                    for tag, check in self.tag_checks.values()
                    if check.get()
                ],
            }
            saved = update_task(self.task_record["id"], updates)
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
            self.error_label.configure(text=f"Nie zapisano zmian: {error}")
            return

        current_tags = {int(tag["id"]): tag for tag in updates["tags"]}
        for task in datas.current_tasks_list:
            if str(getattr(task, "id", "")) == str(saved["id"]):
                task.description = saved["description"]
                task.deadline = saved.get("deadline")
                task.time = saved.get("time")
                task.focus = saved.get("focus", 0)
                task.priority = saved.get("priority", 1)
                task.tags = [tag for tag in self.tags if tag.id in current_tags]
        self.on_saved()
        self.destroy()


class TaskSurveyDialog(ctk.CTkToplevel):
    def __init__(self, master, task_record, on_completed, **kwargs):
        super().__init__(master, **kwargs)
        self.task_record = task_record
        self.on_completed = on_completed
        self.rating_sliders = {}

        self.title("Ankieta po zadaniu")
        self.geometry("560x680")
        self.minsize(500, 620)
        self.transient(master)
        self.grab_set()

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=22, pady=18)
        ctk.CTkLabel(content, text="Zanim zamkniesz zadanie", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w")
        task_description = str(task_record.get("description", "")).strip() or "Bez opisu"
        task_identity = f"Zadanie {task_record.get('id', '?')} · {task_description}"
        ctk.CTkLabel(content, text=task_identity, wraplength=500, justify="left").pack(anchor="w", pady=(4, 12))

        duration_row = ctk.CTkFrame(content, fg_color="transparent")
        duration_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(duration_row, text="Rzeczywisty czas pracy (min)").pack(side="left")
        self.duration_entry = ctk.CTkEntry(duration_row, width=100, placeholder_text="minuty")
        self.duration_entry.pack(side="right")
        planned_minutes = _planned_minutes(task_record.get("time"))
        if planned_minutes:
            self.duration_entry.insert(0, planned_minutes)

        self._add_rating(content)

        ctk.CTkLabel(content, text="Notatka (opcjonalnie)").pack(anchor="w", pady=(6, 3))
        self.note_box = ctk.CTkTextbox(content, height=58, wrap="word")
        self.note_box.pack(fill="x")

        self.error_label = ctk.CTkLabel(content, text="", text_color="#ef6461", wraplength=500, justify="left")
        self.error_label.pack(anchor="w", pady=(8, 0))
        buttons = ctk.CTkFrame(content, fg_color="transparent")
        buttons.pack(fill="x", side="bottom", pady=(12, 0))
        ctk.CTkButton(buttons, text="Anuluj", fg_color="gray", command=self.destroy).pack(side="left")
        ctk.CTkButton(buttons, text="Zapisz i zakończ", command=self._submit).pack(side="right")

    def _add_rating(self, parent):
        group = ctk.CTkFrame(parent, fg_color="transparent")
        group.pack(fill="x", pady=4)
        heading = ctk.CTkFrame(group, fg_color="transparent")
        heading.pack(fill="x")
        ctk.CTkLabel(heading, text="Jak oceniasz skupienie podczas tego zadania?", anchor="w").pack(
            side="left", fill="x", expand=True
        )
        value_label = ctk.CTkLabel(heading, text="0", width=40, font=ctk.CTkFont(weight="bold"))
        value_label.pack(side="right")
        slider = ctk.CTkSlider(
            group,
            from_=-5,
            to=5,
            number_of_steps=10,
            command=lambda value: value_label.configure(
                text="0" if float(value) == 0 else f"{float(value):+g}"
            ),
        )
        slider.set(0)
        slider.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(
            group,
            text="-5  -4  -3  -2  -1   0  +1  +2  +3  +4  +5",
            text_color="gray70",
        ).pack(anchor="w")
        self.rating_sliders["focus_rating"] = slider

    def _submit(self):
        try:
            survey = {
                "actual_minutes": int(self.duration_entry.get().strip()),
                "focus_rating": int(round(self.rating_sliders["focus_rating"].get())),
                "note": self.note_box.get("1.0", "end").strip(),
            }
            completed_task = complete_task(self.task_record["id"], survey)
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
            self.error_label.configure(text=f"Nie zapisano ankiety: {error}")
            return

        print(f"Zakończono zadanie [{completed_task['id']}]: {_task_title(completed_task)}")
        self.on_completed()
        self.destroy()