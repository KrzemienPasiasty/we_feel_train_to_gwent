import customtkinter as ctk
from datetime import datetime, time
from typing import Callable, Optional, List, Any

import datas
from task import Task
from tag import Tag
from week_periods import WeekTime


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Konwertuje kolor zapisany jako krotka RGB na format HEX."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


class TaskWidget(ctk.CTkFrame):
    """Komponent reprezentujący pojedynczy obiekt Task na kalendarzu."""

    PRIORITY_SYMBOLS = {
        4: "⚡",
        3: "🔴",
        2: "🟡",
        1: "🟢"
    }

    def __init__(
            self,
            master,
            task: Task,  # Teraz używa nowej struktury z task_2.py[cite: 5]
            command: Optional[Callable[[Task], None]] = None,
            **kwargs
    ):
        # Inicjalizacja z kolorowaniem wg. pierwszego tagu, użycie convert_color_to_hex z nowej struktury
        category_color = "#1f538d"
        if getattr(task, 'tags', None) and len(task.tags) > 0:  # [cite: 5]
            first_tag = task.tags[0]  # [cite: 5]
            # Użycie metody konwersji zawartej bezpośrednio w klasie Tag z tag_2.py
            if hasattr(first_tag, 'convert_color_to_hex'):  # [cite: 6]
                category_color = first_tag.convert_color_to_hex(first_tag.color)  # [cite: 6]
            else:
                category_color = rgb_to_hex(first_tag.color)  # [cite: 6]

        super().__init__(
            master,
            fg_color=category_color,
            corner_radius=4,
            cursor="hand2",
            **kwargs
        )

        self.task = task
        self.command = command

        priority = getattr(task, 'priority', 1)  # [cite: 5]
        symbol = self.PRIORITY_SYMBOLS.get(priority, "📌")
        title = getattr(task, 'description', "Brak opisu")  # [cite: 5]

        display_text = f"{symbol} {title}"

        self.label = ctk.CTkLabel(
            self,
            text=display_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffffff",
            anchor="w",
            justify="left"
        )
        self.label.pack(fill="both", expand=True, padx=4, pady=2)

        self.bind("<Button-1>", self._on_click)
        self.label.bind("<Button-1>", self._on_click)

    def _on_click(self, event):
        if self.command:
            self.command(self.task)


class CalendarFrame(ctk.CTkFrame):
    """
    Osadzalny widget kalendarza.
    Obsługuje widok dzienny (is_weekly_view=False) oraz tygodniowy (is_weekly_view=True).
    """

    DAYS_OF_WEEK = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]

    def __init__(
            self,
            master,
            is_weekly_view: bool = True,  # NOWY PARAMETR: Steruje trybem wyświetlania
            target_date: Optional[datetime] = None,  # Używane tylko w widoku dziennym
            start_hour: int = 8,
            end_hour: int = 18,
            command: Optional[Callable[[Task], None]] = None,
            **kwargs
    ):
        super().__init__(master, **kwargs)

        self.start_hour = start_hour
        self.end_hour = end_hour
        self.command = command
        self.is_weekly_view = is_weekly_view

        # Domyślnie użyj dzisiejszej daty jeśli brakuje
        self.target_date = target_date if target_date else datetime.now()

        # Ustalenie zakresu iteracji kolumn dni (0-6 dla tygodnia, 1 dla konkretnego dnia)
        self.days_to_render = list(range(7)) if self.is_weekly_view else [self.target_date.weekday()]
        self.col_count = len(self.days_to_render)

        self.total_intervals = (end_hour - start_hour) * 4
        self.task_widgets: List[TaskWidget] = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_grid()

        self._render_schedule_hints(datas.weekly_schedule_list[0])
        self._render_tasks(datas.current_tasks_list)

    def _build_header(self):
        """Tworzy nagłówek. Dla planu dziennego wypisuje tylko jeden dzień."""
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=(60, 15), pady=(5, 5))

        for idx, day_idx in enumerate(self.days_to_render):
            self.header_frame.grid_columnconfigure(idx, weight=1)

            header_text = self.DAYS_OF_WEEK[day_idx]
            if not self.is_weekly_view:
                header_text += f" ({self.target_date.strftime('%d.%m.%Y')})"

            lbl = ctk.CTkLabel(
                self.header_frame,
                text=header_text,
                font=ctk.CTkFont(size=12, weight="bold")
            )
            lbl.grid(row=0, column=idx, sticky="ew", padx=2)

    def _build_grid(self):
        """Tworzy 15-minutową siatkę. Ilość kolumn zależy od is_weekly_view."""
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

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
                text_color="gray"
            )
            time_lbl.grid(row=slot, column=0, sticky="n", pady=1)

            for idx in range(self.col_count):
                cell_bg = ctk.CTkFrame(
                    self.scroll_frame,
                    fg_color=("gray85", "gray20") if slot % 2 == 0 else ("gray90", "gray17"),
                    height=24,
                    corner_radius=1
                )
                cell_bg.grid(row=slot, column=idx + 1, sticky="nsew", padx=1, pady=1)

    def _render_schedule_hints(self, schedule: WeekTime):  # [cite: 4]
        """Podświetla przypisane tagi, uwzględniając tryb widoku kalendarza."""
        cal_start_min = self.start_hour * 60
        cal_end_min = self.end_hour * 60

        for tag in schedule.tags():  # [cite: 4]
            # Obsługa nowego formatu koloru
            if hasattr(tag, 'convert_color_to_hex'):  # [cite: 6]
                color_hex = tag.convert_color_to_hex(tag.color)  # [cite: 6]
            else:
                color_hex = rgb_to_hex(tag.color)  # [cite: 6]

            for interval in schedule.intervals_for(tag):  # [cite: 4]
                # Jeżeli jesteśmy w widoku dziennym i interwał dotyczy innego dnia - pomijamy
                if not self.is_weekly_view and interval.day != self.target_date.weekday():  # [cite: 4]
                    continue

                # Czas konwertowany wg parametrów week_periods (np. przedział mierzony przesunięciem timedelta)
                # Wydobycie realnych minut z interwału timedelta
                start_min = int(interval.start.total_seconds() // 60)  # [cite: 4]
                end_min = int(interval.end.total_seconds() // 60)  # [cite: 4]

                if end_min <= cal_start_min or start_min >= cal_end_min:
                    continue

                visible_start = max(start_min, cal_start_min)
                visible_end = min(end_min, cal_end_min)

                row_start = (visible_start - cal_start_min) // 15
                row_end = (visible_end - cal_start_min) // 15
                row_span = max(1, row_end - row_start)

                # Dopasowanie kolumny bazujące na tym, co renderujemy
                col_index = interval.day + 1 if self.is_weekly_view else 1  # [cite: 4]

                hint_strip = ctk.CTkFrame(
                    self.scroll_frame,
                    fg_color=color_hex,
                    width=6,  # Marker tagu z lewej
                    corner_radius=2
                )
                hint_strip.grid(
                    row=row_start,
                    column=col_index,
                    rowspan=row_span,
                    sticky="nsw",
                    padx=(2, 0),
                    pady=1
                )

    def _render_tasks(self, tasks: List[Task]):
        """Wizualizuje poszczególne zadania z task.py"""
        cal_start_min = self.start_hour * 60

        for task in tasks:
            # ZMIANA: Używamy assigned_time jako początku przedziału wyświetlania na kalendarzu
            start_time = getattr(task, 'assigned_time', None)
            if start_time is None:
                continue

            # Ekstrakcja dnia dla potrzeb ułożenia zadania w odpowiedniej kolumnie
            try:
                task_day = start_time.weekday()
            except AttributeError:
                continue

            # Filtrowanie przy widoku dziennym
            if not self.is_weekly_view and task_day != self.target_date.weekday():
                continue

            start_min = start_time.hour * 60 + start_time.minute
            if start_min < cal_start_min:
                continue

            row_start = (start_min - cal_start_min) // 15

            # ZMIANA: self.time jest ignorowane w kontekście punktu startowego,
            # a używane wyłącznie do określenia liczby zajmowanych przedziałów (czasu trwania)
            task_req_time = getattr(task, 'time', None)
            if isinstance(task_req_time, datetime):
                duration_minutes = (task_req_time.hour * 60) + task_req_time.minute
            elif isinstance(task_req_time, time):
                duration_minutes = (task_req_time.hour * 60) + task_req_time.minute
            else:
                duration_minutes = 15

            row_span = max(1, duration_minutes // 15)
            col_index = task_day + 1 if self.is_weekly_view else 1

            widget = TaskWidget(
                master=self.scroll_frame,
                task=task,
                command=self.command
            )

            widget.grid(
                row=row_start,
                column=col_index,
                rowspan=row_span,
                sticky="nsew",
                padx=(12, 2),  # Margines by nie zasłonić hint_strip od Tagu
                pady=1
            )
            self.task_widgets.append(widget)