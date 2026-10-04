import json
import customtkinter as ctk

from ui import CalendarFrame, TaskListFrame, TaskFrame
from models import Task, Tag, WeekTime
import datas










if __name__ == "__main__":
    # DATA_FILES = {
    #     "tasks_active.json": datas.current_tasks_list,
    #     "tasks_archived.json": datas.done_tasks_list,
    #     "tags.json": datas.tags_list,
    #     "week_time.json": datas.weekly_schedule_list,
    # }
    #
    # """Wczytuje dane z plików JSON do list z datas.py."""
    # for file_path, data_list in DATA_FILES.items():
    #     datas.load_data_from_json(file_path, data_list)
    # print(datas.current_tasks_list)
    # print(datas.done_tasks_list)
    # print(datas.tags_list)
    # print(datas.weekly_schedule_list)

    datas.load_data_from_json("tags.json", datas.tags_list)






    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    window = ctk.CTk()
    window.title("Task Manager")
    window.geometry("900x600")
    window.minsize(700, 500)

    tabview = ctk.CTkTabview(window)
    tabview.pack(fill="both", expand=True, padx=20, pady=20)

    # Tabs
    tabview.add("Current Tasks")
    tabview.add("Add Task")
    tabview.add("Add Tag")
    tabview.add("Calendar")
    tabview.add("Preferences")

    ########################################################################    CURRENT TASKS
    current_tasks_frame = ctk.CTkFrame(tabview.tab("Current Tasks"))
    current_tasks_frame.pack(fill="both", expand=True, padx=10, pady=10)

    task_list_view = TaskListFrame(
        current_tasks_frame,
        on_add_task_click=lambda: tabview.set("Add Task"),
    )
    task_list_view.pack(fill="both", expand=True)

    ########################################################################    ADD TASK
    add_task_frame = ctk.CTkFrame(tabview.tab("Add Task"))
    add_task_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def on_task_added_callback(new_task):
        task_list_view.refresh_tasks()
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

    ########################################################################    CALENDAR
    calendar_frame = ctk.CTkFrame(tabview.tab("Calendar"))
    calendar_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def my_task_click_handler(task_data: dict):
        """Funkcja callback wywoływana po kliknięciu w task."""
        print("\n[EVENT] Kliknięto task!")
        print(f"ID: {task_data.get('id')}")
        print(f"Tytuł: {task_data.get('title')}")
        print(f"Priorytet: {task_data.get('priority')}")
        print(f"Dane pełne: {task_data}")


    # calendar = CalendarFrame(calendar_frame, )
    # calendar.pack(fill="both", expand=True, padx=10, pady=10)



    ########################################################################    PREFERENCES
    preferences_frame = ctk.CTkFrame(tabview.tab("Preferences"))
    preferences_frame.pack(fill="both", expand=True, padx=10, pady=10)
    ctk.CTkLabel(
        preferences_frame,
        text="Preferencje (Preferences)",
        font=ctk.CTkFont(size=20, weight="bold"),
    ).pack(pady=20)

    # Set default tab to Current Tasks
    tabview.set("Current Tasks")

    window.mainloop()
