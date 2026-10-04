import json
import customtkinter as ctk

from ui import CalendarFrame, TaskListFrame, TaskFrame
from models import Task, Tag, WeekTime
import datas


if __name__ == "__main__":
    # Wczytanie danych z plików JSON
    datas.load_tags_list_from_json(datas.tags_list, "tags.json")
    datas.load_current_tasks_list_from_json(datas.current_tasks_list, "current_tasks.json")
    if not datas.current_tasks_list:
        try:
            datas.load_current_tasks_list_from_json(datas.current_tasks_list, "tasks_active.json")
        except Exception:
            pass
    datas.load_done_tasks_list_from_json(datas.done_tasks_list, "tasks_archived.json")
    try:
        datas.load_weekly_schedule_list_from_json(datas.weekly_schedule_list, "week_time.json")
    except Exception:
        pass

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    window = ctk.CTk()
    window.title("Task Manager")
    window.geometry("1000x700")
    window.minsize(800, 550)

    tabview = ctk.CTkTabview(window)
    tabview.pack(fill="both", expand=True, padx=15, pady=15)

    # Tabs
    tabview.add("Current Tasks")
    tabview.add("Add Task")
    tabview.add("Add Tag")
    tabview.add("Calendar")
    tabview.add("Preferences")

    ########################################################################    CURRENT TASKS
    current_tasks_frame = ctk.CTkFrame(tabview.tab("Current Tasks"))
    current_tasks_frame.pack(fill="both", expand=True, padx=5, pady=5)

    task_list_view = TaskListFrame(
        current_tasks_frame,
        on_add_task_click=lambda: tabview.set("Add Task"),
    )
    task_list_view.pack(fill="both", expand=True)

    ########################################################################    CALENDAR
    calendar_frame = ctk.CTkFrame(tabview.tab("Calendar"))
    calendar_frame.pack(fill="both", expand=True, padx=5, pady=5)

    calendar_view = CalendarFrame(
        calendar_frame,
        is_weekly_view=True,
        on_schedule_updated=lambda: task_list_view.refresh_tasks(),
    )
    calendar_view.pack(fill="both", expand=True)

    ########################################################################    ADD TASK
    add_task_frame = ctk.CTkFrame(tabview.tab("Add Task"))
    add_task_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def on_task_added_callback(new_task):
        task_list_view.refresh_tasks()
        calendar_view.refresh()
        tabview.set("Current Tasks")

    task_frame = TaskFrame(add_task_frame, on_task_added=on_task_added_callback)
    task_frame.pack(fill="both", expand=True, padx=10, pady=10)

    #########################################################################   ADD TAG
    add_tag_frame = ctk.CTkFrame(tabview.tab("Add Tag"))
    add_tag_frame.pack(fill="both", expand=True, padx=10, pady=10)
    ctk.CTkLabel(
        add_tag_frame,
        text="Zarządzanie tagami (Add Tag)",
        font=ctk.CTkFont(size=20, weight="bold"),
    ).pack(pady=20)

    ########################################################################    PREFERENCES
    preferences_frame = ctk.CTkFrame(tabview.tab("Preferences"))
    preferences_frame.pack(fill="both", expand=True, padx=10, pady=10)
    ctk.CTkLabel(
        preferences_frame,
        text="Ustawienia (Preferences)",
        font=ctk.CTkFont(size=20, weight="bold"),
    ).pack(pady=20)

    # Initial refresh with loaded data
    task_list_view.refresh_tasks()
    calendar_view.refresh()

    window.mainloop()
