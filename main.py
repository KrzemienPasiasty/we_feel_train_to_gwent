import json

import customtkinter as ctk

import calender


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
    window = calender.Calender()
    window.mainloop()
