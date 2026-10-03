import json
from xmlrpc.client import DateTime
from tag import Tag # Zakładamy, że ten plik (tag.py) istnieje obok

from task import Task # Zakładamy, że ten plik (task.py) istnieje obok

def fill_task(empty_task: Task, task_data: dict) -> Task:
    """
    Funkcja przyjmująca pusty obiekt Task i napełniająca go danymi ze słownika.
    """
    empty_task.id = task_data.get("id", 0)
    empty_task.description = task_data.get("description", "")
    empty_task.focus = task_data.get("focus", 0)
    empty_task.priority = task_data.get("priority", 1)
    empty_task.llm_metadata = task_data.get("llm_metadata", "")
    
    # 1. Mapowanie 'deadline' na obiekt DateTime
    deadline_str = task_data.get("deadline", "1970-01-01T00:00:00")
    # DateTime poprawnie zinterpretuje stringa w formacie ISO 8601
    empty_task.deadline = DateTime(deadline_str)
    
    # 2. Mapowanie 'time' (samo HH:MM:SS) na obiekt DateTime
    time_str = task_data.get("time", "00:00:00")
    # Doklejamy sztuczną datę początkową, ponieważ DateTime musi mieć rok/miesiąc/dzień
    empty_task.time = DateTime(f"1970-01-01T{time_str}")
    
    # 3. Mapowanie słowników tagów na obiekty klasy Tag
    raw_tags = task_data.get("tags", [])
    for tag_dict in raw_tags:
        # Zakładam, że klasa Tag przyjmuje 'name' w konstruktorze lub można to przypisać w ten sposób.
        # Jeśli twoja klasa Tag działa inaczej, dostosuj poniższe 2 linijki:
        new_tag = Tag()          # Zakładamy, że Tag też wymaga pustego inicjatora
        new_tag.name = tag_dict.get("name", "")
        empty_task.tags.append(new_tag)
        
    return empty_task

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

# --- PRZYKŁAD UŻYCIA (możesz to usunąć, jeśli nie potrzebujesz odpalać tego piku jako skryptu) ---
if __name__ == "__main__":
    # Testujemy załadowanie z JSON-a
    tasks_list = load_tasks_from_json('output.json')
    
    print(f"Załadowano {len(tasks_list)} obiektów Task.")
    if tasks_list:
        pierwszy_task = tasks_list[0]
        print(f"ID: {pierwszy_task.id}")
        print(f"Opis: {pierwszy_task.description}")
        print(f"Tagi: {[t.name for t in pierwszy_task.tags]}")
        print(f"Deadline (obiekt DateTime): {pierwszy_task.deadline}")