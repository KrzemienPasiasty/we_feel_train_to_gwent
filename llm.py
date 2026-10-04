import json
from pydantic import BaseModel, Field
from openai import OpenAI

# Twój klucz API
client = OpenAI(
    api_key="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"
)

# Tagi dostępne w systemie (jeśli chcesz je wysyłać w prompcie, możesz to zrobić w przyszłości)
AVAILABLE_USER_TAGS = [
    "Zarządzanie Finansami", 




   
]

class AIPrediction(BaseModel):
    time: str = Field(description="Oszacowany czas w formacie HH:MM:SS (lub przepisany, jeśli podano).")
    focus: int = Field(description="Wymagane skupienie w skali od -5 do 5.")
    priority: int = Field(description="Priorytet / trudność od 1 do 5.")
    llm_metadata: str = Field(description="Krótkie uzasadnienie szacunków.")

def process_tasks_file(input_filepath: str, output_filepath: str, thoughts_filepath: str):
    """
    Czyta plik input.json, dla zadań z brakującymi polami wysyła zapytanie do OpenAI,
    i zapisuje pełne dane do output.json oraz logiki decyzyjne do ai_thoughts.md.
    """
    with open(input_filepath, 'r', encoding='utf-8') as f:
        all_tasks = json.load(f)

    final_tasks = []
    thoughts_log = "# Dziennik Przemyśleń AI na temat zadań\n\n"

    for task in all_tasks:
        # 1. Tworzenie spójnego opisu zadania
        t_title = task.get('title', '').strip()
        t_desc = task.get('description', '').strip()
        if t_title and t_desc:
            merged_description = f"{t_title} - {t_desc}"
        elif t_title:
            merged_description = t_title
        else:
            merged_description = t_desc or "Zadanie bez nazwy"

        # 2. Sprawdzanie, których pól brakuje
        user_time = task.get('time')
        user_focus = task.get('focus')
        user_priority = task.get('priority')

        has_time = bool(user_time)
        has_focus = user_focus is not None
        has_priority = user_priority is not None

        # Jeśli brakuje chociaż jednego – włączamy AI
        needs_prediction = not (has_time and has_focus and has_priority)

        if needs_prediction:
            print(f"Analizuję zadanie: '{merged_description}' (uzupełniam braki)...")
            
            prompt = f"""
            Jesteś inteligentnym systemem planowania. Otrzymujesz zadanie użytkownika.
            Twoim celem jest przewidzieć TYLKO te wartości, których użytkownik nie podał:
            (czas trwania, wymagane skupienie, priorytet/trudność) na podstawie dostępnych danych.
            
            DANE ZADANIA:
            - Tytuł/Opis: {merged_description}
            - Tagi: {task.get('tags') or 'Brak'}
            
            DANE DO UZUPEŁNIENIA / ZACHOWANIA:
            - Czas (time): {user_time if has_time else 'BRAK - Oszacuj w formacie HH:MM:SS (np. 00:15:00)'}
            - Skupienie (focus): {user_focus if has_focus else 'BRAK - Oszacuj w skali od -5 do 5 (-5=całkowity luz/rutyna, 0=neutralne, 5=głęboka praca)'}
            - Priorytet/Trudność (priority): {user_priority if has_priority else 'BRAK - Oszacuj w skali 1-5'}
            
            ZASADY:
            1. Jeśli w polu 'DANE DO UZUPEŁNIENIA' podano konkretną liczbę lub czas zamiast 'BRAK', ZACHOWAJ JĄ i zwróć bez zmian.
            2. Przewiduj mądrze na podstawie opisu zadania.
            3. W 'llm_metadata' krótko uzasadnij swoje szacunki. Bądź analityczny.
            """

            completion = client.beta.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Zwracaj tylko ustrukturyzowany model AIPrediction. Nie edytujesz innych danych, tylko uzupełniasz luki."},
                    {"role": "user", "content": prompt}
                ],
                response_format=AIPrediction,
            )
            
            ai_data = completion.choices[0].message.parsed
            
            final_time = user_time if has_time else ai_data.time
            final_focus = user_focus if has_focus else ai_data.focus
            final_priority = user_priority if has_priority else ai_data.priority
            final_metadata = ai_data.llm_metadata
            
            # Notowanie przemyśleń
            thoughts_log += f"## 📝 {merged_description}\n"
            thoughts_log += f"- **Wygenerowano:** Czas: `{final_time}` | Skupienie: `{final_focus}` | Priorytet: `{final_priority}`\n"
            thoughts_log += f"- **Przemyślenia AI:** {final_metadata}\n\n"
            
        else:
            print(f"Zadanie '{merged_description}' ma wszystkie dane. Pomijam AI.")
            final_time = user_time
            final_focus = user_focus
            final_priority = user_priority
            final_metadata = task.get('llm_metadata', "Wypełnione manualnie.")

        # 3. Zabezpieczenie tagów i formatowanie końcowe JSON-a
        raw_tags = task.get('tags') or []
        formatted_tags = []
        for t in raw_tags:
            if isinstance(t, dict) and 'name' in t:
                formatted_tags.append(t)
            elif isinstance(t, str):
                formatted_tags.append({"name": t})

        final_task_dict = {
            "id": task.get("id", 0),
            "description": merged_description,
            "deadline": task.get("deadline", "1970-01-01T00:00:00"), 
            "time": final_time,
            "focus": final_focus,
            "priority": final_priority,
            "tags": formatted_tags,
            "llm_metadata": final_metadata
        }
        
        final_tasks.append(final_task_dict)

    # 4. Eksport wyników do plików
    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(final_tasks, f, indent=4, ensure_ascii=False)
        
    with open(thoughts_filepath, 'w', encoding='utf-8') as f:
        f.write(thoughts_log)
        
    print(f"\nGotowe z LLM.py! Zapisano json oraz przemyślenia.")

if __name__ == "__main__":
    process_tasks_file('input.json', 'output.json', 'ai_thoughts.md')