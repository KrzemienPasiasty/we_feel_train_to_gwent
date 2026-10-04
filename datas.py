import os
import json
from datetime import date, datetime, time as time_value
from typing import Any

from tag import Tag
from task import Task
from week_periods import WeeklySchedule


current_tasks_list: list[Task] = []
done_tasks_list: list[Task] = []
tags_list: list[Tag] = []
weekly_schedule_list: list[WeeklySchedule] = []
past_weekly_schedule_list: list[WeeklySchedule] = []
scheduled_meals_list: list = []
trainings_list: list = []


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
    if value is None:
        return None

    if isinstance(value, dict) and "__serialized_type__" in value:
        serialized_type = value["__serialized_type__"]
        serialized_value = value.get("value")
        if serialized_value is None:
            return None
        if serialized_type == "datetime":
            return datetime.fromisoformat(serialized_value)
        if serialized_type == "date":
            return date.fromisoformat(serialized_value)
        if serialized_type == "time":
            return time_value.fromisoformat(serialized_value)
        return serialized_value

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                pass
        for t_fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(s, t_fmt).time()
            except Exception:
                pass
        return value

    return value


def _tag_to_dict(tag) -> dict:
    if isinstance(tag, Tag):
        return {
            "id": tag.id,
            "title": tag.title,
            "color": list(tag.color) if hasattr(tag, "color") and isinstance(tag.color, (list, tuple)) else [100, 100, 100],
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


def _tag_from_dict(tag_data: Any) -> Tag:
    if isinstance(tag_data, Tag):
        return tag_data

    if isinstance(tag_data, str):
        tag_str = tag_data.strip()
        for known in tags_list:
            if known.title.strip().lower() == tag_str.lower():
                return known
        return Tag(
            id=0,
            title=tag_str,
            color=(100, 100, 100),
            is_interactive=True,
        )

    if not isinstance(tag_data, dict):
        return Tag(
            id=0,
            title=str(tag_data),
            color=(100, 100, 100),
            is_interactive=True,
        )

    color_val = tag_data.get("color", (100, 100, 100))
    if isinstance(color_val, (list, tuple)):
        color_tuple = tuple(color_val)
    else:
        color_tuple = (100, 100, 100)

    title = tag_data.get("title", tag_data.get("name", ""))
    for known in tags_list:
        if known.title.strip().lower() == str(title).strip().lower():
            return known

    return Tag(
        id=tag_data.get("id", 0),
        title=title,
        color=color_tuple,
        is_interactive=tag_data.get("is_interactive", True),
    )


def _task_to_dict(task: Task) -> dict:
    return {
        "id": getattr(task, "id", 0),
        "description": getattr(task, "description", ""),
        "start": _encode_task_value(getattr(task, "start", None)),
        "assigned_time": _encode_task_value(getattr(task, "assigned_time", None)),
        "deadline": _encode_task_value(getattr(task, "deadline", None)),
        "time": _encode_task_value(getattr(task, "time", None)),
        "focus": getattr(task, "focus", None),
        "priority": getattr(task, "priority", 1),
        "tags": [_tag_to_dict(tag) for tag in (getattr(task, "tags", None) or [])],
    }


def _task_from_dict(task_data: dict) -> Task:
    if not isinstance(task_data, dict):
        raise ValueError("Each task in a JSON list must be an object")

    task = Task()
    task.id = task_data.get("id", task.id)
    task.description = task_data.get("description", task.description)
    task.start = _decode_task_value(task_data.get("start"))
    task.assigned_time = _decode_task_value(task_data.get("assigned_time"))
    task.deadline = _decode_task_value(task_data.get("deadline"))
    task.time = _decode_task_value(task_data.get("time"))
    task.focus = task_data.get("focus")
    task.priority = task_data.get("priority", task.priority)
    raw_tags = task_data.get("tags") or []
    task.tags = [_tag_from_dict(tag) for tag in raw_tags]
    return task


def _weekly_schedule_to_dict(schedule: WeeklySchedule) -> dict:
    return {
        "slots": [
            [[_tag_to_dict(tag) for tag in slot] for slot in day]
            for day in schedule._slots
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
                raise ValueError("Each slot must contain a list of tags")
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


def _scheduled_meal_to_dict(meal) -> dict:
    s_dt = getattr(meal, "start_datetime", getattr(meal, "datetime", None))
    e_dt = getattr(meal, "end_datetime", None)
    s_t = getattr(meal, "start_time", None)
    e_t = getattr(meal, "end_time", None)
    return {
        "meal_index": getattr(meal, "meal_index", 0),
        "name": getattr(meal, "name", "Meal"),
        "day": getattr(meal, "day", 0),
        "start_time": s_t.strftime("%H:%M:%S") if isinstance(s_t, time_value) else str(s_t or "12:00:00"),
        "end_time": e_t.strftime("%H:%M:%S") if isinstance(e_t, time_value) else str(e_t or "12:30:00"),
        "duration_minutes": getattr(meal, "duration_minutes", 30),
        "color": getattr(meal, "color", "#FF9800"),
        "start_datetime": _encode_task_value(s_dt),
        "end_datetime": _encode_task_value(e_dt),
    }


def _scheduled_meal_from_dict(d: dict):
    from optimizer.schedule_optimizer import ScheduledMeal, time_to_slot
    start_t = _decode_task_value(d.get("start_time"))
    if isinstance(start_t, str):
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                start_t = datetime.strptime(start_t, fmt).time()
                break
            except Exception:
                pass
    if not isinstance(start_t, time_value):
        start_t = time_value(12, 0)

    end_t = _decode_task_value(d.get("end_time"))
    if isinstance(end_t, str):
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                end_t = datetime.strptime(end_t, fmt).time()
                break
            except Exception:
                pass
    if not isinstance(end_t, time_value):
        end_t = time_value(12, 30)

    start_s = time_to_slot(start_t)
    end_s = time_to_slot(end_t)

    meal = ScheduledMeal(
        meal_index=int(d.get("meal_index", 0)),
        name=str(d.get("name", "Meal")),
        day=int(d.get("day", 0)),
        start_slot=start_s,
        end_slot=end_s,
        start_time=start_t,
        end_time=end_t,
        duration_minutes=int(d.get("duration_minutes", 30)),
        color=str(d.get("color", "#FF9800")),
    )
    s_dt = _decode_task_value(d.get("start_datetime"))
    e_dt = _decode_task_value(d.get("end_datetime"))
    meal.start_datetime = s_dt
    meal.datetime = s_dt
    meal.end_datetime = e_dt
    return meal


def _training_to_dict(act) -> dict:
    s_dt = getattr(act, "start_datetime", getattr(act, "datetime", None))
    e_dt = getattr(act, "end_datetime", None)
    s_t = getattr(act, "start_time", None)
    e_t = getattr(act, "end_time", None)
    return {
        "activity_index": getattr(act, "activity_index", 0),
        "name": getattr(act, "name", "Training"),
        "day": getattr(act, "day", 0),
        "start_time": s_t.strftime("%H:%M:%S") if isinstance(s_t, time_value) else str(s_t or "08:00:00"),
        "end_time": e_t.strftime("%H:%M:%S") if isinstance(e_t, time_value) else str(e_t or "09:00:00"),
        "duration_minutes": getattr(act, "duration_minutes", 60),
        "color": getattr(act, "color", "#4CAF50"),
        "outdoor": bool(getattr(act, "outdoor", True)),
        "weather_penalty": float(getattr(act, "weather_penalty", 0.0)),
        "air_quality_penalty": float(getattr(act, "air_quality_penalty", 0.0)),
        "weather_description": str(getattr(act, "weather_description", "Unknown")),
        "air_quality_description": str(getattr(act, "air_quality_description", "Unknown")),
        "start_datetime": _encode_task_value(s_dt),
        "end_datetime": _encode_task_value(e_dt),
    }


def _training_from_dict(d: dict):
    from optimizer.physical_activity import ScheduledActivity, time_to_slot
    start_t = _decode_task_value(d.get("start_time"))
    if isinstance(start_t, str):
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                start_t = datetime.strptime(start_t, fmt).time()
                break
            except Exception:
                pass
    if not isinstance(start_t, time_value):
        start_t = time_value(8, 0)

    end_t = _decode_task_value(d.get("end_time"))
    if isinstance(end_t, str):
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                end_t = datetime.strptime(end_t, fmt).time()
                break
            except Exception:
                pass
    if not isinstance(end_t, time_value):
        end_t = time_value(9, 0)

    start_s = time_to_slot(start_t)
    end_s = time_to_slot(end_t)

    act = ScheduledActivity(
        activity_index=int(d.get("activity_index", 0)),
        name=str(d.get("name", "Training")),
        day=int(d.get("day", 0)),
        start_slot=start_s,
        end_slot=end_s,
        start_time=start_t,
        end_time=end_t,
        duration_minutes=int(d.get("duration_minutes", 60)),
        color=str(d.get("color", "#4CAF50")),
        outdoor=bool(d.get("outdoor", True)),
        weather_penalty=float(d.get("weather_penalty", 0.0)),
        air_quality_penalty=float(d.get("air_quality_penalty", 0.0)),
        weather_description=str(d.get("weather_description", "Unknown")),
        air_quality_description=str(d.get("air_quality_description", "Unknown")),
    )
    s_dt = _decode_task_value(d.get("start_datetime"))
    e_dt = _decode_task_value(d.get("end_datetime"))
    act.start_datetime = s_dt
    act.datetime = s_dt
    act.end_datetime = e_dt
    return act


def save_scheduled_meals_to_json(meals: list, file_path: str = "meals.json") -> None:
    _save_list_to_json(meals, file_path, _scheduled_meal_to_dict)


def load_scheduled_meals_from_json(target_list: list, file_path: str = "meals.json") -> list:
    return _load_list_from_json(target_list, file_path, _scheduled_meal_from_dict)


def save_trainings_to_json(trainings: list, file_path: str = "trainings.json") -> None:
    _save_list_to_json(trainings, file_path, _training_to_dict)


def load_trainings_from_json(target_list: list, file_path: str = "trainings.json") -> list:
    return _load_list_from_json(target_list, file_path, _training_from_dict)


save_meals_to_json = save_scheduled_meals_to_json
load_meals_from_json = load_scheduled_meals_from_json
save_scheduled_trainings_to_json = save_trainings_to_json
load_scheduled_trainings_from_json = load_trainings_from_json


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

    if isinstance(autofill_focus, dict):
        autofill_data = autofill_focus
        task.description = autofill_data.get("description", task.description)
        task.time = autofill_data.get("time", task.time)
        task.focus = autofill_data.get("focus", task.focus)
        task.priority = autofill_data.get("priority", task.priority)
        task.tags = [_tag_from_dict(t) for t in autofill_data.get("tags", [])]
        return task

    import api.autofill_ai as autofill_ai

    output = autofill_ai.autofill(task.description)
    if "time" in output and autofill_time:
        task.time = output["time"]
    if "focus" in output and autofill_focus:
        task.focus = output["focus"]
    return task


if __name__ == "__main__":
    load_current_tasks_list_from_json(current_tasks_list, "current_tasks.json")
    print(current_tasks_list)
