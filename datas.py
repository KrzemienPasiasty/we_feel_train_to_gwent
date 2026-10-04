import json
from tag import Tag
from task import Task
from llm import process_tasks_file
from week_periods import WeekTime

current_tasks_list: list[Task] = []
done_tasks_list: list[Task] = []
tags_list: list[Tag] = []
weekly_schedule_list: list[WeekTime] = []


def save_list_to_json(data_list, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        # Obsługa obiektów klas posiadających metodę to_dict lub atrybut __dict__
        serialized_data = [
            item.to_dict() if hasattr(item, "to_dict") else (item.__dict__ if hasattr(item, "__dict__") else item)
            for item in data_list
        ]
        json.dump(serialized_data, file, ensure_ascii=False, indent=4)


def _deserialize_item(item_data: dict):
    """
    Twierdzenie o parsowaniu typów:
    Jeżeli obiekt JSON (słownik) posiada unikalny zestaw kluczy odpowiadający strukturze
    danej klasy, można go jednoznacznie zmapować na instancję tej klasy.
    """
    if not isinstance(item_data, dict):
        return item_data

    # Tworzenie obiektu Task (gdy posiada klucz właściwy dla zadań, np. 'title', 'name' lub 'is_done')
    if "is_done" in item_data or "autofill_focus" in item_data:
        if hasattr(Task, "from_dict"):
            return Task.from_dict(item_data)
        task = Task()
        for key, value in item_data.items():
            if hasattr(task, key):
                setattr(task, key, value)
        return task

    # Tworzenie obiektu Tag (gdy posiada właściwości dla znaczników, np. 'tag_name', 'color')
    elif "tag_name" in item_data or "color" in item_data:
        if hasattr(Tag, "from_dict"):
            return Tag.from_dict(item_data)
        return Tag(**item_data) if hasattr(Tag, "__init__") else item_data

    # Tworzenie obiektu WeekTime (gdy posiada właściwości dla harmonogramu)
    elif "day" in item_data or "start_time" in item_data:
        if hasattr(WeekTime, "from_dict"):
            return WeekTime.from_dict(item_data)
        return WeekTime(**item_data) if hasattr(WeekTime, "__init__") else item_data

    return item_data


def load_data_from_json(file_path: str, target_list: list = None) -> list:
    """
    Pobiera plik JSON zadanego w parametrze 'file_path', parsuje go na listę
    odpowiednich struktur (Task, Tag, WeekTime) i uaktualnia właściwą listę globalną.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            loaded_data = json.load(file)
    except FileNotFoundError:
        print(f"Plik {file_path} nie istnieje.")
        return []

    if not isinstance(loaded_data, list):
        raise ValueError(f"Oczekiwano listy JSON w pliku {file_path}")

    # Deserializacja elementów do struktur obiektowych
    parsed_objects = [_deserialize_item(item) for item in loaded_data]

    if parsed_objects:
        first_item = parsed_objects[0]

        # Automatyczne przypisanie do odpowiedniej listy globalnej na podstawie typu obiektów
        if isinstance(first_item, Task):
            # Podział na zadania wykonane i niewykonane (jeśli występuje pole is_done)
            target = current_tasks_list if target_list is None else target_list
            target.clear()
            for task in parsed_objects:
                if getattr(task, "is_done", False):
                    done_tasks_list.append(task)
                else:
                    target.append(task)
        elif isinstance(first_item, Tag):
            target = tags_list if target_list is None else target_list
            target.clear()
            target.extend(parsed_objects)
        elif isinstance(first_item, WeekTime):
            target = weekly_schedule_list if target_list is None else target_list
            target.clear()
            target.extend(parsed_objects)
        else:
            if target_list is not None:
                target_list.clear()
                target_list.extend(parsed_objects)

    return parsed_objects


def add_task(task: Task, autofill_focus, autofill_time):
    if autofill_focus or autofill_time:
        print("AAAAAAAA")
        task = fill_task(task, autofill_focus, autofill_time)
    print("BBBBBBBBBBBBBb")
    current_tasks_list.append(task)

    save_list_to_json(current_tasks_list, "aaa.json")


def load_tasks_from_json(json_filepath: str) -> list[Task]:
    """
    Otwiera plik wynikowy JSON z LLM, tworzy obiekty Task i je wypełnia.
    """
    with open(json_filepath, 'r', encoding='utf-8') as f:
        all_tasks_data = json.load(f)

    filled_tasks = []

    for item in all_tasks_data:
        task_instance = Task()
        filled_task = fill_task(task_instance, item)
        filled_tasks.append(filled_task)

    return filled_tasks


def fill_task(task: Task, autofill_focus, autofill_time) -> Task:
    """
    Automatyzuje cały proces: zapis do pliku, call AI, odczyt i mapowanie.
    """
    print("2. Uruchamiam sztuczną inteligencję (llm.py)...")
    task = process_tasks_file(task, autofill_focus, autofill_time)

    print("datas.py 88 działa")
    print(task)
    return task