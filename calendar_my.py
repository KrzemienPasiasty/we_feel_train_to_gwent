import customtkinter as ctk
from datetime import datetime, time
from typing import Callable, Optional, List, Any


# Zakładamy, że struktury Task, Tag, WeeklySchedule są dostępne w Twoim środowisku
from task import Task
from tag import Tag
from week_periods import WeeklySchedule

def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Konwertuje kolor zapisany jako krotka RGB na format HEX."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


class TaskWidget(ctk.CTkFrame):
    """Komponent reprezentujący pojedynczy obiekt Task na kalendarzu."""

    PRIORITY_SYMBOLS = {
        1: "⚡",  # Zakładając, że 1 to priorytet najwyższy
        2: "🔴",
        3: "🟡",
        4: "🟢"
    }

    def __init__(
            self,
            master,
            task: Any,  # Obiekt klasy Task
            command: Optional[Callable[[Any], None]] = None,
            **kwargs
    ):
        # Pobieranie koloru z pierwszego przypisanego tagu (jeśli istnieje)
        category_color = "#1f538d"  # Domyślny kolor
        if hasattr(task, 'tags') and task.tags:
            category_color = rgb_to_hex(task.tags[0].color)

        super().__init__(
            master,
            fg_color=category_color,
            corner_radius=4,
            cursor="hand2",
            **kwargs
        )

        self.task = task
        self.command = command

        # Pobieranie danych bezpośrednio ze struktury Task
        priority = getattr(task, 'priority', 3)
        symbol = self.PRIORITY_SYMBOLS.get(priority, "📌")
        title = getattr(task, 'description', "Brak opisu")

        display_text = f"{symbol} {title}"

        # Etykieta tekstu wewnątrz zadania
        self.label = ctk.CTkLabel(
            self,
            text=display_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffffff",
            anchor="w",
            justify="left"
        )
        self.label.pack(fill="both", expand=True, padx=4, pady=2)

        # Eventy naciśnięcia
        self.bind("<Button-1>", self._on_click)
        self.label.bind("<Button-1>", self._on_click)

    def _on_click(self, event):
        if self.command:
            self.command(self.task)


class CalendarFrame(ctk.CTkFrame):
    """
    Osadzalny widget kalendarza.
    Przyjmuje gotową listę obiektów Task oraz strukturę WeeklySchedule.
    """

    DAYS_OF_WEEK = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]

    def __init__(
            self,
            master,
            tasks: List[Any],
            schedule: Any,  # Obiekt klasy WeeklySchedule
            start_hour: int = 8,
            end_hour: int = 18,
            command: Optional[Callable[[Any], None]] = None,
            **kwargs
    ):
        super().__init__(master, **kwargs)

        self.start_hour = start_hour
        self.end_hour = end_hour
        self.command = command

        # 4 sloty na każdą godzinę
        self.total_intervals = (end_hour - start_hour) * 4

        self.task_widgets: List[TaskWidget] = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_grid()

        # Generowanie UI opartych o dostarczone dane
        self._render_schedule_hints(schedule)
        self._render_tasks(tasks)

    def _build_header(self):
        """Tworzy nagłówek z nazwami dni tygodnia."""
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=(60, 15), pady=(5, 5))

        for day_idx in range(7):
            self.header_frame.grid_columnconfigure(day_idx, weight=1)
            lbl = ctk.CTkLabel(
                self.header_frame,
                text=self.DAYS_OF_WEEK[day_idx],
                font=ctk.CTkFont(size=12, weight="bold")
            )
            lbl.grid(row=0, column=day_idx, sticky="ew", padx=2)

    def _build_grid(self):
        """Tworzy przewijany obszar 15-minutowej siatki czasowej."""
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.scroll_frame.grid_columnconfigure(0, minsize=55)
        for col in range(1, 8):
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

            # Tło komórek wierszy
            for day in range(7):
                cell_bg = ctk.CTkFrame(
                    self.scroll_frame,
                    fg_color=("gray85", "gray20") if slot % 2 == 0 else ("gray90", "gray17"),
                    height=24,
                    corner_radius=1
                )
                cell_bg.grid(row=slot, column=day + 1, sticky="nsew", padx=1, pady=1)

    def _render_schedule_hints(self, schedule: Any):
        """
        Zoptymalizowane podświetlanie przedziałów tagów za pomocą metody intervals_for().
        Tagi renderują się jako cieniutkie paski z lewej strony, by być tylko podglądem.
        """
        cal_start_min = self.start_hour * 60
        cal_end_min = self.end_hour * 60

        for tag in schedule.tags():
            color_hex = rgb_to_hex(tag.color)

            # Pobieramy mądrze połączone interwały dla tagu z week_periods.py
            for interval in schedule.intervals_for(tag):
                start_min = interval.start
                end_min = interval.end

                # Jeśli blok wypada całkowicie poza godzinami kalendarza, pomiń
                if end_min <= cal_start_min or start_min >= cal_end_min:
                    continue

                # Ograniczenie rysowania do widoku kalendarza
                visible_start = max(start_min, cal_start_min)
                visible_end = min(end_min, cal_end_min)

                row_start = (visible_start - cal_start_min) // 15
                row_end = (visible_end - cal_start_min) // 15
                row_span = max(1, row_end - row_start)

                # Minimalna ingerencja: wąski, nieinteraktywny marker z lewej krawędzi komórki
                hint_strip = ctk.CTkFrame(
                    self.scroll_frame,
                    fg_color=color_hex,
                    width=4,  # Wąski pasek
                    corner_radius=2
                )
                # Używamy sticky="nsw" (North-South-West) by przykleić to pionowo do lewej krawędzi
                hint_strip.grid(
                    row=row_start,
                    column=interval.day + 1,
                    rowspan=row_span,
                    sticky="nsw",
                    padx=(2, 0),
                    pady=1
                )

    def _render_tasks(self, tasks: List[Any]):
        """Renderowanie obiektów typu Task."""
        cal_start_min = self.start_hour * 60

        for task in tasks:
            # Zakładam, że algorytm planujący dopina te właściwości do Twojego
            # obiektu Task na czas wyświetlania w GUI
            day = getattr(task, 'day', None)
            start_time = getattr(task, 'start_time', None)

            if day is None or start_time is None:
                # Nie da się umiejscowić taska w siatce bez jego pozycji w czasie
                continue

            start_min = start_time.hour * 60 + start_time.minute
            if start_min < cal_start_min:
                continue

            row_start = (start_min - cal_start_min) // 15

            # Obliczanie czasu trwania. Zakładam, że task.time (DateTime) z Twojego
            # modelu posiada odczytywalne właściwości hour i minute.
            task_req_time = getattr(task, 'time', None)
            if task_req_time:
                duration_minutes = (getattr(task_req_time, 'hour', 0) * 60) + getattr(task_req_time, 'minute', 15)
            else:
                duration_minutes = 15

            row_span = max(1, duration_minutes // 15)

            widget = TaskWidget(
                master=self.scroll_frame,
                task=task,
                command=self.command
            )

            # Kluczowe dla wyglądu: padx=(10, 2) robi margines po lewej stronie taska,
            # dzięki czemu kolorowy "hint" tagów (o szerokości 4px) nie jest przez zadanie zasłonięty.
            widget.grid(
                row=row_start,
                column=day + 1,
                rowspan=row_span,
                sticky="nsew",
                padx=(10, 2),
                pady=1
            )
            self.task_widgets.append(widget)


# ==========================================
# Przykład użycia aplikacji z poziomu CTk
# ==========================================


    # Przykładowe dane z backendu
    sample_tasks = [
        {
            "id": 101,
            "title": "Daily Standup",
            "day": 0,  # Poniedziałek
            "start_time": time(8, 30),
            "duration_minutes": 30,
            "color": "#1E88E5",
            "priority": "HIGH"
        },
        {
            "id": 102,
            "title": "Code Review",
            "day": 1,  # Wtorek
            "start_time": time(10, 0),
            "duration_minutes": 45,
            "color": "#D81B60",
            "priority": "CRITICAL"
        },
        {
            "id": 103,
            "title": "Planowanie Sprintu",
            "day": 2,  # Środa
            "start_time": time(11, 15),
            "duration_minutes": 60,
            "color": "#43A047",
            "priority": "MEDIUM"
        },
        {
            "id": 104,
            "title": "Dokumentacja",
            "day": 4,  # Piątek
            "start_time": time(14, 0),
            "duration_minutes": 90,
            "color": "#FB8C00",
            "priority": "LOW"
        }
    ]

    # Załadowanie zadań
    # calendar.set_tasks(sample_tasks, )
    #
    # root.mainloop()