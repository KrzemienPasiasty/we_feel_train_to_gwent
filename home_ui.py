from io import BytesIO
from pathlib import Path
from tkinter import Canvas

import customtkinter as ctk
from PIL import Image, ImageTk
from resvg_py import svg_to_bytes

from task_lifecycle import ARCHIVED_TASKS_FILE, ACTIVE_TASKS_FILE, TASK_FEEDBACK_FILE, read_task_records


MENU_ITEMS = (
    ("PROFILE", "Profile"),
    ("INTEGRATION", "Preferences"),
    ("INTERFACE", "Tasks"),
    ("ALGORITHM", "Calendar"),
)
HOME_SVG = Path(__file__).resolve().with_name("Ustawienia.svg")
MENU_HOTSPOTS = (
    (280, 185, 910, 320),
    (280, 380, 910, 520),
    (280, 580, 910, 720),
    (280, 780, 910, 930),
)


class FutureFlowHomeFrame(ctk.CTkFrame):
    def __init__(self, master, navigate, **kwargs):
        super().__init__(master, fg_color="#1a0b25", **kwargs)
        self.navigate = navigate
        self.canvas = Canvas(self, background="#1a0b25", highlightthickness=0)
        self.canvas.place(relwidth=1, relheight=1)
        self.canvas.bind("<Configure>", self._render_image)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _event: self.canvas.configure(cursor=""))
        self.canvas.bind("<Button-1>", self._on_click)
        self.photo = None
        self.image_scale = 1.0
        self.image_offset = (0, 0)

    def _render_image(self, event):
        width, height = max(event.width, 1), max(event.height, 1)
        source_width, source_height = 1362, 959
        self.image_scale = min(width / source_width, height / source_height)
        display_size = (
            max(1, round(source_width * self.image_scale)),
            max(1, round(source_height * self.image_scale)),
        )
        svg_bytes = svg_to_bytes(
            svg_path=str(HOME_SVG),
            width=display_size[0],
            height=display_size[1],
            shape_rendering="geometric_precision",
            text_rendering="optimize_legibility",
        )
        rendered_image = Image.open(BytesIO(svg_bytes)).convert("RGBA")
        self.photo = ImageTk.PhotoImage(rendered_image, master=self.canvas)
        self.image_offset = ((width - display_size[0]) / 2, (height - display_size[1]) / 2)
        self.canvas.delete("all")
        self.canvas.create_image(*self.image_offset, anchor="nw", image=self.photo)

    def _destination_at(self, event):
        x = (self.canvas.canvasx(event.x) - self.image_offset[0]) / self.image_scale
        y = (self.canvas.canvasy(event.y) - self.image_offset[1]) / self.image_scale
        for (x0, y0, x1, y1), (_label, destination) in zip(MENU_HOTSPOTS, MENU_ITEMS):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return destination
        return None

    def _on_motion(self, event):
        self.canvas.configure(cursor="hand2" if self._destination_at(event) else "")

    def _on_click(self, event):
        destination = self._destination_at(event)
        if destination:
            self.navigate(destination)


class FutureFlowProfileFrame(ctk.CTkFrame):
    def __init__(self, master, navigate, **kwargs):
        super().__init__(master, **kwargs)
        self.navigate = navigate
        ctk.CTkLabel(self, text="PROFILE", font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=22, pady=(18, 14)
        )
        self.summary = ctk.CTkLabel(self, text="", anchor="w", justify="left")
        self.summary.pack(anchor="w", padx=22, pady=8)
        ctk.CTkButton(self, text="Otwórz aktywne zadania", command=lambda: self.navigate("Tasks")).pack(
            anchor="w", padx=22, pady=(14, 4)
        )
        ctk.CTkButton(self, text="Wróć do FutureFlow", fg_color="transparent", command=lambda: self.navigate("Home")).pack(
            anchor="w", padx=22, pady=4
        )
        self.refresh()

    def refresh(self):
        try:
            active_count = len(read_task_records(ACTIVE_TASKS_FILE))
            completed_count = len(read_task_records(ARCHIVED_TASKS_FILE))
            feedback_count = len(read_task_records(TASK_FEEDBACK_FILE))
            text = (
                f"Aktywne taski     {active_count}\n"
                f"Ukończone taski   {completed_count}\n"
                f"Zapisane ankiety  {feedback_count}"
            )
        except (OSError, ValueError):
            text = "Nie można wczytać podsumowania profilu."
        self.summary.configure(text=text)