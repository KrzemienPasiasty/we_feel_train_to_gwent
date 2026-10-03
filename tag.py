



class Tag:
    def __init__(self,tag):
        self.id: int
        self.title: str
        self.color: (int, int, int)

        self.is_interactive: bool
        """ is task with this tag can be moved by app in time"""

        self.archived: bool


