import json
import math
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ACTIVE_TASKS_FILE = BASE_DIR / "tasks_active.json"
ARCHIVED_TASKS_FILE = BASE_DIR / "tasks_archived.json"
TASK_FEEDBACK_FILE = BASE_DIR / "task_feedback.json"
SURVEY_RATING_VALUES = tuple(range(-5, 6))


def read_task_records(filepath):
    path = Path(filepath)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        records = json.load(file)
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise ValueError(f"Expected a JSON list of task objects in {path}")
    return records


def _write_task_records(filepath, records):
    path = Path(filepath)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=4)
    temporary_path.replace(path)


def _next_task_id(*record_groups):
    ids = []
    for records in record_groups:
        for record in records:
            try:
                ids.append(int(record.get("id", 0)))
            except (TypeError, ValueError):
                continue
    return max(ids, default=0) + 1


def _json_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return str(value)


def persist_new_task(task, active_path=ACTIVE_TASKS_FILE, archived_path=ARCHIVED_TASKS_FILE):
    active_records = read_task_records(active_path)
    archived_records = read_task_records(archived_path)
    task.id = _next_task_id(active_records, archived_records)

    task_record = {
        "id": task.id,
        "description": getattr(task, "description", ""),
        "start": _json_value(getattr(task, "start", None)),
        "deadline": _json_value(getattr(task, "deadline", None)),
        "time": _json_value(getattr(task, "time", None)),
        "focus": getattr(task, "focus", 0),
        "priority": getattr(task, "priority", 1),
        "tags": [
            {"id": tag.id, "name": tag.title}
            for tag in getattr(task, "tags", [])
        ],
        "llm_metadata": getattr(task, "llm_metadata", ""),
        "source": getattr(task, "source", ""),
        "external_id": getattr(task, "external_id", None),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "not_started",
    }
    active_records.append(task_record)
    _write_task_records(active_path, active_records)
    return task_record


def start_task(task_id, active_path=ACTIVE_TASKS_FILE):
    active_records = read_task_records(active_path)
    task_record = next(
        (record for record in active_records if str(record.get("id")) == str(task_id)),
        None,
    )
    if task_record is None:
        raise ValueError(f"Active task {task_id} was not found")
    if task_record.get("status") == "in_progress":
        raise ValueError(f"Task {task_id} is already in progress")

    task_record["status"] = "in_progress"
    task_record["started_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    _write_task_records(active_path, active_records)
    return task_record


def update_task(task_id, updates, active_path=ACTIVE_TASKS_FILE):
    allowed_fields = {"description", "deadline", "time", "focus", "priority", "tags"}
    if set(updates) - allowed_fields:
        raise ValueError("Only task details can be edited")
    if not str(updates.get("description", "")).strip():
        raise ValueError("Task description cannot be empty")
    try:
        updates["priority"] = int(updates["priority"])
        updates["focus"] = float(updates["focus"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Priority and focus must be valid numbers") from error
    if not 1 <= updates["priority"] <= 4:
        raise ValueError("Priority must be between 1 and 4")
    if not math.isfinite(updates["focus"]) or not -5 <= updates["focus"] <= 5:
        raise ValueError("Focus must be between -5 and +5")
    if not isinstance(updates.get("tags"), list) or any(not isinstance(tag, dict) for tag in updates["tags"]):
        raise ValueError("Task tags must be a list")

    active_records = read_task_records(active_path)
    task_record = next(
        (record for record in active_records if str(record.get("id")) == str(task_id)),
        None,
    )
    if task_record is None:
        raise ValueError(f"Active task {task_id} was not found")
    task_record.update({field: _json_value(value) for field, value in updates.items()})
    _write_task_records(active_path, active_records)
    return task_record


def delete_task(task_id, active_path=ACTIVE_TASKS_FILE):
    active_records = read_task_records(active_path)
    matching_index = next(
        (index for index, record in enumerate(active_records) if str(record.get("id")) == str(task_id)),
        None,
    )
    if matching_index is None:
        raise ValueError(f"Active task {task_id} was not found")
    deleted_record = active_records.pop(matching_index)
    _write_task_records(active_path, active_records)
    return deleted_record


def complete_task(
    task_id,
    survey,
    active_path=ACTIVE_TASKS_FILE,
    archived_path=ARCHIVED_TASKS_FILE,
    feedback_path=TASK_FEEDBACK_FILE,
):
    active_records = read_task_records(active_path)
    archived_records = read_task_records(archived_path)
    feedback_records = read_task_records(feedback_path)
    matching_index = next(
        (index for index, record in enumerate(active_records) if str(record.get("id")) == str(task_id)),
        None,
    )
    if matching_index is None:
        raise ValueError(f"Active task {task_id} was not found")
    if active_records[matching_index].get("status") != "in_progress":
        raise ValueError("Start the task before completing it")

    actual_minutes = int(survey["actual_minutes"])
    focus_rating = _survey_rating(survey["focus_rating"])
    if actual_minutes <= 0:
        raise ValueError("Actual duration must be greater than zero")

    task_record = active_records.pop(matching_index)
    task_record["completion"] = {
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "actual_minutes": actual_minutes,
        "focus_rating": focus_rating,
        "note": str(survey.get("note", "")).strip(),
    }
    task_record["status"] = "completed"
    archived_records.append(task_record)

    feedback_records.append({
        "schema_version": 2,
        "task_id": task_record.get("id"),
        "description": task_record.get("description", ""),
        "tags": [tag.get("name", "") for tag in task_record.get("tags", [])],
        "priority": task_record.get("priority"),
        "planned_focus": task_record.get("focus"),
        "planned_time": task_record.get("time"),
        "started_at": task_record.get("started_at"),
        **task_record["completion"],
    })

    _write_task_records(archived_path, archived_records)
    _write_task_records(active_path, active_records)
    _write_task_records(feedback_path, feedback_records)
    return task_record


def _survey_rating(value):
    try:
        rating = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Focus rating must be a whole number from -5 to +5") from error
    if rating not in SURVEY_RATING_VALUES or str(value).strip() not in {str(rating), f"{rating}.0"}:
        raise ValueError("Focus rating must be a whole number from -5 to +5")
    return rating


