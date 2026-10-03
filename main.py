import json

import customtkinter as ctk

from calendar import CalendarFrame
from task import Task, TaskFrame
from tag import Tag
from week_periods import WeeklySchedule





current_tasks_list = []
done_tasks_list = []
tags_list = []
weeklySheadule_list = []
past_weeklySheadule_list = []


def save_list_to_json(data_list, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data_list, file, ensure_ascii=False, indent=4)


def read_list_from_json(data_list, file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            loaded_data = json.load(file)
    except FileNotFoundError:
        return data_list

    if not isinstance(loaded_data, list):
        raise ValueError(f"Expected a JSON list in {file_path}")

    data_list.clear()
    data_list.extend(loaded_data)
    return data_list


if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    window = ctk.CTk()
    window.title("Task Manager")
    window.geometry("900x600")
    window.minsize(700, 500)

    tabview = ctk.CTkTabview(window)
    tabview.pack(fill="both", expand=True, padx=20, pady=20)

    tabview.add("Add Task")
    tabview.add("Add Tag")
    tabview.add("Calendar")
    tabview.add("Preferences")



    ########################################################################    ADD TASK
    add_task_frame = ctk.CTkFrame(tabview.tab("Add Task"))
    add_task_frame.pack(fill="both", expand=True, padx=10, pady=10)

    tags = [Tag(0, "aaa", (0, 0, 0), True)]
    def llm_autofill():
        print("działa llm autofill")
        return 0

    task = TaskFrame(add_task_frame, tags, llm_autofill)
    task.pack(fill="both", expand=True, padx=10, pady=10)


    ######################################################################### ADD TAG
    add_tag_frame = ctk.CTkFrame(tabview.tab("Add Tag"))
    add_tag_frame.pack(fill="both", expand=True, padx=10, pady=10)






    ########################################################################    CALENDAR
    calendar_frame = ctk.CTkFrame(tabview.tab("Calendar"))
    calendar_frame.pack(fill="both", expand=True, padx=10, pady=10)

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
    ctk.CTkLabel(preferences_frame, text="Preferences").pack(pady=20)

    window.mainloop()






    # Osadzenie kalendarza jako zwykły widget
    # calendar = WeeklyCalendarFrame(
    #     master=window,
    #     start_hour=8,
    #     end_hour=17,
    #     command=my_task_click_handler
    # )
    # calendar.pack(fill="both", expand=True, padx=10, pady=10)