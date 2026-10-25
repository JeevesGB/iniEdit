from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class PreviewPanel(ttk.Frame):
    def __init__(self, master, file_titles: dict[str, str]):
        super().__init__(master, padding=6)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.texts: dict[str, tk.Text] = {}
        self.names: dict[str, ttk.Label] = {}
        self.ids = list(file_titles)
        for fid, title in file_titles.items():
            page = ttk.Frame(self.notebook, padding=4)
            page.columnconfigure(0, weight=1)
            page.rowconfigure(1, weight=1)
            bar = ttk.Frame(page)
            bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
            name = ttk.Label(bar, text="", foreground="#777777")
            name.pack(side="left")
            ttk.Button(bar, text="Save this file as…", command=lambda f=fid: self.save_one(f)).pack(side="right")
            ttk.Button(bar, text="Copy", command=lambda f=fid: self.copy(f)).pack(side="right", padx=6)
            text = tk.Text(page, wrap="none", font=("Consolas", 11), state="disabled")
            ysb = ttk.Scrollbar(page, orient="vertical", command=text.yview)
            xsb = ttk.Scrollbar(page, orient="horizontal", command=text.xview)
            text.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
            text.grid(row=1, column=0, sticky="nsew")
            ysb.grid(row=1, column=1, sticky="ns")
            xsb.grid(row=2, column=0, sticky="ew")
            self.notebook.add(page, text=title)
            self.texts[fid], self.names[fid] = text, name

    def show(self, fid: str, content: str, rel_path: str | None) -> None:
        text = self.texts[fid]
        text.configure(state="normal")
        yview = text.yview()
        text.delete("1.0", "end")
        text.insert("1.0", content)
        text.configure(state="disabled")
        text.yview_moveto(yview[0])
        self.names[fid].configure(text=rel_path or "(file name not known yet)")

    def show_disabled(self, fid: str) -> None:
        self.show(fid, "", None)
        self.names[fid].configure(text="Not included in this mod.")

    def content(self, fid: str) -> str:
        return self.texts[fid].get("1.0", "end-1c")

    def copy(self, fid: str):
        self.clipboard_clear()
        self.clipboard_append(self.content(fid))
        self.update()

    def save_one(self, fid: str):
        content = self.content(fid)
        if not content.strip():
            messagebox.showinfo("Nothing to save", "This file is not included in the mod.")
            return
        initial = (self.names[fid].cget("text") or "file.ini").split("/")[-1]
        path = filedialog.asksaveasfilename(title="Save .ini", defaultextension=".ini",
                                            filetypes=[("INI files", "*.ini"), ("All files", "*.*")], initialfile=initial)
        if path:
            try:
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(content)
            except OSError as exc:
                messagebox.showerror("Save failed", str(exc))
