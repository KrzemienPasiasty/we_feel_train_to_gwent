import json
from xmlrpc.client import DateTime
from tag import Tag # Zakładamy, że ten plik (tag.py) istnieje obok

from task import Task # Zakładamy, że ten plik (task.py) istnieje obok
from llm import process_tasks_file

<<<<<<< HEAD
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
    current_tasks_list.append(task)







=======
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
        # POPRAWKA: Przekazujemy nazwę taga do nawiasu, żeby nie było błędu z inicjatorem
        tag_name = tag_dict.get("name", "")
        new_tag = Tag(tag_name)
        empty_task.tags.append(new_tag)
        
    return empty_task
>>>>>>> 61f7828 (task creation developed, date chooser better, datas moved to datas)

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
<<<<<<< HEAD


    print("2. Uruchamiam sztuczną inteligencję (llm.py)...")
    # Callujemy Twoją funkcję z pliku llm.py
    task = process_tasks_file(task, autofill_focus, autofill_time )

    print("datas.py 88 działa")
    print(task)
    return task
=======
    print("\n1. Zapisuję surowe dane do 'input.json'...")
    with open('input.json', 'w', encoding='utf-8') as f:
        json.dump(surowe_zadania, f, indent=4, ensure_ascii=False)

    print("2. Uruchamiam sztuczną inteligencję (llm.py)...")
    # Callujemy Twoją funkcję z pliku llm.py
    process_tasks_file('input.json', 'output.json', 'ai_thoughts.md')

    print("3. Pobieram dane z 'output.json' i tworzę pełne obiekty Task...")
    gotowe_obiekty = load_tasks_from_json('output.json')

    return gotowe_obiekty


# --- PRZYKŁAD UŻYCIA ---
if __name__ == "__main__":

    # Tworzymy symulowane, surowe wejście (zadanie, w którym AI musi wymyślić czas, focus i priorytet)
    testowe_zadanie = [{
        "id": 999,
        "title": "Zaplanować urlop",
        "description": "Kupić bilety do Włoch i wynająć hotel",
        "tags": [{"name": "Zarządzanie Finansami"}, {"name": "Regeneracja"}]
    }]
    
    print("ROZPOCZYNAM GŁÓWNY PROCES:")

    # CALLUJEMY NASZĄ NOWĄ FUNKCJĘ
    wynikowe_taski = process_and_load_tasks(testowe_zadanie)

    # WYPISUJEMY GOTOWY OBIEKT:
    if wynikowe_taski:
        pelen_task = wynikowe_taski[0]
        print("\n=== ZAKOŃCZONO SUKCESEM. GOTOWY OBIEKT: ===")
        print(f"ID:           {pelen_task.id}")
        print(f"Opis:         {pelen_task.description}")

        # Uwaga: używam getattr() żeby obsłużyć zarówno `tag.name` jak i `tag.tag` (zależnie jak to masz w tag.py)
        print(f"Tagi:         {[getattr(t, 'name', getattr(t, 'tag', '')) for t in pelen_task.tags]}")

        print(f"Czas z AI:    {pelen_task.time}")
        print(f"Focus z AI:   {pelen_task.focus}")
        print(f"Priorytet AI: {pelen_task.priority}")
        print(f"Metadane:     {pelen_task.llm_metadata}")
>>>>>>> 61f7828 (task creation developed, date chooser better, datas moved to datas)
