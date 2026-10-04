import os
import json
from datetime import date, datetime, time as time_value

from tag import Tag
from task import Task
from week_periods import WeeklySchedule


current_tasks_list: list[Task] = []
done_tasks_list: list[Task] = []
tags_list: list[Tag] = []
weekly_schedule_list: list[WeeklySchedule] = []
past_weekly_schedule_list: list[WeeklySchedule] = []


def _save_list_to_json(data_list: list, file_path: str, serializer) -> None:
    if isinstance(data_list, (str, os.PathLike)) and isinstance(file_path, list):
        data_list, file_path = file_path, str(data_list)
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(
            [serializer(item) for item in data_list],
            file,
            ensure_ascii=False,
            indent=4,
        )


def _load_list_from_json(target_list: list, file_path: str, deserializer) -> list:
    if isinstance(target_list, (str, os.PathLike)) and isinstance(file_path, list):
        target_list, file_path = file_path, str(target_list)
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            loaded_data = json.load(file)
    except FileNotFoundError:
        return target_list

    if not isinstance(loaded_data, list):
        raise ValueError(f"Expected a JSON list in {file_path}")

    target_list[:] = [deserializer(item) for item in loaded_data]
    return target_list


def _encode_task_value(value):
    if isinstance(value, datetime):
        return {"__serialized_type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__serialized_type__": "date", "value": value.isoformat()}
    if isinstance(value, time_value):
        return {"__serialized_type__": "time", "value": value.isoformat()}
    return value


def _decode_task_value(value):
    if not isinstance(value, dict) or "__serialized_type__" not in value:
        return value

    serialized_type = value["__serialized_type__"]
    serialized_value = value["value"]
    if serialized_type == "datetime":
        return datetime.fromisoformat(serialized_value)
    if serialized_type == "date":
        return date.fromisoformat(serialized_value)
    if serialized_type == "time":
        return time_value.fromisoformat(serialized_value)
    return value


def _tag_to_dict(tag) -> dict:
    if isinstance(tag, Tag):
        return {
            "id": tag.id,
            "title": tag.title,
            "color": list(tag.color) if hasattr(tag, "color") else [100, 100, 100],
            "is_interactive": tag.is_interactive if hasattr(tag, "is_interactive") else True,
        }
    if isinstance(tag, dict):
        return tag
    return {
        "id": 0,
        "title": str(tag),
        "color": [100, 100, 100],
        "is_interactive": True,
    }


def _tag_from_dict(tag_data: dict) -> Tag:
    if not isinstance(tag_data, dict):
        raise ValueError("Each tag in a JSON list must be an object")

    color_val = tag_data.get("color", (100, 100, 100))
    if isinstance(color_val, (list, tuple)):
        color_tuple = tuple(color_val)
    else:
        color_tuple = (100, 100, 100)

    return Tag(
        id=tag_data.get("id", 0),
        title=tag_data.get("title", tag_data.get("name", "")),
        color=color_tuple,
        is_interactive=tag_data.get("is_interactive", True),
    )


def _task_to_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "description": task.description,
        "start": _encode_task_value(getattr(task, "start", None)),
        "deadline": _encode_task_value(task.deadline),
        "time": _encode_task_value(task.time),
        "focus": getattr(task, "focus", None),
        "priority": task.priority,
        "tags": [_tag_to_dict(tag) for tag in task.tags],
    }


def _task_from_dict(task_data: dict) -> Task:
    if not isinstance(task_data, dict):
        raise ValueError("Each task in a JSON list must be an object")

    task = Task()
    task.id = task_data.get("id", task.id)
    task.description = task_data.get("description", task.description)
    task.start = _decode_task_value(task_data.get("start"))
    task.deadline = _decode_task_value(task_data.get("deadline"))
    task.time = _decode_task_value(task_data.get("time"))
    task.focus = task_data.get("focus")
    task.priority = task_data.get("priority", task.priority)
    task.tags = [_tag_from_dict(tag) for tag in task_data.get("tags", [])]
    return task


def _weekly_schedule_to_dict(schedule: WeeklySchedule) -> dict:
    return {
        "slots": [\
            [[_tag_to_dict(tag) for tag in slot] for slot in day]\
            for day in schedule._slots\
        ]
    }


def _weekly_schedule_from_dict(schedule_data: dict) -> WeeklySchedule:
    if not isinstance(schedule_data, dict) or not isinstance(
        schedule_data.get("slots"), list
    ):
        raise ValueError("Each weekly schedule in a JSON list must contain slots")

    schedule = WeeklySchedule()
    slots_data = schedule_data["slots"]
    if len(slots_data) != len(schedule._slots):
        raise ValueError("A weekly schedule must contain seven days")

    restored_slots = []
    for day_data, empty_day in zip(slots_data, schedule._slots):
        if not isinstance(day_data, list) or len(day_data) != len(empty_day):
            raise ValueError("Each day in a weekly schedule must contain 96 slots")
        restored_day = []
        for slot_data in day_data:
            if not isinstance(slot_data, list):
                raise ValueError("Each weekly schedule slot must contain a list of tags")
            restored_day.append([_tag_from_dict(tag) for tag in slot_data])
        restored_slots.append(restored_day)

    schedule._slots = restored_slots
    return schedule


def save_current_tasks_list_to_json(tasks: list[Task], file_path: str = "current_tasks.json") -> None:
    _save_list_to_json(tasks, file_path, _task_to_dict)


def load_current_tasks_list_from_json(
    tasks: list[Task], file_path: str = "current_tasks.json"
) -> list[Task]:
    return _load_list_from_json(tasks, file_path, _task_from_dict)


def save_done_tasks_list_to_json(tasks: list[Task], file_path: str = "tasks_archived.json") -> None:
    _save_list_to_json(tasks, file_path, _task_to_dict)


def load_done_tasks_list_from_json(tasks: list[Task], file_path: str = "tasks_archived.json") -> list[Task]:
    return _load_list_from_json(tasks, file_path, _task_from_dict)


def save_tags_list_to_json(tags: list[Tag], file_path: str = "tags.json") -> None:
    _save_list_to_json(tags, file_path, _tag_to_dict)


def load_tags_list_from_json(tags: list[Tag], file_path: str = "tags.json") -> list[Tag]:
    return _load_list_from_json(tags, file_path, _tag_from_dict)


def save_weekly_schedule_list_to_json(
    schedules: list[WeeklySchedule], file_path: str
) -> None:
    _save_list_to_json(schedules, file_path, _weekly_schedule_to_dict)


def load_weekly_schedule_list_from_json(
    schedules: list[WeeklySchedule], file_path: str
) -> list[WeeklySchedule]:
    return _load_list_from_json(schedules, file_path, _weekly_schedule_from_dict)


def save_past_weekly_schedule_list_to_json(
    schedules: list[WeeklySchedule], file_path: str
) -> None:
    _save_list_to_json(schedules, file_path, _weekly_schedule_to_dict)


def load_past_weekly_schedule_list_from_json(
    schedules: list[WeeklySchedule], file_path: str
) -> list[WeeklySchedule]:
    return _load_list_from_json(schedules, file_path, _weekly_schedule_from_dict)


def add_task(task: Task, autofill_focus=False, autofill_time=False):
    if autofill_focus or autofill_time:
        task = fill_task(task, autofill_focus, autofill_time)
    current_tasks_list.append(task)
    save_current_tasks_list_to_json(current_tasks_list, "current_tasks.json")


def delete_task(task: Task) -> bool:
    if task in current_tasks_list:
        current_tasks_list.remove(task)
        save_current_tasks_list_to_json(current_tasks_list, "current_tasks.json")
        return True
    return False


def complete_task(task: Task) -> bool:
    if task in current_tasks_list:
        current_tasks_list.remove(task)
        done_tasks_list.append(task)
        save_current_tasks_list_to_json(current_tasks_list, "current_tasks.json")
        save_done_tasks_list_to_json(done_tasks_list, "tasks_archived.json")
        return True
    return False


def reload_current_tasks() -> list[Task]:
    load_current_tasks_list_from_json(current_tasks_list, "current_tasks.json")
    return current_tasks_list


def load_tasks_from_json(json_filepath: str) -> list[Task]:
    """Read tasks from an LLM-generated JSON file and fill each task."""
    with open(json_filepath, "r", encoding="utf-8") as file:
        all_tasks_data = json.load(file)

    filled_tasks = []
    for item in all_tasks_data:
        task_instance = Task()
        filled_tasks.append(fill_task(task_instance, item))

    return filled_tasks


def fill_task(task: Task = None, autofill_focus: bool = True, autofill_time: bool = True) -> Task:
    """Fill missing task fields using the LLM integration."""
    if task is None:
        task = Task()
    from llm import process_tasks_file

    return process_tasks_file(task, autofill_focus, autofill_time)


# Initialize default lists from disk
try:
    load_current_tasks_list_from_json(current_tasks_list, "current_tasks.json")
except Exception:
    pass

try:
    load_tags_list_from_json(tags_list, "tags.json")
except Exception:
    pass
