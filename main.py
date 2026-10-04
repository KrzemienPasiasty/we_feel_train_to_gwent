import json

try:
    import tkinter  # noqa: F401 - required by customtkinter
    import customtkinter as ctk
except ModuleNotFoundError as exc:
    raise SystemExit(
        "This project needs a Python build with Tkinter support. "
        "Use 'py -3.14 main.py' or install a full Python distribution that includes tkinter. "
        "Then run: py -3.14 -m pip install -r requirements.txt"
    ) from exc

from calendar_my import CalendarFrame
from sync_ui import SyncFrame
from task import Task, TaskFrame
from tag import Tag
from week_periods import WeeklySchedule
from task_views import ActiveTasksFrame
from tag_calendar import TagManagerFrame, TagCalendarFrame, load_tags
from home_ui import FutureFlowHomeFrame, FutureFlowProfileFrame











if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("green")

    window = ctk.CTk()
    window.title("FutureFlow")
    window.geometry("900x600")
    window.minsize(700, 500)
    load_tags()

    tabview = ctk.CTkTabview(window)
    tabview.pack(fill="both", expand=True, padx=20, pady=20)

    tabview.add("Home")
    tabview.add("Profile")
    tabview.add("Add Task")
    tabview.add("Add Tag")
    tabview.add("Calendar")
    tabview.add("Preferences")
    tabview.add("Tasks")

    home = FutureFlowHomeFrame(tabview.tab("Home"), navigate=tabview.set)
    home.pack(fill="both", expand=True)
    profile = FutureFlowProfileFrame(tabview.tab("Profile"), navigate=tabview.set)
    profile.pack(fill="both", expand=True)



    ########################################################################    ADD TASK
    add_task_frame = ctk.CTkFrame(tabview.tab("Add Task"))
    add_task_frame.pack(fill="both", expand=True, padx=10, pady=10)

    tags = [Tag(0, "aaa", (0, 0, 0), True)]
    def llm_autofill():
        print("działa llm autofill")
        return 0

    tasks_frame = ctk.CTkFrame(tabview.tab("Tasks"))
    tasks_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh_task_views():
        active_tasks_panel.refresh()
        profile.refresh()

    active_tasks_panel = ActiveTasksFrame(tasks_frame, on_data_changed=profile.refresh)
    active_tasks_panel.pack(fill="both", expand=True)

    task = TaskFrame(add_task_frame, on_task_added=refresh_task_views)
    task.pack(fill="both", expand=True, padx=10, pady=10)


    ######################################################################### ADD TAG
    add_tag_frame = ctk.CTkFrame(tabview.tab("Add Tag"))
    add_tag_frame.pack(fill="both", expand=True, padx=10, pady=10)
    tag_manager = TagManagerFrame(add_tag_frame)
    tag_manager.pack(fill="both", expand=True)






    ########################################################################    CALENDAR
    calendar_frame = ctk.CTkFrame(tabview.tab("Calendar"))
    calendar_frame.pack(fill="both", expand=True, padx=10, pady=10)
    state_calendar = TagCalendarFrame(calendar_frame)
    state_calendar.pack(fill="both", expand=True)
    pending_calendar_slot = [None]

    def open_tag_creation(day, slot):
        pending_calendar_slot[0] = (day, slot)
        tabview.set("Add Tag")
        tag_manager.prepare_new_tag()

    def refresh_tag_views(changed_tag=None, is_new=False):
        state_calendar.refresh_tags()
        task.refresh_tags()
        if changed_tag:
            state_calendar.select_tag(changed_tag.id)
            if is_new and pending_calendar_slot[0]:
                day, slot = pending_calendar_slot[0]
                if changed_tag.id not in state_calendar.states.get((day, slot), []):
                    state_calendar._toggle(day, slot, changed_tag.id)
                pending_calendar_slot[0] = None

    state_calendar.on_create_tag = open_tag_creation
    tag_manager.on_tags_changed = refresh_tag_views
    refresh_tag_views()

    def my_task_click_handler(task_data: dict):         ####################TEMP
        """Funkcja callback wywoływana po kliknięciu w task."""
        print("\n[EVENT] Kliknięto task!")
        print(f"ID: {task_data.get('id')}")
        print(f"Tytuł: {task_data.get('title')}")
        print(f"Priorytet: {task_data.get('priority')}")
        print(f"Dane pełne: {task_data}")

    # t = task()
    # calendar = CalendarFrame(calendar_frame, )



    ########################################################################    PREFERENCES
    preferences_frame = ctk.CTkFrame(tabview.tab("Preferences"))
    preferences_frame.pack(fill="both", expand=True, padx=10, pady=10)











    ########################################################################
    ctk.CTkLabel(add_task_frame, text="Add Task").pack(pady=20)
    ctk.CTkLabel(calendar_frame, text="Calendar").pack(pady=20)
    sync_panel = SyncFrame(preferences_frame, on_data_changed=refresh_task_views)
    sync_panel.pack(fill="both", expand=True, padx=20, pady=20)

    window.mainloop()
