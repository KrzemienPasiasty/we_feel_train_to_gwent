import json
from pydantic import BaseModel, Field
from openai import OpenAI

from task import Task


# Twój klucz API
client = OpenAI(
    api_key="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"
)



ai_thoughts_filepath = "ai_thoughts.md"



class AIPrediction(BaseModel):
    time: str = Field(description="Oszacowany czas w formacie HH:MM:SS (lub przepisany, jeśli podano).")
    focus: int = Field(description="Wymagane skupienie w skali od -5 do 5.")
    llm_metadata: str = Field(description="Krótkie uzasadnienie szacunków.")

def process_tasks_file(task: Task, autofill_focus, autofill_time):
    """
    Czyta plik input.json, dla zadań z brakującymi polami wysyła zapytanie do OpenAI,
    i zapisuje pełne dane do output.json oraz logiki decyzyjne do ai_thoughts.md.
    """


    final_tasks = []
    thoughts_log = "# Dziennik Przemyśleń AI na temat zadań\n\n"








        # Jeśli brakuje chociaż jednego – włączamy AI
        #needs_prediction = not (has_time and has_focus and has_priority)


    print(f"Analizuję zadanie: '{task.description}' (uzupełniam braki)...")

    prompt = f"""
    Jesteś inteligentnym systemem planowania. Otrzymujesz zadanie użytkownika.
    Twoim celem jest przewidzieć TYLKO te wartości, których użytkownik nie podał:
    (czas trwania, wymagane skupienie (trudność), na podstawie dostępnych danych.
    
    DANE ZADANIA:
    - Tytuł/Opis: {task.description}
    
    DANE DO UZUPEŁNIENIA / ZACHOWANIA:
    - Czas (time): {task.time if not autofill_time else 'BRAK - Oszacuj w formacie HH:MM:SS (np. 00:15:00)'}
    - Skupienie (focus): {task.focus if not autofill_focus else 'BRAK - Oszacuj w skali od -5 do 5 (-5=całkowity luz/rutyna, 0=neutralne, 5=głęboka praca)'}
    
    
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

    task.time = task.time if not autofill_time else ai_data.time
    task.focus = task.focus if not autofill_focus else ai_data.focus
    final_metadata = ai_data.llm_metadata

    # Notowanie przemyśleń
    thoughts_log += f"## 📝 {task.description}\n"
    thoughts_log += f"- **Wygenerowano:** Czas: `{task.time}` | Skupienie: `{task.focus}`\n"
    thoughts_log += f"- **Przemyślenia AI:** {final_metadata}\n\n"
            



        

        
    with open(ai_thoughts_filepath, 'w', encoding='utf-8') as f:
        f.write(thoughts_log)
        
    print(f"\nGotowe z LLM.py! Zapisano json oraz przemyślenia.")

    return task
