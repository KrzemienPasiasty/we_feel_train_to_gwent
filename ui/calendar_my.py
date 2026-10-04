from datetime import datetime, time, timedelta, date
from typing import Callable, Optional, List, Any, Dict
import threading
import customtkinter as ctk

import datas
from models.task import Task
from models.tag import Tag
from models.week_periods import WeekTime, WeeklySchedule


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
                cell_bg = ctk.CTkFrame(
                    self.scroll_frame,
                    fg_color=("gray85", "gray20") if slot % 2 == 0 else ("gray90", "gray17"),
                    height=24,
                    corner_radius=1,
                )
                cell_bg.grid(row=slot, column=idx + 1, sticky="nsew", padx=1, pady=1)

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

        if self.last_optimization_result is not None:
            self._render_optimization_items(self.last_optimization_result)
        else:
            self._render_tasks(datas.current_tasks_list)

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
                    width=5,
                    corner_radius=2,
                )
                hint_strip.grid(
                    row=row_start,
                    column=col_index,
                    rowspan=row_span,
                    sticky="nsw",
                    padx=(2, 0),
                    pady=1,
                )
                self.hint_widgets.append(hint_strip)

    def _render_tasks(self, tasks: List[Task]):
        """Renderuje zadania z datas.current_tasks_list na siatce."""
        cal_start_min = self.start_hour * 60
        cal_end_min = self.end_hour * 60

        for task in tasks:
            start_time = getattr(task, "assigned_time", None) or getattr(task, "start", None)
            if start_time is None:
                continue

            try:
                task_day = start_time.weekday()
            except AttributeError:
                continue

            if not self.is_weekly_view and task_day != self.target_date.weekday():
                continue

            start_min = start_time.hour * 60 + start_time.minute
            if start_min < cal_start_min or start_min >= cal_end_min:
                continue

            row_start = (start_min - cal_start_min) // 15
            duration_minutes = _parse_task_duration_minutes(task)
            row_span = max(1, min(self.total_intervals - row_start, duration_minutes // 15))

            col_index = (task_day + 1) if self.is_weekly_view else 1

            end_min = start_min + duration_minutes
            start_str = f"{start_time.hour:02d}:{start_time.minute:02d}"
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
                activity_name=act.activity_type,
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

        def worker():
            try:
                from optimizer import optimize_schedule, OptimizationConfig

                ws = datas.weekly_schedule_list[0] if datas.weekly_schedule_list else WeeklySchedule()
                curve = [0.5] * 96

                cfg = OptimizationConfig(
                    reference_date=monday_dt,
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

                    self.last_optimization_result = opt_res
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
        assigned_str = assigned_time.strftime("%Y-%m-%d %H:%M") if isinstance(assigned_time, datetime) else "Nie przypisano"

        deadline = getattr(task, "deadline", None)
        deadline_str = deadline.strftime("%Y-%m-%d %H:%M") if isinstance(deadline, datetime) else str(deadline or "Brak")

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
