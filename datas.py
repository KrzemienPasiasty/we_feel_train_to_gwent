import json
from xmlrpc.client import DateTime
from tag import Tag # Zakładamy, że ten plik (tag.py) istnieje obok

from task import Task # Zakładamy, że ten plik (task.py) istnieje obok
from llm import process_tasks_file
from task_lifecycle import persist_new_task

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


def add_task(task: Task, autofill_focus, autofill_time):
    if autofill_focus or autofill_time:
        print("AAAAAAAA")
        task = fill_task(task,  autofill_focus, autofill_time)
    print("BBBBBBBBBBBBBb")
    persist_new_task(task)
    current_tasks_list.append(task)
    return task


def load_tasks_from_json(json_filepath: str) -> list[Task]:
    """
    Otwiera plik wynikowy JSON z LLM, tworzy puste obiekty Task i je wypełnia.
    """
    with open(json_filepath, 'r', encoding='utf-8') as f:
        all_tasks_data = json.load(f)

    filled_tasks = []

    for item in all_tasks_data:
        # 1. Tworzymy "niezapełniony" obiekt
        task_instance = Task()

        # 2. Wypełniamy obiekt naszą funkcją
        filled_task = fill_task(task_instance, item)

        # 3. Dodajemy do gotowej listy
        filled_tasks.append(filled_task)

    return filled_tasks

# ========================================================================
# NOWA FUNKCJA: KOMPLETNY PROCES (ZAPIS -> CALL LLM.PY -> ODCZYT DO RAM)
# ========================================================================
def fill_task(task: Task, autofill_focus, autofill_time) -> Task:
    """
    Automatyzuje cały proces: zapis do pliku, call AI, odczyt i mapowanie.
    """

    print("2. Uruchamiam sztuczną inteligencję (llm.py)...")
    # Callujemy Twoją funkcję z pliku llm.py
    task = process_tasks_file(task, autofill_focus, autofill_time )

    print("datas.py 88 działa")
    print(task)
    return task
