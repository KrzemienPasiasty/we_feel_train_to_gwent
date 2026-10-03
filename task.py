from datetime import datetime
from typing import List, Optional
from tag import Tag



class Task:
    def __init__(self):
        self.id: int = 0
        self.description: str = ""
        self.deadline: Optional[datetime] = None
        self.time: Optional[datetime] = None
        """ required time to spend at task"""
        self.focus: int
        self.priority: int = 1
        self.tags: List[Tag] = []
        self.llm_metadata: str = ""

    def __repr__(self) -> str:
        tags_str = [t.title if hasattr(t, "title") else str(t) for t in self.tags]
        return (
            f"Task(id={self.id}, description={self.description!r}, "
            f"deadline={self.deadline}, priority={self.priority}, tags={tags_str})"
        )







class TaskFrame():
    pass
