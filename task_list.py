"""
Backward compatibility module: re-exports from ui.task_list.
"""
from ui.task_list import (
    TaskListFrame,
    TaskCard,
    _format_deadline,
    _format_time_duration,
)

__all__ = [
    "TaskListFrame",
    "TaskCard",
    "_format_deadline",
    "_format_time_duration",
]
