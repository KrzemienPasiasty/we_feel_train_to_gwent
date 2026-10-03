import customtkinter as ctk
from datetime import datetime, time
from typing import Callable, Optional, Dict, List, Any


class TaskWidget(ctk.CTkFrame):
    """Komponent reprezentujący pojedynczy task w kalendarzu."""

    PRIORITY_SYMBOLS = {
        "CRITICAL": "⚡",
        "HIGH": "🔴",
        "MEDIUM": "🟡",
        "LOW": "🟢"
    }

    def __init__(
            self,
            master,
            task_data: Dict[str, Any],
            command: Optional[Callable[[Dict[str, Any]], None]] = None,
            **kwargs
    ):
        category_color = task_data.get("color", "#1f538d")
        hover_color = task_data.get("hover_color", "#14375e")

        super().__init__(
            master,
            fg_color=category_color,
            corner_radius=4,
            cursor="hand2",
            **kwargs
        )

        self.task_data = task_data
        self.command = command

        # Formatowanie nagłówka priorytetu i nazwy
        priority = str(task_data.get("priority", "MEDIUM")).upper()
        symbol = self.PRIORITY_SYMBOLS.get(priority, "📌")
        title = task_data.get("title", "Bez nazwy")

        display_text = f"{symbol} {title}"

        # Etykieta tekstu wewnątrz taska
        self.label = ctk.CTkLabel(
            self,
            text=display_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffffff",
            anchor="w",
            justify="left"
        )
        self.label.pack(fill="both", expand=True, padx=4, pady=2)

        # Reakcja na najechanie myszką i kliknięcie
        self.bind("<Enter>", lambda e: self.configure(fg_color=hover_color))
        self.bind("<Leave>", lambda e: self.configure(fg_color=category_color))
        self.bind("<Button-1>", self._on_click)
        self.label.bind("<Button-1>", self._on_click)

    def _on_click(self, event):
        if self.command:
            self.command(self.task_data)


class WeeklyCalendarFrame(ctk.CTkFrame):
    """
    Osadzalny widget kalendarza tygodniowego w CustomTkinter.
    Przedziały czasowe: 15 minut.
    """

    DAYS_OF_WEEK = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]

    def __init__(
            self,
            master,
            start_hour: int = 8,
            end_hour: int = 18,
            command: Optional[Callable[[Dict[str, Any]], None]] = None,
            **kwargs
    ):
        super().__init__(master, **kwargs)

        self.start_hour = start_hour
        self.end_hour = end_hour
        self.command = command

        # Wyliczenie łącznej liczby interwałów 15-minutowych
        self.total_intervals = (end_hour - start_hour) * 4

        self.task_widgets: List[TaskWidget] = []

        # Konfiguracja głównej siatki
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_grid()

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
        """Tworzy przewijany obszar siatki czasowej."""
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # Kolumna 0 na godziny, Kolumny 1-7 na dni tygodnia
        self.scroll_frame.grid_columnconfigure(0, minsize=55)
        for col in range(1, 8):
            self.scroll_frame.grid_columnconfigure(col, weight=1, minsize=100)

        # Generowanie etykiet czasu i pustych komórek tła
        for slot in range(self.total_intervals):
            total_minutes = self.start_hour * 60 + (slot * 15)
            hour = total_minutes // 60
            minute = total_minutes % 60

            # Etykieta godziny wyświetlana co 15 minut
            time_str = f"{hour:02d}:{minute:02d}"
            time_lbl = ctk.CTkLabel(
                self.scroll_frame,
                text=time_str if minute % 30 == 0 else "∙",
                font=ctk.CTkFont(size=10),
                text_color="gray"
            )
            time_lbl.grid(row=slot, column=0, sticky="n", pady=1)

            # Puste linie podziału komórek
            for day in range(7):
                cell_bg = ctk.CTkFrame(
                    self.scroll_frame,
                    fg_color=("gray85", "gray20") if slot % 2 == 0 else ("gray90", "gray17"),
                    height=24,
                    corner_radius=1
                )
                cell_bg.grid(row=slot, column=day + 1, sticky="nsew", padx=1, pady=1)

    def _time_to_slot(self, time_obj: time) -> int:
        """Kowersja czasu na indeks wiersza siatki."""
        minutes_from_start = (time_obj.hour - self.start_hour) * 60 + time_obj.minute
        return minutes_from_start // 15

    def add_task(self, task_data: Dict[str, Any]):
        """
        Backendowe dodawanie taska do kalendarza.

        Oczekiwana struktura task_data:
        {
            "id": int/str,
            "title": str,
            "day": int (0-6, gdzie 0=Poniedziałek),
            "start_time": datetime.time(hour, minute),
            "duration_minutes": int (wielokrotność 15),
            "color": str (hex / color name),
            "priority": str ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        }
        """
        day = task_data.get("day", 0)
        start_t = task_data.get("start_time", time(8, 0))
        duration = task_data.get("duration_minutes", 15)

        start_slot = self._time_to_slot(start_t)
        row_span = max(1, duration // 15)

        # Walidacja zakresu
        if start_slot < 0 or (start_slot + row_span) > self.total_intervals:
            return  # Task wykracza poza ustawione godziny pracy kalendarza

        widget = TaskWidget(
            master=self.scroll_frame,
            task_data=task_data,
            command=self.command
        )

        # Umieszczenie w siatce (kolumna +1 ze względu na kolumnę godzin)
        widget.grid(
            row=start_slot,
            column=day + 1,
            rowspan=row_span,
            sticky="nsew",
            padx=2,
            pady=1
        )
        self.task_widgets.append(widget)

    def clear_tasks(self):
        """Usuwa wszystkie wyrenderowane zadania z kalendarza."""
        for w in self.task_widgets:
            w.destroy()
        self.task_widgets.clear()

    def set_tasks(self, tasks: List[Dict[str, Any]]):
        """Podmienia całą listę zadań."""
        self.clear_tasks()
        for task in tasks:
            self.add_task(task)


# ==========================================
# Przykład użycia aplikacji z poziomu CTk
# ==========================================
if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("System Zarządzania Zadaniami")
    root.geometry("1100x700")


    def my_task_click_handler(task_data: dict):
        """Funkcja callback wywoływana po kliknięciu w task."""
        print("\n[EVENT] Kliknięto task!")
        print(f"ID: {task_data.get('id')}")
        print(f"Tytuł: {task_data.get('title')}")
        print(f"Priorytet: {task_data.get('priority')}")
        print(f"Dane pełne: {task_data}")


    # Osadzenie kalendarza jako zwykły widget
    calendar = WeeklyCalendarFrame(
        master=root,
        start_hour=8,
        end_hour=17,
        command=my_task_click_handler
    )
    calendar.pack(fill="both", expand=True, padx=10, pady=10)

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
    calendar.set_tasks(sample_tasks)

    root.mainloop()