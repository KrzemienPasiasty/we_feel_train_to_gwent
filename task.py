from datetime import datetime
from typing import List, Optional
from tag import Tag


class Task:
    def __init__(self):
        self.id: int = 0
        self.description: str = ""
        self.deadline: Optional[datetime] = None
        self.time: Optional[datetime] = None
        """ required time to spend at task"""
        self.focus: int
        self.priority: int = 1
        self.tags: List[Tag] = []
        self.llm_metadata: str = ""

    def __repr__(self) -> str:
        tags_str = [t.title if hasattr(t, "title") else str(t) for t in self.tags]
        return (
            f"Task(id={self.id}, description={self.description!r}, "
            f"deadline={self.deadline}, priority={self.priority}, tags={tags_str})"
        )










import customtkinter as ctk
import threading
from datetime import datetime
from xmlrpc.client import DateTime

# Importy klas z innych plików według wymagań
from task import Task
from tag import Tag
#from datas import Datas #TODO:temp comment


class TaskFrame(ctk.CTkFrame):
    def __init__(self, master, available_tags: list[Tag], autofill_callback, **kwargs):
        super().__init__(master, **kwargs)

        self.available_tags = available_tags
        self.autofill_callback = autofill_callback
        self.selected_tags = []
        self.tag_buttons = {}

        # --- Nagłówek ---
        self.title_label = ctk.CTkLabel(self, text="Utwórz nowe zadanie", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=(10, 20))

        # --- Przycisk Autofill ---
        self.autofill_btn = ctk.CTkButton(self, text="Autouzupełnianie (AI)", command=self._start_autofill)
        self.autofill_btn.pack(pady=(0, 15), fill="x", padx=20)


        # 1. Description[cite: 1]
        self.desc_label = ctk.CTkLabel(self, text="Opis zadania (Description):")
        self.desc_label.pack(anchor="w", padx=20)
        self.desc_entry = ctk.CTkTextbox(self, height=60)
        self.desc_entry.pack(fill="x", padx=20, pady=(0, 10))

        # 2. Deadline[cite: 1] - Ładny wybór czasu (uproszczony do Comboboxów i Entry)
        self.deadline_label = ctk.CTkLabel(self, text="Termin (Deadline):")
        self.deadline_label.pack(anchor="w", padx=20)

        self.deadline_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.deadline_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.deadline_date = ctk.CTkEntry(self.deadline_frame, placeholder_text="YYYY-MM-DD")
        self.deadline_date.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.deadline_hour = ctk.CTkComboBox(self.deadline_frame, values=[f"{i:02d}" for i in range(24)], width=70)
        self.deadline_hour.pack(side="left", padx=5)

        self.deadline_minute = ctk.CTkComboBox(self.deadline_frame, values=[f"{i:02d}" for i in range(0, 60, 5)],
                                               width=70)
        self.deadline_minute.pack(side="left", padx=(5, 0))

        # 3. Time (Wymagany czas)[cite: 1]
        self.time_label = ctk.CTkLabel(self, text="Wymagany czas (Time) np. 2h:")
        self.time_label.pack(anchor="w", padx=20)
        self.time_entry = ctk.CTkEntry(self, placeholder_text="Np. 02:30 lub 1h")
        self.time_entry.pack(fill="x", padx=20, pady=(0, 10))

        # 4. Focus (Slider)[cite: 1]
        self.focus_label = ctk.CTkLabel(self, text="Skupienie (Focus):")
        self.focus_label.pack(anchor="w", padx=20)
        self.focus_slider = ctk.CTkSlider(self, from_=0, to=10, number_of_steps=10)
        self.focus_slider.set(5)  # Domyślna wartość
        self.focus_slider.pack(fill="x", padx=20, pady=(0, 10))

        # 5. Priority (Slider)[cite: 1]
        self.priority_label = ctk.CTkLabel(self, text="Priorytet (Priority):")
        self.priority_label.pack(anchor="w", padx=20)
        self.priority_slider = ctk.CTkSlider(self, from_=0, to=10, number_of_steps=10)
        self.priority_slider.set(5)
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
        self.add_task_btn.pack(pady=20, fill="x", padx=20)

    def _create_tag_buttons(self):
        """Tworzy przyciski dla obiektów tagów i zapisuje je w słowniku."""
        for tag in self.available_tags:
            btn = ctk.CTkButton(
                self.tags_frame,
                text=tag.title,  # [cite: 2]
                fg_color="gray",
                text_color="white",
                command=lambda t=tag: self._toggle_tag(t)
            )
            btn.pack(side="left", padx=5, pady=5)
            self.tag_buttons[tag] = btn

    def _rgb_to_hex(self, rgb_tuple):
        """Konwertuje kolor zapisany w formacie (R, G, B) na format HEX, wymagany przez customtkinter."""
        return f'#{rgb_tuple[0]:02x}{rgb_tuple[1]:02x}{rgb_tuple[2]:02x}'

    def _toggle_tag(self, tag: Tag):
        """Zaznacza lub odznacza tag po kliknięciu."""
        button = self.tag_buttons[tag]
        if tag in self.selected_tags:
            self.selected_tags.remove(tag)
            button.configure(fg_color="gray")  # Kolor odznaczonego taga
        else:
            self.selected_tags.append(tag)
            # Wykorzystanie koloru zapisanego w obiekcie Tag[cite: 2]
            active_color = self._rgb_to_hex(tag.color) if hasattr(tag, 'color') and tag.color else "#1f6aa5"
            button.configure(fg_color=active_color)

    def _start_autofill(self):
        """Uruchamia funkcję autouzupełniania w osobnym wątku."""
        self.autofill_btn.configure(state="disabled", text="Przetwarzanie (Oczekiwanie na odpowiedź)...")

        def worker():
            # Program czeka na odpowiedź funkcji
            autofill_data = self.autofill_callback()
            # Po uzyskaniu odpowiedzi aktualizuje UI w głównym wątku (wymagane w tkinter)
            self.after(0, self._apply_autofill_data, autofill_data)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_autofill_data(self, data: dict):
        """Wypełnia formularz danymi z callbacka."""
        self.autofill_btn.configure(state="normal", text="Autouzupełnianie (AI)")

        if not data:
            return

        # Przykładowa implementacja uzupełniania danych
        if "description" in data:
            self.desc_entry.delete("0.0", "end")
            self.desc_entry.insert("0.0", data["description"])

        if "focus" in data:
            self.focus_slider.set(data["focus"])

        if "priority" in data:
            self.priority_slider.set(data["priority"])

        if "time" in data:
            self.time_entry.delete(0, "end")
            self.time_entry.insert(0, data["time"])

        if "deadline_date" in data:
            self.deadline_date.delete(0, "end")
            self.deadline_date.insert(0, data["deadline_date"])

        # Automatyczne zaznaczenie przydzielonych tagów (wymaga dopasowania po title[cite: 2])
        if "tags" in data:
            for tag in self.available_tags:
                if tag.title in data["tags"] and tag not in self.selected_tags:
                    self._toggle_tag(tag)

    def _submit_task(self):
        """Tworzy obiekt Task i wywołuje Datas.add_task(task)."""
        new_task = Task()

        # Uzupełnianie atrybutów Taska[cite: 1]
        new_task.description = self.desc_entry.get("0.0", "end").strip()
        new_task.focus = int(self.focus_slider.get())
        new_task.priority = int(self.priority_slider.get())

        # Formatowanie daty
        date_str = self.deadline_date.get()
        hour_str = self.deadline_hour.get()
        min_str = self.deadline_minute.get()
        # Dla uproszczenia jako string. W pełnej aplikacji należałoby to zrzutować na oczekiwany typ DateTime[cite: 1]
        new_task.deadline = f"{date_str}T{hour_str}:{min_str}:00"

        new_task.time = self.time_entry.get()
        new_task.tags = self.selected_tags

        # Wywołanie zewnętrznej klasy obsługującej operacje na danych (Datas)
       # Datas.add_task(new_task)#TODO:temp comment

        # Opcjonalnie czyszczenie formularza po wysłaniu
        self._clear_form()

    def _clear_form(self):
        self.desc_entry.delete("0.0", "end")
        self.time_entry.delete(0, "end")
        self.deadline_date.delete(0, "end")
        self.focus_slider.set(5)
        self.priority_slider.set(5)
        for tag in list(self.selected_tags):
            self._toggle_tag(tag)
