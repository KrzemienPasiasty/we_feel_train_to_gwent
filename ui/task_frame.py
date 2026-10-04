from datetime import datetime
from typing import Callable, List, Optional
import inspect
import threading
import customtkinter as ctk

from models.task import Task
from models.tag import Tag
import datas


class TaskFrame(ctk.CTkFrame):
    def __init__(self, master, on_task_added: Optional[Callable[[Task], None]] = None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_task_added = on_task_added
        self.available_tags = datas.tags_list
        self.autofill_callback = datas.fill_task
        self.selected_tags = []
        self.tag_buttons = {}

        # --- Nagłówek ---
        self.title_label = ctk.CTkLabel(self, text="Utwórz nowe zadanie", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=(10, 15))

        # --- Przycisk Autofill ---
        self.autofill_btn = ctk.CTkButton(self, text="Uzupełnij formularz przez AI", command=self._start_autofill)
        self.autofill_btn.pack(pady=(0, 15), fill="x", padx=20)

        # --- Status / Informacja zwrotna ---
        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self.status_label.pack(pady=(0, 5))

        # --- Pola formularza ---

        # 1. Description
        self.desc_label = ctk.CTkLabel(self, text="Opis zadania (Description):")
        self.desc_label.pack(anchor="w", padx=20)
        self.desc_entry = ctk.CTkTextbox(self, height=60)
        self.desc_entry.pack(fill="x", padx=20, pady=(0, 10))

        # 2. Deadline (Data i czas w jednej linii)
        self.deadline_label = ctk.CTkLabel(self, text="Termin (Deadline):")
        self.deadline_label.pack(anchor="w", padx=20)

        self.deadline_card = ctk.CTkFrame(self, fg_color=("gray85", "gray20"), corner_radius=10)
        self.deadline_card.pack(fill="x", padx=20, pady=(0, 10), ipady=3, ipadx=5)

        now = datetime.now()

        # Pojedyncza linia łącząca wybór daty i czasu
        datetime_row = ctk.CTkFrame(self.deadline_card, fg_color="transparent")
        datetime_row.pack(fill="x", pady=5, padx=5)

        # Data
        ctk.CTkLabel(datetime_row, text="📅", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(5, 2))

        days = [f"{i:02d}" for i in range(1, 32)]
        self.day_opt = ctk.CTkOptionMenu(datetime_row, values=days, width=65)
        self.day_opt.set(f"{now.day:02d}")
        self.day_opt.pack(side="left", padx=2)

        months = [f"{i:02d}" for i in range(1, 13)]
        self.month_opt = ctk.CTkOptionMenu(datetime_row, values=months, width=65)
        self.month_opt.set(f"{now.month:02d}")
        self.month_opt.pack(side="left", padx=2)

        years = [str(y) for y in range(now.year, now.year + 6)]
        self.year_opt = ctk.CTkOptionMenu(datetime_row, values=years, width=80)
        self.year_opt.set(str(now.year))
        self.year_opt.pack(side="left", padx=2)

        # Czas
        ctk.CTkLabel(datetime_row, text="⏰", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(15, 2))

        hours = [f"{i:02d}" for i in range(24)]
        self.deadline_hour = ctk.CTkOptionMenu(datetime_row, values=hours, width=65)
        self.deadline_hour.set("12")
        self.deadline_hour.pack(side="left", padx=2)

        ctk.CTkLabel(datetime_row, text=":", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=1)

        minutes = [f"{i:02d}" for i in range(0, 60, 5)]
        self.deadline_minute = ctk.CTkOptionMenu(datetime_row, values=minutes, width=65)
        self.deadline_minute.set("00")
        self.deadline_minute.pack(side="left", padx=2)

        # 3. Time (Wymagany czas)
        self.time_label = ctk.CTkLabel(self, text="Wymagany czas (Time) np. 02:30 (zostaw puste dla auto):")
        self.time_label.pack(anchor="w", padx=20)
        self.time_entry = ctk.CTkEntry(self, placeholder_text="")
        self.time_entry.pack(fill="x", padx=20, pady=(0, 10))

        # 4. Focus (Slider + Checkbox)
        self.focus_label = ctk.CTkLabel(self, text="Skupienie (Focus):")
        self.focus_label.pack(anchor="w", padx=20)

        self.focus_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.focus_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.focus_slider = ctk.CTkSlider(self.focus_frame, from_=0, to=10, number_of_steps=10)
        self.focus_slider.set(5)
        self.focus_slider.pack(side="left", expand=True, fill="x", padx=(0, 10))

        self.focus_auto_cb = ctk.CTkCheckBox(self.focus_frame, text="Auto (puste)", command=self._toggle_focus_slider)
        self.focus_auto_cb.pack(side="right")

        # 5. Priority (1 - 4)
        self.priority_label = ctk.CTkLabel(self, text="Priorytet (Priority: 1 - 4):")
        self.priority_label.pack(anchor="w", padx=20)
        self.priority_slider = ctk.CTkSlider(self, from_=1, to=4, number_of_steps=3)
        self.priority_slider.set(1)
        self.priority_slider.pack(fill="x", padx=20, pady=(0, 15))

        # --- Tagi w formie przycisków ---
        self.tags_label = ctk.CTkLabel(self, text="Wybierz Tagi:")
        self.tags_label.pack(anchor="w", padx=20)

        self.tags_frame = ctk.CTkScrollableFrame(self, height=80, orientation="horizontal")
        self.tags_frame.pack(fill="x", padx=20, pady=(0, 20))

        self._create_tag_buttons()

        # --- Przycisk Dodawania Zadania ---
        self.add_task_btn = ctk.CTkButton(self, text="Dodaj zadanie (Add Task)", fg_color="green",
                                          hover_color="darkgreen", command=self._submit_task)
        self.add_task_btn.pack(pady=(10, 20), fill="x", padx=20)

    def _toggle_focus_slider(self):
        if self.focus_auto_cb.get() == 1:
            self.focus_slider.configure(state="disabled")
        else:
            self.focus_slider.configure(state="normal")

    def _create_tag_buttons(self):
        self.available_tags = datas.tags_list
        for tag in self.available_tags:
            btn = ctk.CTkButton(
                self.tags_frame,
                text=tag.title,
                fg_color="gray",
                text_color="white",
                command=lambda t=tag: self._toggle_tag(t)
            )
            btn.pack(side="left", padx=5, pady=5)
            self.tag_buttons[tag] = btn

    def _rgb_to_hex(self, rgb_tuple):
        return f'#{rgb_tuple[0]:02x}{rgb_tuple[1]:02x}{rgb_tuple[2]:02x}'

    def _toggle_tag(self, tag: Tag):
        button = self.tag_buttons.get(tag)
        if not button:
            return
        if tag in self.selected_tags:
            self.selected_tags.remove(tag)
            button.configure(fg_color="gray")
        else:
            self.selected_tags.append(tag)
            active_color = self._rgb_to_hex(tag.color) if hasattr(tag, 'color') and tag.color else "#1f6aa5"
            button.configure(fg_color=active_color)

    def _start_autofill(self):
        description = self.desc_entry.get("0.0", "end").strip()
        if not description:
            self.status_label.configure(
                text="Podaj opis zadania przed uzyciem AI!",
                text_color="orange"
            )
            return

        self.status_label.configure(text="AI analizuje zadanie...", text_color="white")
        self.autofill_btn.configure(
            state="disabled",
            text="Przetwarzanie (Oczekiwanie na odpowiedz)..."
        )

        time_val = self.time_entry.get().strip()
        autofill_time = not bool(time_val)
        autofill_focus = (self.focus_auto_cb.get() == 1)

        # If neither is explicitly indicated as empty, user clicked AI to estimate both
        if not autofill_time and not autofill_focus:
            autofill_time = True
            autofill_focus = True

        task = Task()
        task.description = description
        task.time = time_val if not autofill_time else ""
        task.focus = int(self.focus_slider.get()) if not autofill_focus else 0
        task.priority = int(self.priority_slider.get())
        task.tags = list(self.selected_tags)

        result_container = {"done": False, "data": None, "error": None}

        def worker():
            try:
                callback = self.autofill_callback
                res = None
                if callable(callback):
                    sig = inspect.signature(callback)
                    param_count = len(sig.parameters)
                    if param_count >= 3:
                        res = callback(task, autofill_focus, autofill_time)
                    elif param_count == 1:
                        res = callback(task)
                    else:
                        res = callback(task, autofill_focus, autofill_time)
                else:
                    res = datas.fill_task(task, autofill_focus, autofill_time)

                result_container["data"] = res
            except Exception as e:
                result_container["error"] = str(e)
            finally:
                result_container["done"] = True

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def check_result():
            if result_container["done"]:
                if result_container["error"]:
                    self._apply_autofill_error(result_container["error"])
                else:
                    self._apply_autofill_data(result_container["data"])
            else:
                self.after(100, check_result)

        self.after(100, check_result)

    def _apply_autofill_data(self, data):
        self.autofill_btn.configure(state="normal", text="Uzupełnij formularz przez AI")
        if not data:
            self.status_label.configure(text="Brak danych z AI", text_color="orange")
            return

        if isinstance(data, Task):
            if data.time:
                self.time_entry.delete(0, "end")
                self.time_entry.insert(0, str(data.time))

            if data.focus is not None:
                self.focus_auto_cb.deselect()
                self._toggle_focus_slider()
                f_val = float(data.focus)
                if -5 <= f_val <= 5:
                    f_val = f_val + 5
                self.focus_slider.set(max(0, min(10, f_val)))

            if getattr(data, "priority", None) is not None:
                self.priority_slider.set(max(1, min(4, int(data.priority))))

            if getattr(data, "tags", None):
                for tag in data.tags:
                    tag_title = tag.title if hasattr(tag, "title") else str(tag)
                    for avail_tag in self.available_tags:
                        if avail_tag.title == tag_title and avail_tag not in self.selected_tags:
                            self._toggle_tag(avail_tag)

            self.status_label.configure(text="Pola uzupelnione przez AI!", text_color="#4caf50")
            self.after(4000, lambda: self.status_label.configure(text=""))
            return

        if isinstance(data, dict):
            if "description" in data and data["description"]:
                self.desc_entry.delete("0.0", "end")
                self.desc_entry.insert("0.0", data["description"])

            if "focus" in data and data["focus"] is not None:
                self.focus_auto_cb.deselect()
                self._toggle_focus_slider()
                f_val = float(data["focus"])
                if -5 <= f_val <= 5:
                    f_val = f_val + 5
                self.focus_slider.set(max(0, min(10, f_val)))

            if "priority" in data and data["priority"] is not None:
                self.priority_slider.set(max(1, min(4, int(data["priority"]))))

            if "time" in data and data["time"]:
                self.time_entry.delete(0, "end")
                self.time_entry.insert(0, str(data["time"]))

            if "tags" in data and data["tags"]:
                for tag_item in data["tags"]:
                    tag_title = tag_item.title if hasattr(tag_item, "title") else str(tag_item)
                    for avail_tag in self.available_tags:
                        if avail_tag.title == tag_title and avail_tag not in self.selected_tags:
                            self._toggle_tag(avail_tag)

            self.status_label.configure(text="Pola uzupelnione przez AI!", text_color="#4caf50")
            self.after(4000, lambda: self.status_label.configure(text=""))

    def _apply_autofill_error(self, err_msg: str):
        self.autofill_btn.configure(state="normal", text="Uzupełnij formularz przez AI")
        self.status_label.configure(text=f"Blad AI: {err_msg}", text_color="red")
        self.after(6000, lambda: self.status_label.configure(text=""))

    def _submit_task(self):
        new_task = Task()
        autofill_focus, autofill_time = False, False

        # Sprawdzanie Time
        time_input = self.time_entry.get().strip()
        if not time_input:
            autofill_time = True
            new_task.time = ""
        else:
            new_task.time = time_input

        # Sprawdzanie Focus
        if self.focus_auto_cb.get() == 1:
            autofill_focus = True
            new_task.focus = 0
        else:
            new_task.focus = int(self.focus_slider.get())

        new_task.description = self.desc_entry.get("0.0", "end").strip()
        new_task.priority = int(self.priority_slider.get())

        # Pobieranie daty i czasu z menu rozwijanych
        day = self.day_opt.get()
        month = self.month_opt.get()
        year = self.year_opt.get()
        hour = self.deadline_hour.get()
        minute = self.deadline_minute.get()

        new_task.deadline = f"{year}-{month}-{day}T{hour}:{minute}:00"
        new_task.tags = list(self.selected_tags)

        # Generowanie unikalnego ID
        existing_ids = [t.id for t in datas.current_tasks_list if hasattr(t, "id") and isinstance(t.id, int)]
        new_task.id = (max(existing_ids) + 1) if existing_ids else 1

        # Wywołanie funkcji z datas.py
        datas.add_task(new_task, autofill_focus, autofill_time)

        self.status_label.configure(text="Zadanie zostalo pomyslnie dodane!", text_color="#4caf50")
        self.after(3500, lambda: self.status_label.configure(text=""))

        if self.on_task_added:
            self.on_task_added(new_task)

        self._clear_form()

    def _clear_form(self):
        now = datetime.now()
        self.desc_entry.delete("0.0", "end")
        self.time_entry.delete(0, "end")
        self.focus_slider.set(5)
        self.priority_slider.set(1)
        self.focus_auto_cb.deselect()
        self._toggle_focus_slider()

        # Reset daty i czasu do aktualnego
        self.day_opt.set(f"{now.day:02d}")
        self.month_opt.set(f"{now.month:02d}")
        self.year_opt.set(str(now.year))
        self.deadline_hour.set("12")
        self.deadline_minute.set("00")

        for tag in list(self.selected_tags):
            self._toggle_tag(tag)
