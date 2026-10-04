from datetime import datetime, time, timedelta, date
from typing import Callable, Optional, List, Any, Dict
import threading
import customtkinter as ctk

import datas
from models.task import Task
from models.tag import Tag
from models.week_periods import WeekTime, WeeklySchedule
from optimizer.schedule_optimizer import parse_deadline_datetime


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Konwertuje kolor zapisany jako krotka RGB na format HEX."""
    if isinstance(rgb, (tuple, list)) and len(rgb) >= 3:
        return f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"
    if isinstance(rgb, str) and rgb.startswith("#"):
        return rgb
    return "#1f538d"


def _parse_task_duration_minutes(task: Task) -> int:
    """Wyodrębnia czas trwania zadania w minutach z różnych formatów."""
    task_req_time = getattr(task, "time", None)
    if isinstance(task_req_time, (int, float)):
        return max(15, int(task_req_time))
    if isinstance(task_req_time, timedelta):
        return max(15, int(task_req_time.total_seconds() // 60))
    if isinstance(task_req_time, (datetime, time)):
        return max(15, task_req_time.hour * 60 + task_req_time.minute)
    if isinstance(task_req_time, str):
        s = task_req_time.strip().lower()
        if "h" in s:
            try:
                parts = s.split("h")
                hours = float(parts[0].strip())
                minutes = float(parts[1].replace("m", "").strip()) if len(parts) > 1 and parts[1].strip() else 0
                return max(15, int(hours * 60 + minutes))
            except Exception:
                pass
        if ":" in s:
            try:
                parts = s.split(":")
                if len(parts) >= 2:
                    return max(15, int(parts[0]) * 60 + int(parts[1]))
            except Exception:
                pass
        try:
            val = float(s)
            if val <= 12:
                return max(15, int(val * 60))
            return max(15, int(val))
        except Exception:
            pass
    return 60


class TaskWidget(ctk.CTkFrame):
    """Komponent reprezentujący pojedyncze zadanie Task na kalendarzu."""

    PRIORITY_SYMBOLS = {
        4: "⚡",
        3: "🔴",
        2: "🟡",
        1: "🟢",
    }

    def __init__(
        self,
        master,
        task: Task,
        command: Optional[Callable[[Task], None]] = None,
        start_time_str: str = "",
        end_time_str: str = "",
        **kwargs,
    ):
        category_color = "#1f538d"
        if getattr(task, "tags", None) and len(task.tags) > 0:
            first_tag = task.tags[0]
            if hasattr(first_tag, "convert_color_to_hex"):
                category_color = first_tag.convert_color_to_hex(first_tag.color)
            elif hasattr(first_tag, "color") and first_tag.color:
                category_color = rgb_to_hex(first_tag.color)

        super().__init__(
            master,
            fg_color=category_color,
            corner_radius=6,
            cursor="hand2",
            border_width=1,
            border_color=("gray75", "gray30"),
            **kwargs,
        )

        self.task = task
        self.command = command

        priority = getattr(task, "priority", 1)
        symbol = self.PRIORITY_SYMBOLS.get(priority, "📌")
        title = getattr(task, "description", "Brak opisu")
        if "\n" in title:
            title = title.split("\n")[0]

        time_badge = ""
        if start_time_str and end_time_str:
            time_badge = f"{start_time_str}-{end_time_str} "

        display_text = f"{symbol} {time_badge}{title}"

        self.label = ctk.CTkLabel(
            self,
            text=display_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffffff",
            anchor="w",
            justify="left",
        )
        self.label.pack(fill="both", expand=True, padx=5, pady=2)

        self.bind("<Button-1>", self._on_click)
        self.label.bind("<Button-1>", self._on_click)

    def _on_click(self, event):
        if self.command:
            self.command(self.task)


class ScheduledMealWidget(ctk.CTkFrame):
    """Komponent reprezentujący zaplanowany posiłek na siatce kalendarza."""

    def __init__(self, master, meal_name: str, time_str: str, **kwargs):
        super().__init__(
            master,
            fg_color="#d97706",
            corner_radius=4,
            border_width=1,
            border_color="#b45309",
            **kwargs,
        )
        display_text = f"🍽️ {meal_name} ({time_str})"
        self.label = ctk.CTkLabel(
            self,
            text=display_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#ffffff",
            anchor="w",
        )
        self.label.pack(fill="both", expand=True, padx=4, pady=1)


class ScheduledActivityWidget(ctk.CTkFrame):
    """Komponent reprezentujący aktywność fizyczną na siatce kalendarza."""

    def __init__(self, master, activity_name: str, time_str: str, **kwargs):
        super().__init__(
            master,
            fg_color="#059669",
            corner_radius=4,
            border_width=1,
            border_color="#047857",
            **kwargs,
        )
        display_text = f"🏃 {activity_name} ({time_str})"
        self.label = ctk.CTkLabel(
            self,
            text=display_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#ffffff",
            anchor="w",
        )
        self.label.pack(fill="both", expand=True, padx=4, pady=1)


class AddTagToTimeDialog(ctk.CTkToplevel):
    """Okno dialogowe do przypisywania tagów do przedziałów czasu w WeeklySchedule."""

    PRESET_COLORS = [
        ("#0078d4", (0, 120, 212)),    # Niebieski
        ("#107c10", (16, 124, 16)),    # Zielony
        ("#c42b1c", (196, 43, 28)),    # Czerwony
        ("#ca5010", (202, 80, 16)),    # Pomarańczowy
        ("#7e49bc", (126, 73, 188)),   # Fioletowy
        ("#0099bc", (0, 153, 188)),    # Turkusowy
        ("#c4529d", (196, 82, 157)),   # Różowy
        ("#78716c", (120, 113, 108)),  # Szary
    ]
    DAY_LABELS = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]
    HOURS = [f"{h:02d}" for h in range(24)]
    END_HOURS = [f"{h:02d}" for h in range(25)]
    MINUTES = ["00", "15", "30", "45"]

    def __init__(
        self,
        master,
        default_day: Optional[int] = None,
        default_slot: Optional[int] = None,
        default_start_time: Optional[time] = None,
        default_end_time: Optional[time] = None,
        default_tag: Optional[Tag] = None,
        on_saved: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.title("🏷️ Przypisz tag do czasu")
        self.geometry("490x590")
        self.minsize(450, 520)
        self.attributes("-topmost", True)
        self.on_saved = on_saved
        self.selected_color = self.PRESET_COLORS[0][1]

        try:
            self.transient(master)
            master.update_idletasks()
            x = master.winfo_rootx() + (master.winfo_width() // 2) - 245
            y = master.winfo_rooty() + (master.winfo_height() // 2) - 295
            self.geometry(f"+{max(50, x)}+{max(50, y)}")
        except Exception:
            pass

        self._build_ui(default_day, default_slot, default_start_time, default_end_time, default_tag)

    def _build_ui(self, default_day, default_slot, default_start_time, default_end_time, default_tag):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(15, 10))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🏷️ Przypisz tag do czasu",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        )
        title_lbl.pack(fill="x")

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text="Zdefiniuj w jakich dniach i godzinach obowiązuje dany tag w harmonogramie.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        sub_lbl.pack(fill="x", pady=(2, 0))

        content = ctk.CTkFrame(self, fg_color=("gray95", "gray17"), corner_radius=8)
        content.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # 1. Wybór tagu
        tag_lbl = ctk.CTkLabel(content, text="Wybierz lub wpisz tag:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        tag_lbl.pack(fill="x", padx=15, pady=(12, 4))

        tag_names = [t.title for t in datas.tags_list if getattr(t, "title", "")]
        menu_values = tag_names + ["+ Nowy tag..."] if tag_names else ["+ Nowy tag..."]

        self.tag_menu = ctk.CTkOptionMenu(
            content,
            values=menu_values,
            command=self._on_tag_menu_selected,
            dynamic_resizing=False,
        )
        self.tag_menu.pack(fill="x", padx=15, pady=(0, 6))

        self.tag_entry = ctk.CTkEntry(content, placeholder_text="np. Praca, Sen, Sport, Nauka")
        self.tag_entry.pack(fill="x", padx=15, pady=(0, 8))

        # Wybór koloru
        color_row = ctk.CTkFrame(content, fg_color="transparent")
        color_row.pack(fill="x", padx=15, pady=(0, 10))
        ctk.CTkLabel(color_row, text="Kolor tagu:", font=ctk.CTkFont(size=11), text_color="gray").pack(side="left", padx=(0, 8))

        self.color_btns = []
        for hex_col, rgb_col in self.PRESET_COLORS:
            btn = ctk.CTkButton(
                color_row,
                text="",
                width=24,
                height=24,
                fg_color=hex_col,
                hover_color=hex_col,
                corner_radius=12,
                border_width=0,
                command=lambda hc=hex_col, rc=rgb_col: self._select_color(hc, rc),
            )
            btn.pack(side="left", padx=3)
            self.color_btns.append((btn, hex_col, rgb_col))

        # 2. Dni tygodnia
        days_header = ctk.CTkFrame(content, fg_color="transparent")
        days_header.pack(fill="x", padx=15, pady=(6, 4))
        ctk.CTkLabel(days_header, text="Dni tygodnia:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(side="left")

        quick_box = ctk.CTkFrame(days_header, fg_color="transparent")
        quick_box.pack(side="right")
        ctk.CTkButton(quick_box, text="Pn-Pt", width=45, height=22, font=ctk.CTkFont(size=10), command=self._select_workdays).pack(side="left", padx=2)
        ctk.CTkButton(quick_box, text="Tydzień", width=50, height=22, font=ctk.CTkFont(size=10), command=self._select_all_days).pack(side="left", padx=2)
        ctk.CTkButton(quick_box, text="Wyczyść", width=50, height=22, font=ctk.CTkFont(size=10), command=self._clear_days).pack(side="left", padx=2)

        days_box = ctk.CTkFrame(content, fg_color="transparent")
        days_box.pack(fill="x", padx=15, pady=(0, 10))
        self.day_checkboxes: List[ctk.CTkCheckBox] = []

        default_days_set = {default_day} if default_day is not None else {0, 1, 2, 3, 4}

        for i, label in enumerate(self.DAY_LABELS):
            cb = ctk.CTkCheckBox(days_box, text=label, width=46, checkbox_width=18, checkbox_height=18)
            cb.pack(side="left", padx=3)
            if i in default_days_set:
                cb.select()
            self.day_checkboxes.append(cb)

        # 3. Godziny
        time_lbl = ctk.CTkLabel(content, text="Przedział godzinowy:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        time_lbl.pack(fill="x", padx=15, pady=(6, 4))

        time_box = ctk.CTkFrame(content, fg_color="transparent")
        time_box.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(time_box, text="Od:").pack(side="left", padx=(0, 4))
        self.start_h = ctk.CTkOptionMenu(time_box, values=self.HOURS, width=58)
        self.start_h.pack(side="left")
        ctk.CTkLabel(time_box, text=":").pack(side="left", padx=2)
        self.start_m = ctk.CTkOptionMenu(time_box, values=self.MINUTES, width=58)
        self.start_m.pack(side="left", padx=(0, 15))

        ctk.CTkLabel(time_box, text="Do:").pack(side="left", padx=(0, 4))
        self.end_h = ctk.CTkOptionMenu(time_box, values=self.END_HOURS, width=58)
        self.end_h.pack(side="left")
        ctk.CTkLabel(time_box, text=":").pack(side="left", padx=2)
        self.end_m = ctk.CTkOptionMenu(time_box, values=self.MINUTES, width=58)
        self.end_m.pack(side="left")

        if default_start_time is not None and default_end_time is not None:
            self.start_h.set(f"{default_start_time.hour:02d}")
            self.start_m.set(f"{(default_start_time.minute // 15) * 15:02d}")
            end_hour_val = 24 if default_end_time == time(0, 0) else default_end_time.hour
            self.end_h.set(f"{end_hour_val:02d}")
            self.end_m.set(f"{(default_end_time.minute // 15) * 15:02d}")
        elif default_slot is not None:
            start_min = getattr(self.master, "start_hour", 6) * 60 + default_slot * 15
            end_min = min(24 * 60, start_min + 60)
            self.start_h.set(f"{start_min // 60:02d}")
            self.start_m.set(f"{start_min % 60:02d}")
            self.end_h.set(f"{end_min // 60:02d}")
            self.end_m.set(f"{end_min % 60:02d}")
        else:
            self.start_h.set("09")
            self.start_m.set("00")
            self.end_h.set("17")
            self.end_m.set("00")

        if default_tag is not None:
            self.tag_menu.set(default_tag.title)
            self.tag_entry.delete(0, "end")
            self.tag_entry.insert(0, default_tag.title)
            if hasattr(default_tag, "color") and default_tag.color:
                self._select_color(rgb_to_hex(default_tag.color), tuple(default_tag.color))
        elif tag_names:
            first_tag = datas.tags_list[0]
            self.tag_menu.set(first_tag.title)
            self.tag_entry.delete(0, "end")
            self.tag_entry.insert(0, first_tag.title)
            if hasattr(first_tag, "color") and first_tag.color:
                self._select_color(rgb_to_hex(first_tag.color), tuple(first_tag.color))
        else:
            self.tag_menu.set("+ Nowy tag...")
            self.tag_entry.insert(0, "Praca")
            self._select_color(self.PRESET_COLORS[0][0], self.PRESET_COLORS[0][1])

        self.status_lbl = ctk.CTkLabel(content, text="", font=ctk.CTkFont(size=11), text_color="red")
        self.status_lbl.pack(fill="x", padx=15, pady=(4, 6))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(0, 15))

        self.save_btn = ctk.CTkButton(
            btn_frame,
            text="💾 Przypisz tag",
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._save_tag,
        )
        self.save_btn.pack(side="left", padx=4, expand=True, fill="x")

        self.remove_btn = ctk.CTkButton(
            btn_frame,
            text="🗑️ Usuń z tego czasu",
            fg_color="#c62828",
            hover_color="#8e0000",
            font=ctk.CTkFont(size=12),
            command=self._remove_tag,
        )
        self.remove_btn.pack(side="left", padx=4, expand=True, fill="x")

        self.cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Anuluj",
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            command=self.destroy,
        )
        self.cancel_btn.pack(side="left", padx=4)

    def _select_color(self, hex_col, rgb_col):
        self.selected_color = tuple(rgb_col)
        for btn, h_c, r_c in self.color_btns:
            if h_c.lower() == hex_col.lower():
                btn.configure(border_width=2, border_color="#ffffff")
            else:
                btn.configure(border_width=0)

    def _on_tag_menu_selected(self, choice: str):
        if choice == "+ Nowy tag...":
            self.tag_entry.delete(0, "end")
            self.tag_entry.focus()
        else:
            self.tag_entry.delete(0, "end")
            self.tag_entry.insert(0, choice)
            for t in datas.tags_list:
                if t.title == choice:
                    if hasattr(t, "color") and t.color:
                        self._select_color(rgb_to_hex(t.color), tuple(t.color))
                    break

    def _select_workdays(self):
        for i, cb in enumerate(self.day_checkboxes):
            if i < 5:
                cb.select()
            else:
                cb.deselect()

    def _select_all_days(self):
        for cb in self.day_checkboxes:
            cb.select()

    def _clear_days(self):
        for cb in self.day_checkboxes:
            cb.deselect()

    def _save_tag(self):
        title = self.tag_entry.get().strip()
        if not title:
            self.status_lbl.configure(text="Podaj nazwę tagu!", text_color="red")
            return

        selected_days = [i for i, cb in enumerate(self.day_checkboxes) if cb.get()]
        if not selected_days:
            self.status_lbl.configure(text="Wybierz przynajmniej jeden dzień!", text_color="red")
            return

        sh = int(self.start_h.get())
        sm = int(self.start_m.get())
        eh = int(self.end_h.get())
        em = int(self.end_m.get())

        if eh == 24 and em > 0:
            self.status_lbl.configure(text="Dla godziny 24 minuty muszą wynosić 00!", text_color="red")
            return

        s_min = sh * 60 + sm
        e_min = eh * 60 + em
        if e_min <= s_min:
            self.status_lbl.configure(text="Godzina końca musi być późniejsza niż początku!", text_color="red")
            return

        target_tag = None
        for t in datas.tags_list:
            if t.title.strip().lower() == title.lower():
                target_tag = t
                break

        if target_tag is None:
            max_id = max((t.id for t in datas.tags_list), default=0)
            target_tag = Tag(
                id=max_id + 1,
                title=title,
                color=self.selected_color,
                is_interactive=True,
            )
            datas.tags_list.append(target_tag)
            datas.save_tags_list_to_json(datas.tags_list, "tags.json")

        if not datas.weekly_schedule_list:
            datas.weekly_schedule_list.append(WeeklySchedule())
        ws = datas.weekly_schedule_list[0]

        start_t = time(sh, sm)
        end_t = time(0, 0) if eh == 24 else time(eh, em)

        ws.assign(selected_days, start_t, end_t, target_tag)
        datas.save_weekly_schedule_list_to_json(datas.weekly_schedule_list, "week_time.json")

        if self.on_saved:
            self.on_saved()

        self.destroy()

    def _remove_tag(self):
        title = self.tag_entry.get().strip()
        if not title:
            self.status_lbl.configure(text="Podaj nazwę tagu do usunięcia!", text_color="red")
            return

        selected_days = [i for i, cb in enumerate(self.day_checkboxes) if cb.get()]
        if not selected_days:
            self.status_lbl.configure(text="Wybierz dni, z których chcesz usunąć tag!", text_color="red")
            return

        sh = int(self.start_h.get())
        sm = int(self.start_m.get())
        eh = int(self.end_h.get())
        em = int(self.end_m.get())

        if eh == 24 and em > 0:
            self.status_lbl.configure(text="Dla godziny 24 minuty muszą wynosić 00!", text_color="red")
            return
        if (eh * 60 + em) <= (sh * 60 + sm):
            self.status_lbl.configure(text="Godzina końca musi być późniejsza niż początku!", text_color="red")
            return

        target_tag = None
        for t in datas.tags_list:
            if t.title.strip().lower() == title.lower():
                target_tag = t
                break

        if target_tag is None:
            self.status_lbl.configure(text=f"Tag '{title}' nie istnieje na liście!", text_color="orange")
            return

        if datas.weekly_schedule_list:
            ws = datas.weekly_schedule_list[0]
            start_t = time(sh, sm)
            end_t = time(0, 0) if eh == 24 else time(eh, em)
            ws.unassign(selected_days, start_t, end_t, target_tag)
            datas.save_weekly_schedule_list_to_json(datas.weekly_schedule_list, "week_time.json")

        if self.on_saved:
            self.on_saved()

        self.destroy()


class CalendarFrame(ctk.CTkFrame):
    """
    Zaawansowany widget kalendarza tygodniowego i dziennego
    z przyciskiem automatycznej optymalizacji harmonogramu zadań (Organize My Tasks).
    """

    DAYS_OF_WEEK = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]

    def __init__(
        self,
        master,
        is_weekly_view: bool = True,
        target_date: Optional[datetime] = None,
        start_hour: int = 6,
        end_hour: int = 23,
        command: Optional[Callable[[Task], None]] = None,
        on_schedule_updated: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)

        self.start_hour = start_hour
        self.end_hour = end_hour
        self.command = command or self._default_task_click
        self.on_schedule_updated = on_schedule_updated
        self.is_weekly_view = is_weekly_view

        self.target_date = target_date if target_date else datetime.now()

        self.days_to_render = list(range(7)) if self.is_weekly_view else [self.target_date.weekday()]
        self.col_count = len(self.days_to_render)

        self.total_intervals = (end_hour - start_hour) * 4
        self.task_widgets: List[ctk.CTkFrame] = []
        self.hint_widgets: List[ctk.CTkFrame] = []
        self.last_optimization_result = None
        self.last_optimization_monday = None

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_toolbar()
        self._build_header()
        self._build_grid()

        self.refresh()

    def _build_toolbar(self):
        """Tworzy pasek narzędziowy kalendarza z przyciskiem optymalizacji."""
        self.toolbar = ctk.CTkFrame(self, fg_color=("gray90", "gray16"), corner_radius=8)
        self.toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 5))

        # Lewa strona paska: Przełącznik widoku i nawigacja
        left_box = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        left_box.pack(side="left", padx=10, pady=6)

        self.view_segmented = ctk.CTkSegmentedButton(
            left_box,
            values=["Tydzień", "Dzień"],
            command=self._on_view_change,
        )
        self.view_segmented.set("Tydzień" if self.is_weekly_view else "Dzień")
        self.view_segmented.pack(side="left", padx=(0, 10))

        self.prev_btn = ctk.CTkButton(left_box, text="◀", width=32, command=self._prev_period)
        self.prev_btn.pack(side="left", padx=2)

        self.today_btn = ctk.CTkButton(left_box, text="Dziś", width=55, command=self._go_to_today)
        self.today_btn.pack(side="left", padx=2)

        self.next_btn = ctk.CTkButton(left_box, text="▶", width=32, command=self._next_period)
        self.next_btn.pack(side="left", padx=2)

        self.date_label = ctk.CTkLabel(
            left_box,
            text=self._get_period_label(),
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.date_label.pack(side="left", padx=(12, 5))

        # Prawa strona paska: Przycisk Organize My Tasks i status
        right_box = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        right_box.pack(side="right", padx=10, pady=6)

        self.status_label = ctk.CTkLabel(
            right_box,
            text="Gotowy do optymalizacji",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.status_label.pack(side="left", padx=(0, 12))

        self.add_tag_time_btn = ctk.CTkButton(
            right_box,
            text="🏷️ Dodaj tag do czasu",
            width=135,
            fg_color="#1f538d",
            hover_color="#14375e",
            command=self.open_add_tag_to_time_dialog,
        )
        self.add_tag_time_btn.pack(side="left", padx=(0, 8))

        self.refresh_btn = ctk.CTkButton(
            right_box,
            text="⟳ Odśwież",
            width=80,
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray38"),
            command=self.refresh,
        )
        self.refresh_btn.pack(side="left", padx=(0, 8))

        self.organize_btn = ctk.CTkButton(
            right_box,
            text="⚡ Organize My Tasks",
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.organize_tasks,
        )
        self.organize_btn.pack(side="left")

    def _get_period_label(self) -> str:
        """Zwraca tekst etykiety aktualnego okresu (tydzień lub dzień)."""
        if self.is_weekly_view:
            mon = self.target_date - timedelta(days=self.target_date.weekday())
            sun = mon + timedelta(days=6)
            return f"Tydzień: {mon.strftime('%d.%m')} - {sun.strftime('%d.%m.%Y')}"
        else:
            day_name = self.DAYS_OF_WEEK[self.target_date.weekday()]
            return f"{day_name}, {self.target_date.strftime('%d.%m.%Y')}"

    def _update_period_label(self):
        self.date_label.configure(text=self._get_period_label())

    def _on_view_change(self, value: str):
        self.is_weekly_view = (value == "Tydzień")
        self.days_to_render = list(range(7)) if self.is_weekly_view else [self.target_date.weekday()]
        self.col_count = len(self.days_to_render)
        self._update_period_label()
        self._rebuild_grid_and_header()

    def _prev_period(self):
        step = timedelta(days=7 if self.is_weekly_view else 1)
        self.target_date -= step
        self.days_to_render = list(range(7)) if self.is_weekly_view else [self.target_date.weekday()]
        self._update_period_label()
        self._rebuild_grid_and_header()

    def _next_period(self):
        step = timedelta(days=7 if self.is_weekly_view else 1)
        self.target_date += step
        self.days_to_render = list(range(7)) if self.is_weekly_view else [self.target_date.weekday()]
        self._update_period_label()
        self._rebuild_grid_and_header()

    def _go_to_today(self):
        self.target_date = datetime.now()
        self.days_to_render = list(range(7)) if self.is_weekly_view else [self.target_date.weekday()]
        self._update_period_label()
        self._rebuild_grid_and_header()

    def _rebuild_grid_and_header(self):
        self.header_frame.destroy()
        self.scroll_frame.destroy()
        self._build_header()
        self._build_grid()
        self.refresh()

    def _build_header(self):
        """Tworzy nagłówek kolumn z nazwami i datami dni."""
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=1, column=0, sticky="ew", padx=(65, 20), pady=(5, 5))

        mon = self.target_date - timedelta(days=self.target_date.weekday())
        for idx, day_idx in enumerate(self.days_to_render):
            self.header_frame.grid_columnconfigure(idx, weight=1)

            day_dt = mon + timedelta(days=day_idx)
            header_text = f"{self.DAYS_OF_WEEK[day_idx]}\n{day_dt.strftime('%d.%m')}"

            lbl = ctk.CTkLabel(
                self.header_frame,
                text=header_text,
                font=ctk.CTkFont(size=12, weight="bold"),
                justify="center",
            )
            lbl.grid(row=0, column=idx, sticky="ew", padx=2)

    def _build_grid(self):
        """Tworzy siatkę 15-minutową wewnątrz scrollowalnego kontenera."""
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=(0, 5))

        self.scroll_frame.grid_columnconfigure(0, minsize=55)
        for col in range(1, self.col_count + 1):
            self.scroll_frame.grid_columnconfigure(col, weight=1, minsize=100)

        for slot in range(self.total_intervals):
            total_minutes = self.start_hour * 60 + (slot * 15)
            hour = total_minutes // 60
            minute = total_minutes % 60

            time_str = f"{hour:02d}:{minute:02d}"
            time_lbl = ctk.CTkLabel(
                self.scroll_frame,
                text=time_str if minute % 30 == 0 else "∙",
                font=ctk.CTkFont(size=10),
                text_color="gray",
            )
            time_lbl.grid(row=slot, column=0, sticky="n", pady=1)

            for idx in range(self.col_count):
                day_for_col = self.days_to_render[idx]
                cell_bg = ctk.CTkFrame(
                    self.scroll_frame,
                    fg_color=("gray85", "gray20") if slot % 2 == 0 else ("gray90", "gray17"),
                    height=24,
                    corner_radius=1,
                    cursor="hand2",
                )
                cell_bg.grid(row=slot, column=idx + 1, sticky="nsew", padx=1, pady=1)
                cell_bg.bind(
                    "<Button-1>",
                    lambda e, d=day_for_col, s=slot: self.open_add_tag_to_time_dialog(default_day=d, default_slot=s),
                )

    def refresh(self):
        """Czyści i ponownie renderuje wskazówki tła, zadania oraz posiłki i aktywności."""
        for w in self.task_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self.task_widgets.clear()

        for h in self.hint_widgets:
            try:
                h.destroy()
            except Exception:
                pass
        self.hint_widgets.clear()

        if datas.weekly_schedule_list:
            self._render_schedule_hints(datas.weekly_schedule_list[0])

        current_monday = self.target_date.date() - timedelta(days=self.target_date.weekday())
        is_same_opt_week = (
            self.last_optimization_monday is None or self.last_optimization_monday == current_monday
        )
        if self.last_optimization_result is not None and is_same_opt_week:
            self._render_optimization_items(self.last_optimization_result)
        else:
            self._render_tasks(datas.current_tasks_list)
            self._render_saved_meals_and_trainings()

    def _render_schedule_hints(self, schedule: Optional[WeekTime]):
        """Renderuje paski tagów tła (np. godziny pracy/snu/nauki)."""
        if not schedule or not hasattr(schedule, "tags"):
            return

        cal_start_min = self.start_hour * 60
        cal_end_min = self.end_hour * 60

        for tag in schedule.tags():
            if hasattr(tag, "convert_color_to_hex"):
                color_hex = tag.convert_color_to_hex(tag.color)
            elif hasattr(tag, "color") and tag.color:
                color_hex = rgb_to_hex(tag.color)
            else:
                color_hex = "#1f538d"

            for interval in schedule.intervals_for(tag):
                if not self.is_weekly_view and interval.day != self.target_date.weekday():
                    continue

                start_min = int(interval.start.total_seconds() // 60)
                end_min = int(interval.end.total_seconds() // 60)

                if end_min <= cal_start_min or start_min >= cal_end_min:
                    continue

                visible_start = max(start_min, cal_start_min)
                visible_end = min(end_min, cal_end_min)

                row_start = (visible_start - cal_start_min) // 15
                row_end = (visible_end - cal_start_min) // 15
                row_span = max(1, min(self.total_intervals - row_start, row_end - row_start))

                col_index = (interval.day + 1) if self.is_weekly_view else 1

                hint_strip = ctk.CTkFrame(
                    self.scroll_frame,
                    fg_color=color_hex,
                    width=6,
                    corner_radius=2,
                    cursor="hand2",
                )
                hint_strip.grid(
                    row=row_start,
                    column=col_index,
                    rowspan=row_span,
                    sticky="nsw",
                    padx=(2, 0),
                    pady=1,
                )
                st_time = interval.start_time
                et_dt = datetime.min + interval.end
                et_time = et_dt.time() if interval.end < timedelta(days=1) else time(0, 0)
                hint_strip.bind(
                    "<Button-1>",
                    lambda e, t=tag, d=interval.day, st=st_time, et=et_time: self.open_add_tag_to_time_dialog(
                        default_day=d, default_start_time=st, default_end_time=et, default_tag=t
                    ),
                )
                self.hint_widgets.append(hint_strip)

    def _render_tasks(self, tasks: List[Task]):
        """Renderuje zadania z datas.current_tasks_list na siatce."""
        cal_start_min = self.start_hour * 60
        cal_end_min = self.end_hour * 60

        mon = self.target_date.date() - timedelta(days=self.target_date.weekday())
        sun = mon + timedelta(days=6)

        for task in tasks:
            start_time = getattr(task, "assigned_time", None) or getattr(task, "start", None)
            if start_time is None:
                continue

            if isinstance(start_time, str):
                start_time = parse_deadline_datetime(start_time)

            if not isinstance(start_time, (datetime, date)):
                continue

            task_date = start_time.date() if isinstance(start_time, datetime) else start_time
            task_day = start_time.weekday()

            if self.is_weekly_view:
                if isinstance(start_time, datetime) and not (mon <= task_date <= sun):
                    continue
            else:
                if isinstance(start_time, datetime) and task_date != self.target_date.date():
                    continue

            start_min = start_time.hour * 60 + start_time.minute if isinstance(start_time, datetime) else 9 * 60
            if start_min < cal_start_min or start_min >= cal_end_min:
                continue

            row_start = (start_min - cal_start_min) // 15
            duration_minutes = _parse_task_duration_minutes(task)
            row_span = max(1, min(self.total_intervals - row_start, duration_minutes // 15))

            col_index = (task_day + 1) if self.is_weekly_view else 1

            end_min = start_min + duration_minutes
            start_str = f"{start_time.hour:02d}:{start_time.minute:02d}" if isinstance(start_time, datetime) else "09:00"
            end_str = f"{(end_min // 60) % 24:02d}:{end_min % 60:02d}"

            widget = TaskWidget(
                master=self.scroll_frame,
                task=task,
                command=self.command,
                start_time_str=start_str,
                end_time_str=end_str,
            )
            widget.grid(
                row=row_start,
                column=col_index,
                rowspan=row_span,
                sticky="nsew",
                padx=(10, 2),
                pady=1,
            )
            self.task_widgets.append(widget)

    def _render_optimization_items(self, opt_result):
        """Renderuje zadania, posiłki oraz aktywności z wyniku optymalizacji."""
        cal_start_min = self.start_hour * 60
        cal_end_min = self.end_hour * 60

        # 1. Render tasks
        for st in opt_result.best_schedule.assignments:
            if not self.is_weekly_view and st.day != self.target_date.weekday():
                continue

            start_min = st.start_time.hour * 60 + st.start_time.minute
            if start_min < cal_start_min or start_min >= cal_end_min:
                continue

            row_start = (start_min - cal_start_min) // 15
            row_span = max(1, min(self.total_intervals - row_start, st.duration_minutes // 15))
            col_index = (st.day + 1) if self.is_weekly_view else 1

            start_str = f"{st.start_time.hour:02d}:{st.start_time.minute:02d}"
            end_str = f"{st.end_time.hour:02d}:{st.end_time.minute:02d}"

            widget = TaskWidget(
                master=self.scroll_frame,
                task=st.task,
                command=self.command,
                start_time_str=start_str,
                end_time_str=end_str,
            )
            widget.grid(
                row=row_start,
                column=col_index,
                rowspan=row_span,
                sticky="nsew",
                padx=(10, 2),
                pady=1,
            )
            self.task_widgets.append(widget)

        # 2. Render meals
        for meal in opt_result.best_schedule.meals:
            if not self.is_weekly_view and meal.day != self.target_date.weekday():
                continue

            start_min = meal.start_time.hour * 60 + meal.start_time.minute
            if start_min < cal_start_min or start_min >= cal_end_min:
                continue

            row_start = (start_min - cal_start_min) // 15
            row_span = max(1, min(self.total_intervals - row_start, meal.duration_minutes // 15))
            col_index = (meal.day + 1) if self.is_weekly_view else 1

            start_str = f"{meal.start_time.hour:02d}:{meal.start_time.minute:02d}"
            end_str = f"{meal.end_time.hour:02d}:{meal.end_time.minute:02d}"

            meal_widget = ScheduledMealWidget(
                self.scroll_frame,
                meal_name=meal.name,
                time_str=f"{start_str}-{end_str}",
            )
            meal_widget.grid(
                row=row_start,
                column=col_index,
                rowspan=row_span,
                sticky="nsew",
                padx=(10, 2),
                pady=1,
            )
            self.task_widgets.append(meal_widget)

        # 3. Render physical activities
        for act in opt_result.best_schedule.activities:
            if not self.is_weekly_view and act.day != self.target_date.weekday():
                continue

            start_min = act.start_time.hour * 60 + act.start_time.minute
            if start_min < cal_start_min or start_min >= cal_end_min:
                continue

            row_start = (start_min - cal_start_min) // 15
            row_span = max(1, min(self.total_intervals - row_start, act.duration_minutes // 15))
            col_index = (act.day + 1) if self.is_weekly_view else 1

            start_str = f"{act.start_time.hour:02d}:{act.start_time.minute:02d}"
            end_str = f"{act.end_time.hour:02d}:{act.end_time.minute:02d}"

            act_widget = ScheduledActivityWidget(
                self.scroll_frame,
                activity_name=act.name,
                time_str=f"{start_str}-{end_str}",
            )
            act_widget.grid(
                row=row_start,
                column=col_index,
                rowspan=row_span,
                sticky="nsew",
                padx=(10, 2),
                pady=1,
            )
            self.task_widgets.append(act_widget)

    def organize_tasks(self):
        """
        Główna akcja 'Organize My Tasks':
        uruchamia algorytm optymalizacji w osobnym wątku i aktualizuje siatkę kalendarza.
        """
        active_tasks = [t for t in datas.current_tasks_list]
        if not active_tasks:
            self.status_label.configure(
                text="Brak zadań do optymalizacji! Dodaj zadania w formularzu.",
                text_color="orange",
            )
            return

        self.status_label.configure(
            text="Optymalizowanie harmonogramu zadań...",
            text_color="white",
        )
        self.organize_btn.configure(
            state="disabled",
            text="Optymalizowanie...",
        )

        result_container: Dict[str, Any] = {"done": False, "result": None, "error": None}

        # Reference Monday for the target week
        monday_dt = datetime.combine(
            self.target_date.date() - timedelta(days=self.target_date.weekday()),
            time.min,
        )

        now_dt = datetime.now()
        week_end = monday_dt + timedelta(days=6, hours=23, minutes=59)
        if week_end < now_dt:
            self.status_label.configure(
                text="Nie można planować w przeszłości! Przejdź do bieżącego lub przyszłego tygodnia ▶",
                text_color="orange",
            )
            self.organize_btn.configure(
                state="normal",
                text="⚡ Organize My Tasks",
            )
            return

        min_schedule_dt = now_dt if monday_dt <= now_dt else monday_dt

        def worker():
            try:
                from optimizer import optimize_schedule, OptimizationConfig

                ws = datas.weekly_schedule_list[0] if datas.weekly_schedule_list else WeeklySchedule()
                curve = [0.5] * 96

                cfg = OptimizationConfig(
                    reference_date=monday_dt,
                    min_schedule_datetime=min_schedule_dt,
                    earliest_task_time=time(self.start_hour, 0),
                    latest_task_time=time(self.end_hour, 0),
                    population_size=25,
                    max_generations=25,
                    enable_meals=True,
                    enable_physical_activity=True,
                    random_seed=42,
                )

                tasks_copy = list(active_tasks)
                opt_result = optimize_schedule(
                    scoring_functions=None,
                    task_list=tasks_copy,
                    weekly_schedule=ws,
                    productivity_curve_data=curve,
                    config=cfg,
                )
                result_container["result"] = opt_result
            except Exception as e:
                import traceback
                traceback.print_exc()
                result_container["error"] = str(e)
            finally:
                result_container["done"] = True

        threading.Thread(target=worker, daemon=True).start()

        def check_completion():
            if result_container["done"]:
                self.organize_btn.configure(
                    state="normal",
                    text="⚡ Organize My Tasks",
                )
                if result_container["error"]:
                    self.status_label.configure(
                        text=f"Błąd: {result_container['error']}",
                        text_color="red",
                    )
                else:
                    opt_res = result_container["result"]
                    assigned_count = len(opt_res.best_schedule.assignments)
                    unassigned_count = len(opt_res.best_schedule.unassigned_tasks)

                    # Zapis przypisanych czasów do obiektów Task
                    for st in opt_res.best_schedule.assignments:
                        assigned_dt = monday_dt + timedelta(
                            days=st.day,
                            hours=st.start_time.hour,
                            minutes=st.start_time.minute,
                        )
                        st.task.assigned_time = assigned_dt
                        st.task.start = assigned_dt

                    datas.save_current_tasks_list_to_json(datas.current_tasks_list)

                    # Zapis posiłków do pliku i listy datas
                    datas.scheduled_meals_list.clear()
                    for meal in opt_res.best_schedule.meals:
                        meal_dt = monday_dt + timedelta(
                            days=meal.day,
                            hours=meal.start_time.hour,
                            minutes=meal.start_time.minute,
                        )
                        meal.datetime = meal_dt
                        meal.start_datetime = meal_dt
                        meal.end_datetime = meal_dt + timedelta(minutes=meal.duration_minutes)
                        datas.scheduled_meals_list.append(meal)
                    datas.save_scheduled_meals_to_json(datas.scheduled_meals_list, "meals.json")

                    # Zapis treningów do pliku i listy datas
                    datas.trainings_list.clear()
                    for act in opt_res.best_schedule.activities:
                        act_dt = monday_dt + timedelta(
                            days=act.day,
                            hours=act.start_time.hour,
                            minutes=act.start_time.minute,
                        )
                        act.datetime = act_dt
                        act.start_datetime = act_dt
                        act.end_datetime = act_dt + timedelta(minutes=act.duration_minutes)
                        datas.trainings_list.append(act)
                    datas.save_trainings_to_json(datas.trainings_list, "trainings.json")

                    self.last_optimization_result = opt_res
                    self.last_optimization_monday = monday_dt.date()
                    self.refresh()

                    status_msg = f"✓ Zaplanowano {assigned_count} zadań (Wynik: {opt_res.best_score:.1f})"
                    if unassigned_count > 0:
                        status_msg += f", brak miejsca: {unassigned_count}"
                    self.status_label.configure(text=status_msg, text_color="#4caf50")

                    if self.on_schedule_updated:
                        self.on_schedule_updated()
            else:
                self.after(100, check_completion)

        self.after(100, check_completion)

    def _render_saved_meals_and_trainings(self):
        """Renderuje zapisane posiłki i treningi z plików/list datas na siatce kalendarza."""
        cal_start_min = self.start_hour * 60
        cal_end_min = self.end_hour * 60

        mon = self.target_date.date() - timedelta(days=self.target_date.weekday())
        sun = mon + timedelta(days=6)

        # 1. Posiłki
        for meal in datas.scheduled_meals_list:
            meal_dt = getattr(meal, "start_datetime", getattr(meal, "datetime", None))
            if isinstance(meal_dt, datetime):
                meal_date = meal_dt.date()
                if self.is_weekly_view:
                    if not (mon <= meal_date <= sun):
                        continue
                else:
                    if meal_date != self.target_date.date():
                        continue
                day_idx = meal_dt.weekday()
                start_min = meal_dt.hour * 60 + meal_dt.minute
            else:
                day_idx = getattr(meal, "day", 0)
                if not self.is_weekly_view and day_idx != self.target_date.weekday():
                    continue
                start_t = getattr(meal, "start_time", time(12, 0))
                start_min = start_t.hour * 60 + start_t.minute

            if start_min < cal_start_min or start_min >= cal_end_min:
                continue

            duration = getattr(meal, "duration_minutes", 30)
            row_start = (start_min - cal_start_min) // 15
            row_span = max(1, min(self.total_intervals - row_start, duration // 15))
            col_index = (day_idx + 1) if self.is_weekly_view else 1

            end_min = start_min + duration
            start_str = f"{start_min // 60:02d}:{start_min % 60:02d}"
            end_str = f"{(end_min // 60) % 24:02d}:{end_min % 60:02d}"

            meal_widget = ScheduledMealWidget(
                self.scroll_frame,
                meal_name=getattr(meal, "name", "Posiłek"),
                time_str=f"{start_str}-{end_str}",
            )
            meal_widget.grid(
                row=row_start,
                column=col_index,
                rowspan=row_span,
                sticky="nsew",
                padx=(10, 2),
                pady=1,
            )
            self.task_widgets.append(meal_widget)

        # 2. Treningi
        for act in datas.trainings_list:
            act_dt = getattr(act, "start_datetime", getattr(act, "datetime", None))
            if isinstance(act_dt, datetime):
                act_date = act_dt.date()
                if self.is_weekly_view:
                    if not (mon <= act_date <= sun):
                        continue
                else:
                    if act_date != self.target_date.date():
                        continue
                day_idx = act_dt.weekday()
                start_min = act_dt.hour * 60 + act_dt.minute
            else:
                day_idx = getattr(act, "day", 0)
                if not self.is_weekly_view and day_idx != self.target_date.weekday():
                    continue
                start_t = getattr(act, "start_time", time(8, 0))
                start_min = start_t.hour * 60 + start_t.minute

            if start_min < cal_start_min or start_min >= cal_end_min:
                continue

            duration = getattr(act, "duration_minutes", 60)
            row_start = (start_min - cal_start_min) // 15
            row_span = max(1, min(self.total_intervals - row_start, duration // 15))
            col_index = (day_idx + 1) if self.is_weekly_view else 1

            end_min = start_min + duration
            start_str = f"{start_min // 60:02d}:{start_min % 60:02d}"
            end_str = f"{(end_min // 60) % 24:02d}:{end_min % 60:02d}"

            act_widget = ScheduledActivityWidget(
                self.scroll_frame,
                activity_name=getattr(act, "name", "Trening"),
                time_str=f"{start_str}-{end_str}",
            )
            act_widget.grid(
                row=row_start,
                column=col_index,
                rowspan=row_span,
                sticky="nsew",
                padx=(10, 2),
                pady=1,
            )
            self.task_widgets.append(act_widget)

    def open_add_tag_to_time_dialog(
        self,
        default_day: Optional[int] = None,
        default_slot: Optional[int] = None,
        default_start_time: Optional[time] = None,
        default_end_time: Optional[time] = None,
        default_tag: Optional[Tag] = None,
    ):
        """Otwiera okno dialogowe przypisywania tagu do czasu w harmonogramie."""
        if default_day is None:
            default_day = self.target_date.weekday()

        dialog = AddTagToTimeDialog(
            master=self,
            default_day=default_day,
            default_slot=default_slot,
            default_start_time=default_start_time,
            default_end_time=default_end_time,
            default_tag=default_tag,
            on_saved=self._on_schedule_tag_saved,
        )
        dialog.focus()

    def _on_schedule_tag_saved(self):
        """Wywoływane po zapisaniu lub usunięciu tagu w harmonogramie."""
        self.refresh()
        self.status_label.configure(text="✓ Zaktualizowano tagi w harmonogramie", text_color="#4caf50")
        if self.on_schedule_updated:
            self.on_schedule_updated()

    def _default_task_click(self, task: Task):
        """Domyślne okienko szczegółów po kliknięciu w zadanie na kalendarzu."""
        top = ctk.CTkToplevel(self)
        top.title(f"Szczegóły zadania: #{getattr(task, 'id', '')}")
        top.geometry("450x380")
        top.attributes("-topmost", True)

        desc = getattr(task, "description", "Brak opisu")
        priority = getattr(task, "priority", 1)
        priority_map = {4: "⚡ Krytyczny (4)", 3: "🔴 Wysoki (3)", 2: "🟡 Średni (2)", 1: "🟢 Niski (1)"}
        priority_str = priority_map.get(priority, str(priority))

        assigned_time = getattr(task, "assigned_time", None) or getattr(task, "start", None)
        if isinstance(assigned_time, str):
            assigned_time = parse_deadline_datetime(assigned_time)
        assigned_str = assigned_time.strftime("%Y-%m-%d %H:%M") if isinstance(assigned_time, datetime) else "Nie przypisano"

        deadline = getattr(task, "deadline", None)
        if isinstance(deadline, str):
            deadline_parsed = parse_deadline_datetime(deadline)
            deadline_str = deadline_parsed.strftime("%Y-%m-%d %H:%M") if deadline_parsed else deadline
        elif isinstance(deadline, datetime):
            deadline_str = deadline.strftime("%Y-%m-%d %H:%M")
        else:
            deadline_str = str(deadline or "Brak")

        duration_min = _parse_task_duration_minutes(task)
        focus = getattr(task, "focus", 5)

        tags_str = ", ".join(t.title for t in task.tags) if getattr(task, "tags", None) else "Brak tagów"

        ctk.CTkLabel(top, text="Szczegóły zadania", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 10))

        content_frame = ctk.CTkFrame(top, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=25, pady=5)

        rows = [
            ("Opis:", desc),
            ("Termin (Deadline):", deadline_str),
            ("Zaplanowany czas:", assigned_str),
            ("Czas trwania:", f"{duration_min} min ({duration_min / 60:.1f}h)"),
            ("Priorytet:", priority_str),
            ("Wymagane skupienie:", f"{focus}/10"),
            ("Tagi:", tags_str),
        ]

        for r_idx, (label_txt, val_txt) in enumerate(rows):
            ctk.CTkLabel(content_frame, text=label_txt, font=ctk.CTkFont(weight="bold")).grid(
                row=r_idx, column=0, sticky="w", pady=3
            )
            ctk.CTkLabel(content_frame, text=val_txt).grid(row=r_idx, column=1, sticky="w", padx=10, pady=3)

        btn_box = ctk.CTkFrame(top, fg_color="transparent")
        btn_box.pack(fill="x", padx=25, pady=(10, 15))

        def complete_and_close():
            datas.complete_task(task)
            self.refresh()
            top.destroy()

        ctk.CTkButton(
            btn_box,
            text="✓ Oznacz jako ukończone",
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            command=complete_and_close,
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))

        ctk.CTkButton(
            btn_box,
            text="Zamknij",
            fg_color="gray",
            hover_color="darkgray",
            command=top.destroy,
        ).pack(side="right", padx=(5, 0))
