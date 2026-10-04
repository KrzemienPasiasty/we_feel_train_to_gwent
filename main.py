import json
import customtkinter as ctk

from ui import CalendarFrame, TaskListFrame, TaskFrame, PreferencesFrame, TagManagementFrame
from sync_ui import SyncFrame
from models import Task, Tag, WeekTime
import datas


def create_app():
    # 1. Wczytanie danych z plików JSON
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
    if not datas.weekly_schedule_list:
        datas.weekly_schedule_list.append(WeekTime())

    try:
        datas.load_scheduled_meals_from_json(datas.scheduled_meals_list, "meals.json")
    except Exception:
        pass
    try:
        datas.load_trainings_from_json(datas.trainings_list, "trainings.json")
    except Exception:
        pass

    # 2. Konfiguracja motywu w stylistyce FUTUREFLOW
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    window = ctk.CTk()
    window.title("FUTUREFLOW — Task Manager & AI Calendar")
    window.geometry("1100x760")
    window.minsize(900, 600)

    # 3. Górny pasek brandingowy FUTUREFLOW
    brand_bar = ctk.CTkFrame(window, fg_color=("gray90", "#181422"), height=48, corner_radius=0)
    brand_bar.pack(fill="x", side="top")

    logo_box = ctk.CTkFrame(brand_bar, fg_color="transparent")
    logo_box.pack(side="left", padx=16, pady=8)

    ctk.CTkLabel(
        logo_box,
        text="🟣 FUTUREFLOW",
        font=ctk.CTkFont(size=19, weight="bold"),
        text_color="#E169FF",
    ).pack(side="left")

    ctk.CTkLabel(
        logo_box,
        text="  |  AI-POWERED SCHEDULE & TASK OPTIMIZER",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color=("gray50", "#9c92ab"),
    ).pack(side="left")

    status_sync_lbl = ctk.CTkLabel(
        brand_bar,
        text="● System aktywny",
        font=ctk.CTkFont(size=11),
        text_color="#4caf50",
    )
    status_sync_lbl.pack(side="right", padx=16)

    # 4. Główne zakładki aplikacji (Styl FUTUREFLOW Neon)
    tabview = ctk.CTkTabview(
        window,
        segmented_button_selected_color="#E169FF",
        segmented_button_selected_hover_color="#D83CFF",
        segmented_button_unselected_color=("gray85", "#261f33"),
        segmented_button_unselected_hover_color=("gray75", "#382e4a"),
        text_color="white",
    )
    tabview.pack(fill="both", expand=True, padx=12, pady=(4, 12))

    # Zakładki
    tabview.add("Current Tasks")
    tabview.add("Calendar")
    tabview.add("Add Task")
    tabview.add("Add Tag")
    tabview.add("Preferences")
    tabview.add("Integrations")

    # Callbacks do synchronizacji między widokami
    def on_tags_globally_changed():
        """Wywoływane, gdy tag został dodany, zmieniony lub usunięty."""
        task_frame.refresh_tags()
        tag_mgmt_view.refresh()
        calendar_view.refresh()
        task_list_view.refresh_tasks()

    ######################################################################## CURRENT TASKS
    current_tasks_frame = ctk.CTkFrame(tabview.tab("Current Tasks"), fg_color="transparent")
    current_tasks_frame.pack(fill="both", expand=True, padx=4, pady=4)

    task_list_view = TaskListFrame(
        current_tasks_frame,
        on_add_task_click=lambda: tabview.set("Add Task"),
    )
    task_list_view.pack(fill="both", expand=True)

    ######################################################################## CALENDAR
    calendar_frame = ctk.CTkFrame(tabview.tab("Calendar"), fg_color="transparent")
    calendar_frame.pack(fill="both", expand=True, padx=4, pady=4)

    calendar_view = CalendarFrame(
        calendar_frame,
        is_weekly_view=True,
        on_schedule_updated=lambda: (task_list_view.refresh_tasks(), on_tags_globally_changed()),
    )
    calendar_view.pack(fill="both", expand=True)

    ######################################################################## ADD TASK
    add_task_frame = ctk.CTkFrame(tabview.tab("Add Task"), fg_color="transparent")
    add_task_frame.pack(fill="both", expand=True, padx=6, pady=6)

    def on_task_added_callback(new_task):
        task_list_view.refresh_tasks()
        calendar_view.refresh()
        tabview.set("Current Tasks")

    task_frame = TaskFrame(add_task_frame, on_task_added=on_task_added_callback)
    task_frame.pack(fill="both", expand=True)

    ######################################################################## ADD TAG (TAG MANAGEMENT)
    add_tag_frame = ctk.CTkFrame(tabview.tab("Add Tag"), fg_color="transparent")
    add_tag_frame.pack(fill="both", expand=True, padx=6, pady=6)

    tag_mgmt_view = TagManagementFrame(
        add_tag_frame,
        on_tags_updated=on_tags_globally_changed,
    )
    tag_mgmt_view.pack(fill="both", expand=True)

    ######################################################################## PREFERENCES
    preferences_frame = ctk.CTkFrame(tabview.tab("Preferences"), fg_color="transparent")
    preferences_frame.pack(fill="both", expand=True, padx=6, pady=6)

    pref_view = PreferencesFrame(
        preferences_frame,
        on_theme_change=lambda: (task_list_view.refresh_tasks(), calendar_view.refresh()),
    )
    pref_view.pack(fill="both", expand=True)

    ######################################################################## INTEGRATIONS
    integrations_view = SyncFrame(
        tabview.tab("Integrations"),
        on_data_changed=lambda: (task_list_view.refresh_tasks(), calendar_view.refresh()),
    )
    integrations_view.pack(fill="both", expand=True, padx=6, pady=6)

    # Initial refresh
    task_list_view.refresh_tasks()
    calendar_view.refresh()

    return window


if __name__ == "__main__":
    app = create_app()
    app.mainloop()
