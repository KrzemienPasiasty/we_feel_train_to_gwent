from models.task import Task

def __getattr__(name):
    if name == "TaskFrame":
        from ui.task_frame import TaskFrame
        return TaskFrame
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["Task", "TaskFrame"]
