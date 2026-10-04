from datetime import datetime
from typing import Callable, Optional, List
import customtkinter as ctk

from task import Task
from tag import Tag
import datas


def _rgb_to_hex(rgb_tuple) -> str:
    if isinstance(rgb_tuple, (list, tuple)) and len(rgb_tuple) >= 3:
        return f"#{int(rgb_tuple[0]):02x}{int(rgb_tuple[1]):02x}{int(rgb_tuple[2]):02x}"
    return "#1f6aa5"


def _format_deadline(deadline_val) -> str:
    if not deadline_val:
        return "Brak terminu"
    if isinstance(deadline_val, datetime):
        return deadline_val.strftime("%Y-%m-%d %H:%M")
    if isinstance(deadline_val, str):
        try:
            dt = datetime.fromisoformat(deadline_val.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return deadline_val
    return str(deadline_val)


def _format_time_duration(time_val) -> str:
    if not time_val:
        return "Auto / Nie określono"
    if isinstance(time_val, str):
        if "T" in time_val:
            try:
                dt = datetime.fromisoformat(time_val)
                return f"{dt.hour:02d}:{dt.minute:02d}"
            except Exception:
                pass
        return time_val
    if isinstance(time_val, datetime):
        return f"{time_val.hour:02d}:{time_val.minute:02d}"
    return str(time_val)


class TaskCard(ctk.CTkFrame):
    """Karta reprezentująca pojedyncze zadanie na liście."""

    PRIORITY_INFO = {
        1: ("⚡ Krytyczny (1)", "#b71c1c", "#ff8a80"),
        2: ("🔴 Wysoki (2)", "#e65100", "#ffb74d"),
        3: ("🟡 Średni (3)", "#f57f17", "#fff176"),
        4: ("🟢 Niski (4)", "#2e7d32", "#a5d6a7"),
    }

    def __init__(
        self,
        master,
        task: Task,
        on_complete: Optional[Callable[[Task], None]] = None,
        on_delete: Optional[Callable[[Task], None]] = None,
        **kwargs,
    ):
        super().__init__(
            master,
            corner_radius=10,
            fg_color=("gray90", "#2b2b2b"),
            border_width=1,
            border_color=("gray75", "#3d3d3d"),
            **kwargs,
        )
        self.task = task
        self.on_complete = on_complete
        self.on_delete = on_delete

        self._build_card()

    def _build_card(self):
        # Top bar: Priorytet, ID oraz przyciski akcji
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=12, pady=(10, 6))

        # Badge priorytetu
        priority = getattr(self.task, "priority", 3)
        p_text, p_bg, p_text_color = self.PRIORITY_INFO.get(
            priority, (f"Priorytet {priority}", "#455a64", "#cfd8dc")
        )

        priority_badge = ctk.CTkLabel(
            top_bar,
            text=f" {p_text} ",
            fg_color=p_bg,
            text_color="white",
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        priority_badge.pack(side="left", padx=(0, 8))

        # Badge ID
        task_id = getattr(self.task, "id", None)
        id_str = f"#{task_id}" if task_id is not None else "#?"
        id_badge = ctk.CTkLabel(
            top_bar,
            text=id_str,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray40", "gray65"),
        )
        id_badge.pack(side="left", padx=4)

        # Przyciski akcji z prawej
        btn_container = ctk.CTkFrame(top_bar, fg_color="transparent")
        btn_container.pack(side="right")

        delete_btn = ctk.CTkButton(
            btn_container,
            text="🗑️ Usuń",
            width=70,
            height=26,
            fg_color=("gray75", "#424242"),
            hover_color="#c62828",
            font=ctk.CTkFont(size=11),
            command=self._handle_delete,
        )
        delete_btn.pack(side="right", padx=3)

        complete_btn = ctk.CTkButton(
            btn_container,
            text="✓ Ukończ",
            width=75,
            height=26,
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._handle_complete,
        )
        complete_btn.pack(side="right", padx=3)

        # Treść zadania (opis)
        desc = getattr(self.task, "description", "") or "(Brak opisu)"
        desc_label = ctk.CTkLabel(
            self,
            text=desc,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=700,
        )
        desc_label.pack(fill="x", padx=14, pady=(2, 8))

        # Pasek metadanych (Termin, Czas, Focus)
        meta_bar = ctk.CTkFrame(self, fg_color="transparent")
        meta_bar.pack(fill="x", padx=14, pady=(0, 8))

        # Deadline
        deadline_text = _format_deadline(getattr(self.task, "deadline", None))
        deadline_lbl = ctk.CTkLabel(
            meta_bar,
            text=f"📅 Termin: {deadline_text}",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )
        deadline_lbl.pack(side="left", padx=(0, 16))

        # Czas trwania
        time_text = _format_time_duration(getattr(self.task, "time", None))
        time_lbl = ctk.CTkLabel(
            meta_bar,
            text=f"⏱️ Wymagany czas: {time_text}",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )
        time_lbl.pack(side="left", padx=(0, 16))

        # Focus
        focus_val = getattr(self.task, "focus", None)
        if focus_val is not None:
            focus_str = f"{focus_val}/10" if isinstance(focus_val, (int, float)) and focus_val > 1 else (f"{int(focus_val*10)}/10" if isinstance(focus_val, float) else str(focus_val))
            focus_lbl = ctk.CTkLabel(
                meta_bar,
                text=f"🧠 Focus: {focus_str}",
                font=ctk.CTkFont(size=12),
                text_color=("gray30", "gray70"),
            )
            focus_lbl.pack(side="left", padx=(0, 16))

        # Pasek tagów
        tags = getattr(self.task, "tags", [])
        if tags:
            tags_bar = ctk.CTkFrame(self, fg_color="transparent")
            tags_bar.pack(fill="x", padx=14, pady=(0, 10))

            tag_icon = ctk.CTkLabel(
                tags_bar,
                text="🏷️ Tagi:",
                font=ctk.CTkFont(size=11),
                text_color=("gray40", "gray60"),
            )
            tag_icon.pack(side="left", padx=(0, 6))

            for tag in tags:
                if isinstance(tag, Tag):
                    title = tag.title
                    color = _rgb_to_hex(tag.color)
                elif isinstance(tag, dict):
                    title = tag.get("title", tag.get("name", "Tag"))
                    color = _rgb_to_hex(tag.get("color", (100, 100, 100)))
                else:
                    title = str(tag)
                    color = "#455a64"

                tag_chip = ctk.CTkLabel(
                    tags_bar,
                    text=f" {title} ",
                    fg_color=color,
                    text_color="white",
                    corner_radius=4,
                    font=ctk.CTkFont(size=11, weight="bold"),
                )
                tag_chip.pack(side="left", padx=3)

    def _handle_complete(self):
        if self.on_complete:
            self.on_complete(self.task)

    def _handle_delete(self):
        if self.on_delete:
            self.on_delete(self.task)


class TaskListFrame(ctk.CTkFrame):
    """
    Główny komponent widoku listy aktualnych zadań w oknie aplikacji.
    Zawiera nagłówek ze statystykami, wyszukiwanie, filtrowanie, sortowanie
    oraz przewijaną listę kart zadań.
    """

    def __init__(
        self,
        master,
        on_add_task_click: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.on_add_task_click = on_add_task_click

        self._build_header()
        self._build_controls()
        self._build_scrollable_list()

        # Załadowanie zadań na start
        self.refresh_tasks()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 10))

        # Tytuł i licznik
        left_box = ctk.CTkFrame(header, fg_color="transparent")
        left_box.pack(side="left")

        title = ctk.CTkLabel(
            left_box,
            text="📋 Aktualna lista zadań",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title.pack(side="left", padx=(0, 10))

        self.count_badge = ctk.CTkLabel(
            left_box,
            text="0 zadań",
            fg_color=("gray80", "#3a3a3a"),
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            padx=10,
            pady=3,
        )
        self.count_badge.pack(side="left")

        # Przyciski po prawej
        right_box = ctk.CTkFrame(header, fg_color="transparent")
        right_box.pack(side="right")

        self.refresh_btn = ctk.CTkButton(
            right_box,
            text="🔄 Odśwież",
            width=90,
            height=32,
            font=ctk.CTkFont(size=12),
            command=lambda: self.refresh_tasks(reload_from_disk=True),
        )
        self.refresh_btn.pack(side="left", padx=5)

        if self.on_add_task_click:
            self.add_btn = ctk.CTkButton(
                right_box,
                text="➕ Dodaj zadanie",
                width=120,
                height=32,
                fg_color="#1f6aa5",
                hover_color="#144870",
                font=ctk.CTkFont(size=12, weight="bold"),
                command=self.on_add_task_click,
            )
            self.add_btn.pack(side="left", padx=5)

    def _build_controls(self):
        controls = ctk.CTkFrame(self, fg_color=("gray85", "#242424"), corner_radius=8)
        controls.pack(fill="x", padx=15, pady=(0, 10), ipady=5)

        # Wyszukiwarka
        self.search_entry = ctk.CTkEntry(
            controls,
            placeholder_text="🔍 Szukaj w zadaniach...",
            width=260,
        )
        self.search_entry.pack(side="left", padx=(10, 10), pady=6)
        self.search_entry.bind("<KeyRelease>", lambda event: self._apply_filters())

        # Filtr priorytetu
        ctk.CTkLabel(controls, text="Priorytet:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(5, 3)
        )
        self.priority_filter = ctk.CTkOptionMenu(
            controls,
            values=[
                "Wszystkie",
                "1 - Krytyczny (⚡)",
                "2 - Wysoki (🔴)",
                "3 - Średni (🟡)",
                "4 - Niski (🟢)",
            ],
            width=150,
            command=lambda val: self._apply_filters(),
        )
        self.priority_filter.set("Wszystkie")
        self.priority_filter.pack(side="left", padx=(0, 10), pady=6)

        # Filtr tagów
        ctk.CTkLabel(controls, text="Tag:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(5, 3)
        )
        self.tag_filter = ctk.CTkOptionMenu(
            controls,
            values=["Wszystkie"],
            width=130,
            command=lambda val: self._apply_filters(),
        )
        self.tag_filter.set("Wszystkie")
        self.tag_filter.pack(side="left", padx=(0, 10), pady=6)

        # Sortowanie
        ctk.CTkLabel(controls, text="Sortuj:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(5, 3)
        )
        self.sort_menu = ctk.CTkOptionMenu(
            controls,
            values=[
                "Domyślnie",
                "Priorytet: najwyższy",
                "Priorytet: najniższy",
                "Termin: najbliższy",
            ],
            width=160,
            command=lambda val: self._apply_filters(),
        )
        self.sort_menu.set("Domyślnie")
        self.sort_menu.pack(side="left", padx=(0, 10), pady=6)

    def _build_scrollable_list(self):
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def update_tag_filter_options(self):
        tag_titles = set()
        for tag in datas.tags_list:
            if hasattr(tag, "title") and tag.title:
                tag_titles.add(tag.title)
        for task in datas.current_tasks_list:
            for t in getattr(task, "tags", []):
                if isinstance(t, Tag) and t.title:
                    tag_titles.add(t.title)
                elif isinstance(t, dict):
                    title = t.get("title", t.get("name"))
                    if title:
                        tag_titles.add(title)
        options = ["Wszystkie"] + sorted(list(tag_titles))
        current_val = self.tag_filter.get()
        self.tag_filter.configure(values=options)
        if current_val in options:
            self.tag_filter.set(current_val)
        else:
            self.tag_filter.set("Wszystkie")

    def refresh_tasks(self, reload_from_disk: bool = False):
        """Przeładowuje listę zadań ze źródła danych i odświeża widok."""
        if reload_from_disk:
            datas.reload_current_tasks()
        self.update_tag_filter_options()
        self._apply_filters()

    def _apply_filters(self):
        query = self.search_entry.get().strip().lower()
        priority_sel = self.priority_filter.get()
        tag_sel = self.tag_filter.get()
        sort_sel = self.sort_menu.get()

        tasks = list(datas.current_tasks_list)

        # 1. Filtrowanie po tekście
        if query:
            filtered = []
            for t in tasks:
                desc = getattr(t, "description", "").lower()
                tags_str = " ".join(
                    [
                        tag.title.lower() if isinstance(tag, Tag) else str(tag).lower()
                        for tag in getattr(t, "tags", [])
                    ]
                )
                if query in desc or query in tags_str:
                    filtered.append(t)
            tasks = filtered

        # 2. Filtrowanie po priorytecie
        if priority_sel.startswith("1"):
            tasks = [t for t in tasks if getattr(t, "priority", None) == 1]
        elif priority_sel.startswith("2"):
            tasks = [t for t in tasks if getattr(t, "priority", None) == 2]
        elif priority_sel.startswith("3"):
            tasks = [t for t in tasks if getattr(t, "priority", None) == 3]
        elif priority_sel.startswith("4"):
            tasks = [t for t in tasks if getattr(t, "priority", None) == 4]

        # 3. Filtrowanie po tagu
        if tag_sel != "Wszystkie":
            filtered = []
            for t in tasks:
                t_tags = getattr(t, "tags", [])
                match = False
                for tag in t_tags:
                    title = tag.title if isinstance(tag, Tag) else (tag.get("title", tag.get("name")) if isinstance(tag, dict) else str(tag))
                    if title == tag_sel:
                        match = True
                        break
                if match:
                    filtered.append(t)
            tasks = filtered

        # 4. Sortowanie
        if sort_sel == "Priorytet: najwyższy":
            tasks.sort(key=lambda t: getattr(t, "priority", 99))
        elif sort_sel == "Priorytet: najniższy":
            tasks.sort(key=lambda t: getattr(t, "priority", 0), reverse=True)
        elif sort_sel == "Termin: najbliższy":
            def sort_key_deadline(t):
                dl = getattr(t, "deadline", None)
                if not dl:
                    return "9999-12-31"
                if isinstance(dl, datetime):
                    return dl.isoformat()
                return str(dl)
            tasks.sort(key=sort_key_deadline)

        self._render_tasks_list(tasks, total_count=len(datas.current_tasks_list))

    def _render_tasks_list(self, tasks: List[Task], total_count: int):
        # Czyszczenie dotychczasowych widgetów
        for child in self.scroll_frame.winfo_children():
            child.destroy()

        count_text = f"{len(tasks)} / {total_count} zadań" if len(tasks) != total_count else f"{len(tasks)} zadań"
        self.count_badge.configure(text=count_text)

        if not tasks:
            empty_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, pady=60)

            empty_icon = ctk.CTkLabel(
                empty_frame,
                text="📭",
                font=ctk.CTkFont(size=48),
            )
            empty_icon.pack(pady=(0, 10))

            empty_msg = (
                "Brak zadań spełniających wybrane kryteria wyszukiwania."
                if total_count > 0
                else "Brak aktywnych zadań w liście! Dodaj nowe zadanie, aby zaplanować swój czas."
            )

            empty_lbl = ctk.CTkLabel(
                empty_frame,
                text=empty_msg,
                font=ctk.CTkFont(size=14),
                text_color=("gray50", "gray65"),
            )
            empty_lbl.pack(pady=(0, 15))

            if self.on_add_task_click and total_count == 0:
                add_first_btn = ctk.CTkButton(
                    empty_frame,
                    text="➕ Utwórz pierwsze zadanie",
                    font=ctk.CTkFont(size=13, weight="bold"),
                    command=self.on_add_task_click,
                )
                add_first_btn.pack()
            return

        for task in tasks:
            card = TaskCard(
                self.scroll_frame,
                task=task,
                on_complete=self._complete_task,
                on_delete=self._delete_task,
            )
            card.pack(fill="x", pady=5, padx=5)

    def _complete_task(self, task: Task):
        datas.complete_task(task)
        self.refresh_tasks()

    def _delete_task(self, task: Task):
        datas.delete_task(task)
        self.refresh_tasks()
