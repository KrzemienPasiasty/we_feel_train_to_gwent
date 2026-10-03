from xmlrpc.client import DateTime
from tag import Tag


class Task:
    def __init__(self):
        self.id: int
        self.description: str
        self.deadline: DateTime
        self.time: DateTime
        """ required time to spend at task"""
        self.priority: int
        self.tags: list[Tag]


        self.llm_metadata: str
