import json
from pathlib import Path
from tkinter import Canvas

import customtkinter as ctk

import datas
from tag import Tag

BASE_DIR = Path(__file__).resolve().parent
TAGS_FILE = BASE_DIR / "tags.json"
CALENDAR_FILE = BASE_DIR / "calendar_states.json"
DAYS = ("Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Niedz")
CALENDAR_SLOT_MINUTES = 5
SLOTS_PER_DAY = 24 * 60 // CALENDAR_SLOT_MINUTES
LEGACY_SLOT_MINUTES = 15
CREATE_TAG_OPTION = "+ Utwórz tag"
COLORS = (
    (0, 120, 212),
    (16, 124, 16),
    (196, 43, 28),
    (202, 80, 16),
    (126, 73, 188),
    (0, 153, 188),
    (196, 82, 157),
    (120, 113, 108),
)


def _read(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        records = json.load(file)
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError(f"Expected a list of objects in {path}")
    return records


def _write(path, records):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=4)
    temporary.replace(path)


def _hex(color):
    return "#%02x%02x%02x" % tuple(color)


def load_tags():
    records = _read(TAGS_FILE)
    datas.tags_list[:] = [
        Tag(int(row.get("id", index + 1)), str(row.get("title", "")), tuple(row.get("color", (100, 100, 100))), bool(row.get("is_interactive", False)))
        for index, row in enumerate(records)
        if str(row.get("title", "")).strip()
    ]
    return datas.tags_list


def add_tag(title, color, recurrences=(), tag_id=None):
    title = title.strip()
    if not title:
        raise ValueError("Wpisz nazwę tagu")
    rows = _read(TAGS_FILE)
    if any(
        int(row.get("id", 0)) != tag_id
        and str(row.get("title", "")).strip().casefold() == title.casefold()
        for row in rows
    ):
        raise ValueError("Tag o tej nazwie już istnieje")
    existing = next((row for row in rows if int(row.get("id", 0)) == tag_id), None) if tag_id else None
    if tag_id is None:
        tag_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
    record = {
        "id": tag_id,
        "title": title,
        "color": list(color),
        "is_interactive": existing.get("is_interactive", False) if existing else False,
        "recurrences": list(recurrences),
    }
    if existing:
        rows[rows.index(existing)] = record
    else:
        rows.append(record)
    _write(TAGS_FILE, rows)
    load_tags()
    return next(tag for tag in datas.tags_list if tag.id == tag_id)


def toggle_calendar_slot(day, slot, tag_id, recurring_tag_ids=(), calendar_path=CALENDAR_FILE, present=None):
    day = int(day)
    slot = int(slot)
    tag_id = int(tag_id)
    if not 0 <= day < 7 or not 0 <= slot < SLOTS_PER_DAY:
        raise ValueError("Slot poza zakresem kalendarza")

    records = _read(calendar_path)
    states = {}
    excluded = {}
    for row in records:
        try:
            saved_day = int(row["day"])
            start_minute = int(row["start_minute"])
            saved_tag_ids = row.get("tag_ids")
            if saved_tag_ids is not None:
                saved_slot = start_minute // CALENDAR_SLOT_MINUTES
                if 0 <= saved_day < 7 and 0 <= saved_slot < SLOTS_PER_DAY:
                    states[(saved_day, saved_slot)] = list(dict.fromkeys(int(value) for value in saved_tag_ids))
                    excluded[(saved_day, saved_slot)] = list(
                        dict.fromkeys(int(value) for value in row.get("excluded_tag_ids", []))
                    )
            else:
                saved_tag_id = int(row["tag_id"])
                legacy_start = start_minute // LEGACY_SLOT_MINUTES * LEGACY_SLOT_MINUTES
                first_slot = legacy_start // CALENDAR_SLOT_MINUTES
                for saved_slot in range(first_slot, first_slot + LEGACY_SLOT_MINUTES // CALENDAR_SLOT_MINUTES):
                    if 0 <= saved_day < 7 and saved_slot < SLOTS_PER_DAY:
                        states.setdefault((saved_day, saved_slot), []).append(saved_tag_id)
                        excluded.setdefault((saved_day, saved_slot), [])
        except (KeyError, TypeError, ValueError):
            continue

    key = (day, slot)
    tag_ids = states.setdefault(key, [])
    excluded_ids = excluded.setdefault(key, [])
    recurring_ids = set(int(value) for value in recurring_tag_ids)
    visible = tag_id in tag_ids or (tag_id in recurring_ids and tag_id not in excluded_ids)
    should_be_visible = not visible if present is None else bool(present)
    if should_be_visible:
        if tag_id in recurring_ids:
            if tag_id in excluded_ids:
                excluded_ids.remove(tag_id)
        else:
            if tag_id in excluded_ids:
                excluded_ids.remove(tag_id)
            if tag_id not in tag_ids:
                tag_ids.append(tag_id)
    else:
        if tag_id in tag_ids:
            tag_ids.remove(tag_id)
        if tag_id in recurring_ids and tag_id not in excluded_ids:
            excluded_ids.append(tag_id)
    saved_records = [
        {
            "day": saved_day,
            "start_minute": saved_slot * CALENDAR_SLOT_MINUTES,
            "tag_ids": tag_ids,
            "excluded_tag_ids": excluded.get((saved_day, saved_slot), []),
        }
        for (saved_day, saved_slot), tag_ids in sorted(states.items())
        if tag_ids or excluded.get((saved_day, saved_slot))
    ]
    _write(calendar_path, saved_records)
    return states


def _recurring_states(tag_records):
    states = {}
    for tag in tag_records:
        try:
            tag_id = int(tag["id"])
        except (KeyError, TypeError, ValueError):
            continue
        for rule in tag.get("recurrences", []):
            try:
                frequency = rule["frequency"]
                start_minute = int(rule["start_minute"])
                end_minute = int(rule["end_minute"])
                days = range(7) if frequency == "daily" else [int(day) for day in rule["days"]]
                if frequency not in {"daily", "weekly"} or not 0 <= start_minute < end_minute <= 24 * 60:
                    continue
                first_slot = start_minute // CALENDAR_SLOT_MINUTES
                end_slot = end_minute // CALENDAR_SLOT_MINUTES
                for day in days:
                    if not 0 <= day < 7:
                        continue
                    for slot in range(first_slot, end_slot):
                        states.setdefault((day, slot), []).append(tag_id)
            except (KeyError, TypeError, ValueError):
                continue
    return states


class RecurrenceRuleFrame(ctk.CTkFrame):
    DAY_LABELS = ("Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd")
    HOURS = tuple(f"{hour:02d}" for hour in range(24))
    END_HOURS = HOURS + ("24",)
    MINUTES = tuple(f"{minute:02d}" for minute in range(0, 60, 5))

    def __init__(self, master, on_remove, rule=None, **kwargs):
        super().__init__(master, corner_radius=4, **kwargs)
        rule = rule or {}
        first_row = ctk.CTkFrame(self, fg_color="transparent")
        first_row.pack(fill="x", padx=6, pady=(5, 2))

        self.frequency = ctk.CTkOptionMenu(
            first_row,
            values=("Codziennie", "Co tydzień"),
            width=116,
            command=self._frequency_changed,
        )
        self.frequency.pack(side="left", padx=(0, 8))
        self.start_hour = ctk.CTkOptionMenu(first_row, values=self.HOURS, width=54)
        self.start_hour.pack(side="left")
        ctk.CTkLabel(first_row, text=":").pack(side="left")
        self.start_minute = ctk.CTkOptionMenu(first_row, values=self.MINUTES, width=54)
        self.start_minute.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(first_row, text="do").pack(side="left", padx=(0, 6))
        self.end_hour = ctk.CTkOptionMenu(first_row, values=self.END_HOURS, width=54)
        self.end_hour.pack(side="left")
        ctk.CTkLabel(first_row, text=":").pack(side="left")
        self.end_minute = ctk.CTkOptionMenu(first_row, values=self.MINUTES, width=54)
        self.end_minute.pack(side="left", padx=(0, 6))
        ctk.CTkButton(first_row, text="Usuń", width=56, fg_color="#8f3030", hover_color="#a83b3b", command=on_remove).pack(side="right")

        day_row = ctk.CTkFrame(self, fg_color="transparent")
        day_row.pack(fill="x", padx=6, pady=(0, 5))
        self.day_checks = []
        selected_days = set(int(day) for day in rule.get("days", (0, 1, 2, 3, 4)))
        for day_index, label in enumerate(self.DAY_LABELS):
            checkbox = ctk.CTkCheckBox(day_row, text=label, width=42, checkbox_width=16, checkbox_height=16)
            checkbox.pack(side="left", padx=(0, 4))
            if day_index in selected_days:
                checkbox.select()
            self.day_checks.append(checkbox)

        frequency = "Co tydzień" if rule.get("frequency") == "weekly" else "Codziennie"
        self.frequency.set(frequency)
        start_minute = int(rule.get("start_minute", 9 * 60))
        end_minute = int(rule.get("end_minute", 17 * 60))
        self.start_hour.set(f"{start_minute // 60:02d}")
        self.start_minute.set(f"{start_minute % 60:02d}")
        self.end_hour.set(f"{end_minute // 60:02d}")
        self.end_minute.set(f"{end_minute % 60:02d}")
        self._frequency_changed(frequency)

    def _frequency_changed(self, frequency):
        state = "normal" if frequency == "Co tydzień" else "disabled"
        for checkbox in self.day_checks:
            checkbox.configure(state=state)

    def to_record(self):
        start_minute = int(self.start_hour.get()) * 60 + int(self.start_minute.get())
        end_hour = int(self.end_hour.get())
        end_minute = int(self.end_minute.get())
        if end_hour == 24 and end_minute != 0:
            raise ValueError("Godzina końca 24 wymaga minut 00")
        end_minute += end_hour * 60
        if start_minute >= end_minute:
            raise ValueError("Koniec powtarzania musi być późniejszy niż początek")
        frequency = "weekly" if self.frequency.get() == "Co tydzień" else "daily"
        days = [index for index, checkbox in enumerate(self.day_checks) if checkbox.get()]
        if frequency == "weekly" and not days:
            raise ValueError("Wybierz przynajmniej jeden dzień tygodnia")
        return {
            "frequency": frequency,
            "days": days if frequency == "weekly" else [],
            "start_minute": start_minute,
            "end_minute": end_minute,
        }


class TagManagerFrame(ctk.CTkFrame):
    def __init__(self, master, on_tags_changed=None, **kwargs):
        super().__init__(master, **kwargs)
        load_tags()
        self.on_tags_changed = on_tags_changed
        self.color = COLORS[0]
        self.editing_tag_id = None
        self.rule_editors = []
        ctk.CTkLabel(self, text="Stany i tagi", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=16, pady=12)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16)
        self.entry = ctk.CTkEntry(row, placeholder_text="Nazwa stanu, np. W pracy")
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda _event: self._add())
        self.save_button = ctk.CTkButton(row, text="Dodaj tag", command=self._add)
        self.save_button.pack(side="right")
        self.cancel_button = ctk.CTkButton(row, text="Anuluj", width=70, state="disabled", command=self._cancel_edit)
        self.cancel_button.pack(side="right", padx=(0, 6))
        palette = ctk.CTkFrame(self, fg_color="transparent")
        palette.pack(anchor="w", padx=16, pady=10)
        self.swatches = []
        for color in COLORS:
            button = ctk.CTkButton(palette, text="", width=28, height=26, fg_color=_hex(color), hover_color=_hex(color), command=lambda choice=color: self._choose_color(choice))
            button.pack(side="left", padx=(0, 6))
            self.swatches.append((button, color))
        self._choose_color(self.color)
        recurrence_header = ctk.CTkFrame(self, fg_color="transparent")
        recurrence_header.pack(fill="x", padx=16, pady=(4, 2))
        ctk.CTkLabel(recurrence_header, text="Powtarzanie").pack(side="left")
        ctk.CTkButton(recurrence_header, text="Dodaj regułę", width=112, command=self._add_rule).pack(side="right")
        self.rules_container = ctk.CTkScrollableFrame(self, height=150)
        self.rules_container.pack(fill="x", padx=16, pady=(0, 8))
        self.message = ctk.CTkLabel(self, text="", anchor="w")
        self.message.pack(fill="x", padx=16)
        self.list = ctk.CTkScrollableFrame(self)
        self.list.pack(fill="both", expand=True, padx=16, pady=12)
        self._render()

    def _choose_color(self, color):
        self.color = color
        for button, choice in self.swatches:
            button.configure(border_width=2 if choice == color else 0, border_color="#ffffff")

    def _add(self):
        try:
            recurrences = [editor.to_record() for editor in self.rule_editors]
            tag = add_tag(self.entry.get(), self.color, recurrences, self.editing_tag_id)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.message.configure(text=str(error), text_color="#ef6461")
            return
        self.entry.delete(0, "end")
        was_editing = self.editing_tag_id is not None
        self.editing_tag_id = None
        self.save_button.configure(text="Dodaj tag")
        self.cancel_button.configure(state="disabled")
        self._clear_rules()
        self.message.configure(text=f"Zapisano zmiany: {tag.title}" if was_editing else f"Dodano: {tag.title}", text_color="#59c3a5")
        self._render()
        if self.on_tags_changed:
            self.on_tags_changed(tag, not was_editing)

    def _add_rule(self, rule=None):
        editor = RecurrenceRuleFrame(
            self.rules_container,
            on_remove=lambda: self._remove_rule(editor),
            rule=rule,
        )
        editor.pack(fill="x", padx=2, pady=3)
        self.rule_editors.append(editor)

    def _remove_rule(self, editor):
        if editor in self.rule_editors:
            self.rule_editors.remove(editor)
        editor.destroy()

    def _clear_rules(self):
        for editor in self.rule_editors:
            editor.destroy()
        self.rule_editors.clear()

    def _edit(self, tag_id):
        record = next((row for row in _read(TAGS_FILE) if int(row.get("id", 0)) == tag_id), None)
        if record is None:
            self.message.configure(text="Nie znaleziono tagu do edycji", text_color="#ef6461")
            return
        self.editing_tag_id = tag_id
        self.entry.delete(0, "end")
        self.entry.insert(0, record.get("title", ""))
        self.color = tuple(record.get("color", COLORS[0]))
        self._choose_color(self.color)
        self._clear_rules()
        for rule in record.get("recurrences", []):
            self._add_rule(rule)
        self.save_button.configure(text="Zapisz tag")
        self.cancel_button.configure(state="normal")
        self.message.configure(text=f"Edytujesz: {record.get('title', '')}")
        self.focus_entry()

    def _cancel_edit(self):
        self.editing_tag_id = None
        self.entry.delete(0, "end")
        self.save_button.configure(text="Dodaj tag")
        self.cancel_button.configure(state="disabled")
        self._clear_rules()
        self.color = COLORS[0]
        self._choose_color(self.color)
        self.message.configure(text="Edycja anulowana")

    def focus_entry(self):
        self.after(60, self.entry.focus_set)

    def prepare_new_tag(self):
        self.editing_tag_id = None
        self.entry.delete(0, "end")
        self.save_button.configure(text="Dodaj tag")
        self.cancel_button.configure(state="disabled")
        self._clear_rules()
        self.color = COLORS[0]
        self._choose_color(self.color)
        self.focus_entry()

    def _render(self):
        for child in self.list.winfo_children():
            child.destroy()
        for tag in datas.tags_list:
            row = ctk.CTkFrame(self.list, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text="  ", width=24, fg_color=_hex(tag.color)).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(row, text=tag.title, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="Edytuj", width=72, command=lambda tag_id=tag.id: self._edit(tag_id)).pack(side="right")


class TagCalendarFrame(ctk.CTkFrame):
    HEADER_HEIGHT = 30
    ROW_HEIGHT = 6
    TIME_WIDTH = 48

    def __init__(self, master, on_create_tag=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_create_tag = on_create_tag
        self.tags_by_name = {}
        self.tags_by_id = {}
        self.states = {}
        self.recurrence_states = {}
        self.selected_tag_id = None
        self._has_loaded_tags = False
        self._dragging = False
        self._dragged_slots = set()
        self._drag_tag_id = None
        self._drag_present = True

        ctk.CTkLabel(self, text="Kalendarz stanów", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(controls, text="Tag stanu").pack(side="left", padx=(0, 8))
        self.menu = ctk.CTkOptionMenu(controls, values=[CREATE_TAG_OPTION], command=self._select)
        self.menu.pack(side="left")
        self.message = ctk.CTkLabel(controls, text="")
        self.message.pack(side="left", padx=10)

        canvas_frame = ctk.CTkFrame(self, fg_color="transparent")
        canvas_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas = Canvas(canvas_frame, bg="#171d25", highlightthickness=0, yscrollincrement=self.ROW_HEIGHT)
        scrollbar = ctk.CTkScrollbar(canvas_frame, orientation="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._render_calendar_canvas)
        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Motion>", self._on_mouse_motion)
        self.refresh_tags()

    def refresh_tags(self):
        try:
            tags = load_tags()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.message.configure(text=f"Błąd tagów: {error}")
            return
        self.tags_by_name = {tag.title: tag for tag in tags}
        self.tags_by_id = {tag.id: tag for tag in tags}
        names = list(self.tags_by_name)
        values = names + [CREATE_TAG_OPTION]
        self.menu.configure(values=values, state="normal")
        create_tag_selected = self._has_loaded_tags and self.menu.get() == CREATE_TAG_OPTION
        if self.selected_tag_id in self.tags_by_id:
            selected = self.tags_by_id[self.selected_tag_id].title
        elif create_tag_selected or not names:
            selected = CREATE_TAG_OPTION
        else:
            selected = names[0]
        self.menu.set(selected)
        tag = self.tags_by_name.get(selected)
        self.selected_tag_id = tag.id if tag else None
        self._has_loaded_tags = True
        self._render_states()

    def _select(self, title):
        tag = self.tags_by_name.get(title)
        self.selected_tag_id = tag.id if tag else None
        if title == CREATE_TAG_OPTION:
            self.message.configure(text="Kliknij slot, aby utworzyć i przypisać tag")

    def select_tag(self, tag_id):
        tag = self.tags_by_id.get(tag_id)
        if tag:
            self.selected_tag_id = tag.id
            self.menu.set(tag.title)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_mouse_motion(self, event):
        if self._dragging:
            return
        selected_slot = self._slot_from_event(event)
        if selected_slot is None:
            return
        day, slot = selected_slot
        minute = slot * CALENDAR_SLOT_MINUTES
        time_text = f"{minute // 60:02d}:{minute % 60:02d}"
        names = [
            self.tags_by_id[tag_id].title
            for tag_id in self.states.get((day, slot), [])
            if tag_id in self.tags_by_id
        ]
        self.message.configure(text=f"{DAYS[day]} {time_text} · {', '.join(names) if names else 'Brak tagu'}")

    def _slot_from_event(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        if y < self.HEADER_HEIGHT or x < self.TIME_WIDTH:
            return None
        width = max(self.canvas.winfo_width(), self.TIME_WIDTH + 7 * 64)
        day_width = (width - self.TIME_WIDTH) / 7
        day = int((x - self.TIME_WIDTH) / day_width)
        slot = int((y - self.HEADER_HEIGHT) / self.ROW_HEIGHT)
        if not 0 <= day < 7 or not 0 <= slot < SLOTS_PER_DAY:
            return None
        return day, slot

    def _on_mouse_down(self, event):
        selected_slot = self._slot_from_event(event)
        if selected_slot is None:
            return
        day, slot = selected_slot
        if self.selected_tag_id is None:
            if self.on_create_tag:
                self.on_create_tag(day, slot)
            else:
                self.message.configure(text="Wybierz tag lub utwórz nowy")
            return
        self._dragging = True
        self._dragged_slots.clear()
        self._drag_tag_id = self.selected_tag_id
        self._drag_present = self._drag_tag_id not in self.states.get((day, slot), [])
        self._paint_drag_slot(day, slot)

    def _on_drag(self, event):
        if not self._dragging:
            return
        selected_slot = self._slot_from_event(event)
        if selected_slot is not None:
            self._paint_drag_slot(*selected_slot)

    def _on_mouse_up(self, _event):
        self._dragging = False
        self._dragged_slots.clear()

    def _paint_drag_slot(self, day, slot):
        key = (day, slot)
        if key in self._dragged_slots:
            return
        self._dragged_slots.add(key)
        self._toggle(day, slot, self._drag_tag_id, present=self._drag_present)

    def _toggle(self, day, slot, tag_id, present=None):
        try:
            self.states = toggle_calendar_slot(
                day,
                slot,
                tag_id,
                recurring_tag_ids=self.recurrence_states.get((day, slot), []),
                present=present,
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.message.configure(text=f"Błąd zapisu: {error}")
            self._render_states()
            return
        self._render_states(redraw=False)
        minute_of_day = slot * CALENDAR_SLOT_MINUTES
        time_text = f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"
        active_titles = [self.tags_by_id[value].title for value in self.states.get((day, slot), []) if value in self.tags_by_id]
        result = ", ".join(active_titles) if active_titles else "Slot wyczyszczony"
        self.message.configure(text=f"{DAYS[day]} {time_text}: {result}")
        self._draw_calendar_cell(day, slot)

    def _render_states(self, redraw=True):
        try:
            rows = _read(CALENDAR_FILE)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.message.configure(text=f"Błąd kalendarza: {error}")
            return
        manual_states = {}
        excluded_states = {}
        for row in rows:
            try:
                day = int(row["day"])
                start_minute = int(row["start_minute"])
                tag_ids = row.get("tag_ids")
                if tag_ids is None:
                    legacy_start = start_minute // LEGACY_SLOT_MINUTES * LEGACY_SLOT_MINUTES
                    first_slot = legacy_start // CALENDAR_SLOT_MINUTES
                    tag_ids = [int(row["tag_id"])]
                    slots = range(first_slot, first_slot + LEGACY_SLOT_MINUTES // CALENDAR_SLOT_MINUTES)
                else:
                    tag_ids = [int(tag_id) for tag_id in tag_ids]
                    slots = (start_minute // CALENDAR_SLOT_MINUTES,)
                excluded_tag_ids = [int(tag_id) for tag_id in row.get("excluded_tag_ids", [])]
                for saved_slot in slots:
                    if 0 <= day < 7 and 0 <= saved_slot < SLOTS_PER_DAY:
                        key = (day, saved_slot)
                        manual_states.setdefault(key, []).extend(tag_ids)
                        excluded_states.setdefault(key, []).extend(excluded_tag_ids)
            except (KeyError, TypeError, ValueError):
                continue

        try:
            self.recurrence_states = _recurring_states(_read(TAGS_FILE))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.message.configure(text=f"Błąd reguł tagów: {error}")
            self.recurrence_states = {}
        self.states = {}
        all_slots = set(manual_states) | set(excluded_states) | set(self.recurrence_states)
        for key in all_slots:
            excluded = set(excluded_states.get(key, []))
            tag_ids = list(dict.fromkeys(manual_states.get(key, []) + self.recurrence_states.get(key, [])))
            tag_ids = [tag_id for tag_id in tag_ids if tag_id not in excluded and tag_id in self.tags_by_id]
            if tag_ids:
                self.states[key] = tag_ids
        if redraw:
            self._render_calendar_canvas()

    def _render_calendar_canvas(self, _event=None):
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), self.TIME_WIDTH + 7 * 64)
        day_width = (width - self.TIME_WIDTH) / 7
        total_height = self.HEADER_HEIGHT + SLOTS_PER_DAY * self.ROW_HEIGHT
        self.canvas.configure(scrollregion=(0, 0, width, total_height))

        for day, name in enumerate(DAYS):
            x = self.TIME_WIDTH + (day + 0.5) * day_width
            self.canvas.create_text(x, self.HEADER_HEIGHT / 2, text=name, fill="#f1f5f9", font=("Segoe UI", 10, "bold"))
        self.canvas.create_line(self.TIME_WIDTH, 0, self.TIME_WIDTH, total_height, fill="#475569")

        for slot in range(SLOTS_PER_DAY):
            minute = slot * CALENDAR_SLOT_MINUTES
            y0 = self.HEADER_HEIGHT + slot * self.ROW_HEIGHT
            y1 = y0 + self.ROW_HEIGHT - 1
            if minute % 60 == 0:
                self.canvas.create_text(4, y0 + 1, text=f"{minute // 60:02d}:00", anchor="nw", fill="#cbd5e1", font=("Segoe UI", 8))
                self.canvas.create_line(0, y0, width, y0, fill="#536174")
            for day in range(7):
                self._draw_calendar_cell(day, slot, width, day_width)

        for day in range(1, 7):
            x = self.TIME_WIDTH + day * day_width
            self.canvas.create_line(x, 0, x, total_height, fill="#344050")

    def _draw_calendar_cell(self, day, slot, width=None, day_width=None):
        width = width or max(self.canvas.winfo_width(), self.TIME_WIDTH + 7 * 64)
        day_width = day_width or (width - self.TIME_WIDTH) / 7
        x0 = self.TIME_WIDTH + day * day_width
        x1 = x0 + day_width - 1
        y0 = self.HEADER_HEIGHT + slot * self.ROW_HEIGHT
        y1 = y0 + self.ROW_HEIGHT - 1
        cell_tag = f"calendar-cell-{day}-{slot}"
        self.canvas.delete(cell_tag)
        tag_ids = self.states.get((day, slot), [])
        if not tag_ids:
            minute = slot * CALENDAR_SLOT_MINUTES
            hour_shade = "#222a35" if (minute // 60) % 2 == 0 else "#1d252f"
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=hour_shade, outline="", tags=(cell_tag,))
            return
        colors = [
            self.tags_by_id[tag_id].color
            for tag_id in tag_ids
            if tag_id in self.tags_by_id
        ]
        if not colors:
            fill = "#222a35"
        else:
            base = (34, 42, 53)
            opacity = min(0.62, 0.3 + 0.1 * (len(colors) - 1))
            average_color = tuple(sum(color[channel] for color in colors) / len(colors) for channel in range(3))
            fill = _hex(tuple(
                round(base[channel] * (1 - opacity) + average_color[channel] * opacity)
                for channel in range(3)
            ))
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="", tags=(cell_tag,))
