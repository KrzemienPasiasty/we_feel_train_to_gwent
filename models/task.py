from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from .tag import Tag


class Task:
    def __init__(self):
        self.id: int = 0
        self.description: str = ""
        self.start: Optional[datetime] = None
        self.deadline: Optional[datetime | str] = None
        self.time: Optional[datetime | str] = None
        """ required time to spend at task"""
        self.focus: float | int = 5
        self.priority: int = 1
        self.tags: List[Tag] = []

    def __repr__(self) -> str:
        return (
            f"Task("
            f"  id={self.id},"
            f"  description={self.description!r},"
            f"  deadline={self.deadline!r},"
            f"  time={self.time!r},"
            f"  focus={self.focus!r},"
            f"  priority={self.priority!r},"
            f"  tags={self.tags!r}"
            f")"
        )
