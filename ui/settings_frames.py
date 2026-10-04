import customtkinter as ctk

import datas
from models.tag import Tag


class PreferencesFrame(ctk.CTkFrame):
    def __init__(self, master, on_theme_change=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_theme_change = on_theme_change
        ctk.CTkLabel(self, text="Preferences", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=16, pady=16)
        self.theme = ctk.CTkOptionMenu(self, values=["Dark", "Light", "System"], command=self._set_theme)
        self.theme.pack(anchor="w", padx=16, pady=8)
        self.theme.set(ctk.get_appearance_mode())

    def _set_theme(self, value):
        ctk.set_appearance_mode(value)
        if self.on_theme_change:
            self.on_theme_change()


class TagManagementFrame(ctk.CTkFrame):
    def __init__(self, master, on_tags_updated=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_tags_updated = on_tags_updated
        ctk.CTkLabel(self, text="Manage Tags", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=8)
        self.entry = ctk.CTkEntry(row, placeholder_text="New tag name")
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row, text="Add", command=self.add_tag).pack(side="right")
        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=8)
        self.refresh()

    def refresh(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        for tag in list(datas.tags_list):
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=tag.title).pack(side="left", padx=10, pady=6)
            ctk.CTkButton(row, text="Delete", width=70, command=lambda item=tag: self.delete_tag(item)).pack(side="right", padx=6, pady=4)

    def add_tag(self):
        title = self.entry.get().strip()
        if not title or any(tag.title.casefold() == title.casefold() for tag in datas.tags_list):
            return
        next_id = max((int(tag.id) for tag in datas.tags_list), default=0) + 1
        datas.tags_list.append(Tag(next_id, title))
        datas.save_tags_list_to_json(datas.tags_list)
        self.entry.delete(0, "end")
        self.refresh()
        if self.on_tags_updated:
            self.on_tags_updated()

    def delete_tag(self, tag):
        datas.tags_list[:] = [item for item in datas.tags_list if item != tag]
        datas.save_tags_list_to_json(datas.tags_list)
        self.refresh()
        if self.on_tags_updated:
            self.on_tags_updated()
