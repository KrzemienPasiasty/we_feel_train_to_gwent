class Tag:
    def __init__(self, id=0, title="", color=(100, 100, 100), is_interactive=True):
        if isinstance(id, str) and not title:
            self.id = 0
            self.title = id
        else:
            self.id = id
            self.title = title
        self.color = tuple(color) if isinstance(color, (list, tuple)) else (100, 100, 100)
        self.is_interactive = is_interactive
        """ is task with this tag can be moved by app in time"""

    def convert_color_to_hex(self, color=None):
        """Konwertuje kolor zapisany w formacie (R, G, B) na format HEX, wymagany przez customtkinter."""
        c = color if color is not None else self.color
        return f'#{c[0]:02x}{c[1]:02x}{c[2]:02x}'

    def __repr__(self) -> str:
        return f"Tag(id={self.id}, title={self.title!r}, color={self.color}, is_interactive={self.is_interactive})"

    def __eq__(self, other):
        if isinstance(other, Tag):
            return self.id == other.id and self.title == other.title
        if isinstance(other, str):
            return self.title == other
        return False

    def __hash__(self):
        return hash((self.id, self.title))
