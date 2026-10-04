import json

import customtkinter as ctk

from calendar_my import CalendarFrame
from task import Task, TaskFrame
from tag import Tag
from week_periods import WeeklySchedule











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

    task = TaskFrame(add_task_frame)
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