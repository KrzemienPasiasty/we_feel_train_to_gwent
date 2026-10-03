import json
from pydantic import BaseModel
from typing import List
from openai import OpenAI

# Twój klucz API
client = OpenAI(
    api_key="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"
)

# Tagi dostępne w systemie (AI nie może zmyślać innych)
AVAILABLE_USER_TAGS = [
    "Zarządzanie Finansami", 
    "Dokumentacja", 
    "Zdrowie", 
    "Trening", 
    "Praca", 
    "Regeneracja"
]

class AI_MissingAttributes(BaseModel):
    time: str             
    priority: int         
    tags: List[str]       
    llm_metadata: str     

def process_tasks_file(input_filepath: str, output_filepath: str):
    with open(input_filepath, 'r', encoding='utf-8') as f:
        all_tasks = json.load(f)

    # Segregacja zadań
    history_tasks = [t for t in all_tasks if t.get('priority') is not None]
    tasks_to_fill = [t for t in all_tasks if t.get('priority') is None]

    print(f"Baza wiedzy (historia): {len(history_tasks)} zadań.")
    print(f"Do uzupełnienia przez AI: {len(tasks_to_fill)} zadań.\n")

    history_context = "\n".join([
        f"- {t.get('title')} ({t.get('description', '')}) | Priorytet: {t.get('priority')} | Czas: {t.get('time')} | Tagi: {[tag['name'] for tag in t.get('tags', [])]}" 
        for t in history_tasks
    ])

    for task in tasks_to_fill:
        print(f"Analizuję nowe zadanie: '{task.get('title')}'...")
        
        prompt = f"""
        Jesteś inteligentnym systemem planowania. 
        Oszacuj czas, priorytet, tagi oraz dodaj metadane uzasadniające wybór dla nowego zadania.
        
        ZASADY:
        1. Czas ('time') podaj w formacie HH:MM:SS inkrementy do 5 minut!!! (np. "00:15:00").
        2. Priorytet to liczba od 1 (niski) do 5 (bardzo wysoki).
        3. Tagi wybieraj WYŁĄCZNIE z tej listy: {AVAILABLE_USER_TAGS}. NIE wymyślaj własnych! Jeśli żaden nie pasuje, zwróć pustą listę.
        4. W metadanych krótko uzasadnij podjęte decyzje.
        
        HISTORIA ZADAŃ (ucz się z niej logiki i priorytetów):
        {history_context if history_context else "Brak historii."}
        
        NOWE ZADANIE DO UZUPEŁNIENIA:
        Tytuł: {task.get('title')}
        Opis: {task.get('description', 'Brak')}
        """

        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Zwracaj tylko ustrukturyzowany JSON, bez formatowania markdown."},
                {"role": "user", "content": prompt}
            ],
            response_format=AI_MissingAttributes,
        )
        
        ai_data = completion.choices[0].message.parsed
        
        task['time'] = ai_data.time
        task['priority'] = ai_data.priority
        task['tags'] = [{"name": tag_name} for tag_name in ai_data.tags]
        task['llm_metadata'] = ai_data.llm_metadata
        
    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(all_tasks, f, indent=4, ensure_ascii=False)
        
    print(f"Gotowe! Zapisano do: {output_filepath}")

if __name__ == "__main__":
    process_tasks_file('input.json', 'output.json')