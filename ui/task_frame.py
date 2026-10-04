from datetime import datetime
from typing import Callable, List, Optional
import inspect
import threading
import customtkinter as ctk

from models.task import Task
from models.tag import Tag
import datas


class TaskFrame(ctk.CTkFrame):
    """
    Formularz tworzenia/edycji zadania oparty na wytycznych 'EDIT TASKA.svg'
    z podpowiedziami artysty (how much focus..., when do you start..., how long..., what category..., how urgent...)
    oraz kolorystyką FUTUREFLOW (#E169FF / neon accents).
    """

    ACCENT_PURPLE = "#E169FF"
    DEEP_PURPLE = "#571FA0"
    VIVID_MAGENTA = "#D83CFF"
    CARD_BG = ("#f4f0f8", "#1e1828")
    BORDER_COLOR = ("#d5cae6", "#3d3250")

    def __init__(self, master, on_task_added: Optional[Callable[[Task], None]] = None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.on_task_added = on_task_added
        self.available_tags = datas.tags_list
        self.autofill_callback = datas.fill_task
        self.selected_tags = []
        self.tag_buttons = {}

        # --- Nagłówek ---
        header_box = ctk.CTkFrame(self, fg_color="transparent")
        header_box.pack(pady=(6, 10), fill="x", padx=15)

        self.title_label = ctk.CTkLabel(
            header_box,
            text="✨ FUTUREFLOW — UTWÓRZ / EDYTUJ ZADANIE",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.ACCENT_PURPLE,
        )
        self.title_label.pack(side="left")

        # --- Przycisk Autofill AI ---
        self.autofill_btn = ctk.CTkButton(
            self,
            text="⚡ Uzupełnij parametry przez AI (Autofill)",
            fg_color=self.DEEP_PURPLE,
            hover_color="#6e28c7",
            font=ctk.CTkFont(weight="bold"),
            command=self._start_autofill,
        )
        self.autofill_btn.pack(pady=(0, 10), fill="x", padx=15)

        # --- Status / Informacja zwrotna ---
        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self.status_label.pack(pady=(0, 4))

        # Scrollable container for form fields
        form_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=self.CARD_BG,
            corner_radius=12,
            border_width=1,
            border_color=self.BORDER_COLOR,
        )
        form_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # 1. Description
        desc_hdr = ctk.CTkFrame(form_scroll, fg_color="transparent")
        desc_hdr.pack(fill="x", padx=15, pady=(10, 2))
        ctk.CTkLabel(desc_hdr, text="Opis zadania (Description):", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        self.desc_entry = ctk.CTkTextbox(form_scroll, height=55)
        self.desc_entry.pack(fill="x", padx=15, pady=(0, 10))

        # 2. Focus (how much focus does this task require?)
        focus_hdr = ctk.CTkFrame(form_scroll, fg_color="transparent")
        focus_hdr.pack(fill="x", padx=15, pady=(4, 2))
        ctk.CTkLabel(focus_hdr, text="Wymagane skupienie (Focus):", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkLabel(focus_hdr, text="  (how much focus does this task require?)", font=ctk.CTkFont(size=11, slant="italic"), text_color="gray").pack(side="left")

        self.focus_frame = ctk.CTkFrame(form_scroll, fg_color="transparent")
        self.focus_frame.pack(fill="x", padx=15, pady=(0, 10))

        self.focus_slider = ctk.CTkSlider(self.focus_frame, from_=0, to=10, number_of_steps=10, progress_color=self.ACCENT_PURPLE)
        self.focus_slider.set(5)
        self.focus_slider.pack(side="left", expand=True, fill="x", padx=(0, 10))

        self.focus_auto_cb = ctk.CTkCheckBox(self.focus_frame, text="Auto (oszacuj)", command=self._toggle_focus_slider)
        self.focus_auto_cb.pack(side="right")

        # 3. Deadline (when do you start the task? when is your deadline?)
        dl_hdr = ctk.CTkFrame(form_scroll, fg_color="transparent")
        dl_hdr.pack(fill="x", padx=15, pady=(4, 2))
        ctk.CTkLabel(dl_hdr, text="Termin ostateczny (Deadline):", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkLabel(dl_hdr, text="  (when do you start the task? when is your deadline?)", font=ctk.CTkFont(size=11, slant="italic"), text_color="gray").pack(side="left")

        self.deadline_card = ctk.CTkFrame(form_scroll, fg_color=("gray85", "#241d30"), corner_radius=10, border_width=1, border_color=self.BORDER_COLOR)
        self.deadline_card.pack(fill="x", padx=15, pady=(0, 10), ipady=3, ipadx=5)

        now = datetime.now()
        datetime_row = ctk.CTkFrame(self.deadline_card, fg_color="transparent")
        datetime_row.pack(fill="x", pady=4, padx=5)

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

        # 4. Time / Duration (how long is this task going to take?)
        time_hdr = ctk.CTkFrame(form_scroll, fg_color="transparent")
        time_hdr.pack(fill="x", padx=15, pady=(4, 2))
        ctk.CTkLabel(time_hdr, text="Wymagany czas trwania (Duration):", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkLabel(time_hdr, text="  (how long is this task going to take?)", font=ctk.CTkFont(size=11, slant="italic"), text_color="gray").pack(side="left")

        self.time_entry = ctk.CTkEntry(form_scroll, placeholder_text="np. 01:30 lub 12:12 (zostaw puste dla auto)")
        self.time_entry.pack(fill="x", padx=15, pady=(0, 10))

        # 5. Category / Tags (what category is this task?)
        tag_hdr = ctk.CTkFrame(form_scroll, fg_color="transparent")
        tag_hdr.pack(fill="x", padx=15, pady=(4, 2))
        ctk.CTkLabel(tag_hdr, text="Kategoria / Tagi (Tags):", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkLabel(tag_hdr, text="  (what category is this task?) Tags...", font=ctk.CTkFont(size=11, slant="italic"), text_color="gray").pack(side="left")

        self.tags_frame = ctk.CTkScrollableFrame(form_scroll, height=65, orientation="horizontal", fg_color=("gray90", "#241d30"))
        self.tags_frame.pack(fill="x", padx=15, pady=(0, 10))
        self._create_tag_buttons()

        # 6. Priority / Urgency (how urgent is this task?)
        prio_hdr = ctk.CTkFrame(form_scroll, fg_color="transparent")
        prio_hdr.pack(fill="x", padx=15, pady=(4, 2))
        ctk.CTkLabel(prio_hdr, text="Priorytet pilności (Priority: 1 - 4):", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkLabel(prio_hdr, text="  (how urgent is this task? Low / Med / High / Critical)", font=ctk.CTkFont(size=11, slant="italic"), text_color="gray").pack(side="left")

        self.priority_slider = ctk.CTkSlider(form_scroll, from_=1, to=4, number_of_steps=3, progress_color=self.ACCENT_PURPLE)
        self.priority_slider.set(1)
        self.priority_slider.pack(fill="x", padx=15, pady=(0, 14))

        # --- Przycisk Dodawania Zadania ---
        self.add_task_btn = ctk.CTkButton(
            self,
            text="💾 Dodaj zadanie (Add Task)",
            fg_color=self.ACCENT_PURPLE,
            hover_color=self.VIVID_MAGENTA,
            text_color="black",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._submit_task,
        )
        self.add_task_btn.pack(pady=(6, 12), fill="x", padx=15)

    def _toggle_focus_slider(self):
        if self.focus_auto_cb.get() == 1:
            self.focus_slider.configure(state="disabled")
        else:
            self.focus_slider.configure(state="normal")

    def refresh_tags(self):
        """Odświeża listę tagów dostępnych w formularzu."""
        for child in self.tags_frame.winfo_children():
            child.destroy()
        self.tag_buttons.clear()
        self._create_tag_buttons()

    def _create_tag_buttons(self):
        self.available_tags = datas.tags_list
        for tag in self.available_tags:
            is_selected = tag in self.selected_tags
            active_color = self._rgb_to_hex(tag.color) if hasattr(tag, "color") and tag.color else "#1f6aa5"
            btn = ctk.CTkButton(
                self.tags_frame,
                text=tag.title,
                fg_color=active_color if is_selected else ("gray75", "#382e4a"),
                text_color="white" if is_selected else ("black", "white"),
                corner_radius=8,
                command=lambda t=tag: self._toggle_tag(t),
            )
            btn.pack(side="left", padx=4, pady=4)
            self.tag_buttons[tag] = btn

    def _rgb_to_hex(self, rgb_tuple):
        return f"#{rgb_tuple[0]:02x}{rgb_tuple[1]:02x}{rgb_tuple[2]:02x}"

    def _toggle_tag(self, tag: Tag):
        button = self.tag_buttons.get(tag)
        if not button:
            return
        if tag in self.selected_tags:
            self.selected_tags.remove(tag)
            button.configure(fg_color=("gray75", "#382e4a"), text_color=("black", "white"))
        else:
            self.selected_tags.append(tag)
            active_color = self._rgb_to_hex(tag.color) if hasattr(tag, "color") and tag.color else "#1f6aa5"
            button.configure(fg_color=active_color, text_color="white")

    def _start_autofill(self):
        description = self.desc_entry.get("0.0", "end").strip()
        if not description:
            self.status_label.configure(
                text="Podaj opis zadania przed użyciem AI!",
                text_color="orange",
            )
            return

        self.status_label.configure(text="AI analizuje zadanie...", text_color="white")
        self.autofill_btn.configure(
            state="disabled",
            text="Przetwarzanie (Oczekiwanie na odpowiedź)...",
        )

        time_val = self.time_entry.get().strip()
        autofill_time = not bool(time_val)
        autofill_focus = (self.focus_auto_cb.get() == 1)

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
        self.autofill_btn.configure(state="normal", text="⚡ Uzupełnij parametry przez AI (Autofill)")
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

            self.status_label.configure(text="Pola uzupełnione przez AI!", text_color="#4caf50")
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

            self.status_label.configure(text="Pola uzupełnione przez AI!", text_color="#4caf50")
            self.after(4000, lambda: self.status_label.configure(text=""))

    def _apply_autofill_error(self, err_msg: str):
        self.autofill_btn.configure(state="normal", text="⚡ Uzupełnij parametry przez AI (Autofill)")
        self.status_label.configure(text=f"Błąd AI: {err_msg}", text_color="red")
        self.after(6000, lambda: self.status_label.configure(text=""))

    def _submit_task(self):
        new_task = Task()
        autofill_focus, autofill_time = False, False

        time_input = self.time_entry.get().strip()
        if not time_input:
            autofill_time = True
            new_task.time = ""
        else:
            new_task.time = time_input

        if self.focus_auto_cb.get() == 1:
            autofill_focus = True
            new_task.focus = 0
        else:
            new_task.focus = int(self.focus_slider.get())

        new_task.description = self.desc_entry.get("0.0", "end").strip()
        new_task.priority = int(self.priority_slider.get())

        day = self.day_opt.get()
        month = self.month_opt.get()
        year = self.year_opt.get()
        hour = self.deadline_hour.get()
        minute = self.deadline_minute.get()

        new_task.deadline = f"{year}-{month}-{day}T{hour}:{minute}:00"
        new_task.tags = list(self.selected_tags)

        existing_ids = [t.id for t in datas.current_tasks_list if hasattr(t, "id") and isinstance(t.id, int)]
        new_task.id = (max(existing_ids) + 1) if existing_ids else 1

        datas.add_task(new_task, autofill_focus, autofill_time)

        self.status_label.configure(text="Zadanie zostało pomyślnie dodane!", text_color="#4caf50")
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

        self.day_opt.set(f"{now.day:02d}")
        self.month_opt.set(f"{now.month:02d}")
        self.year_opt.set(str(now.year))
        self.deadline_hour.set("12")
        self.deadline_minute.set("00")

        for tag in list(self.selected_tags):
            self._toggle_tag(tag)
