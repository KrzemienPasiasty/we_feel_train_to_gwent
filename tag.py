



class Tag:
    def __init__(self, id, title, color, is_interactive):
        self.id: int = id
        self.title: str = title
        self.color: (int, int, int) = color

        self.is_interactive: bool = is_interactive
        """ is task with this tag can be moved by app in time"""

        self.archived: bool



    def convert_color_to_hex(self, color):
        """Konwertuje kolor zapisany w formacie (R, G, B) na format HEX, wymagany przez customtkinter."""
        return f'#{color[0]:02x}{color[1]:02x}{color[2]:02x}'

