from __future__ import annotations
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from core.project import MOD_ID_RE


class StartDialog(tk.Toplevel):

    def __init__(self, parent: tk.Misc, recent: list[Path] | None = None):
        super().__init__(parent)
        self.result: str | None = None
        self.folder: Path | None = None
        self.recent = list(recent or [])
        self.title("GT3 Mod Creator")
        self.resizable(False, False)
        self.transient(parent)
        body = ttk.Frame(self, padding=20)
        body.pack()
        ttk.Label(body, text="What would you like to do?", font=("TkDefaultFont", 12, "bold")).pack(pady=(0, 14))
        self._choice(body, "New mod…", "Pick a name and a place; the mod's folders are created for you.", "new")
        self._choice(body, "Edit existing mod…", "Open a mod folder (the one with mod.ini in it).", "open")
        if self.recent:
            ttk.Label(body, text="Recent mods (double-click to open):", foreground="#666666").pack(
                anchor="w", pady=(14, 2))
            self.box = tk.Listbox(body, height=min(6, len(self.recent)), width=54, exportselection=False)
            for path in self.recent:
                self.box.insert("end", f"{path.name}    {path.parent}")
            self.box.selection_set(0)
            self.box.pack(fill="x")
            self.box.bind("<Double-1>", self._open_recent)
            self.box.bind("<Return>", self._open_recent)
        ttk.Button(body, text="Skip (start with a blank form)", command=self.destroy).pack(pady=(14, 0))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        _centre(self, parent)
        self.grab_set()

    def _choice(self, parent, text: str, hint: str, choice: str):
        ttk.Button(parent, text=text, width=34, command=lambda: self._pick(choice)).pack(pady=(4, 0), ipady=6)
        ttk.Label(parent, text=hint, foreground="#666666").pack(pady=(0, 6))

    def _open_recent(self, _event=None):
        sel = self.box.curselection()
        if sel:
            self.folder = self.recent[sel[0]]
            self._pick("recent")

    def _pick(self, choice: str):
        self.result = choice
        self.destroy()


class NewModDialog(tk.Toplevel):

    def __init__(self, parent: tk.Misc, initial_dir: Path | None = None):
        super().__init__(parent)
        self.result: tuple[str, Path] | None = None
        self.title("New mod")
        self.resizable(False, False)
        self.transient(parent)
        self.name_var = tk.StringVar()
        self.dir_var = tk.StringVar(value=str(initial_dir or Path.home()))
        self.path_var = tk.StringVar()

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Mod folder name:").grid(row=0, column=0, sticky="w", pady=4)
        name = ttk.Entry(body, textvariable=self.name_var, width=40)
        name.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)
        ttk.Label(body, text="Location:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self.dir_var, width=40).grid(row=1, column=1, sticky="ew", padx=(8, 4), pady=4)
        ttk.Button(body, text="Browse…", command=self._browse).grid(row=1, column=2, pady=4)
        ttk.Label(body, text="Lower-case letters, digits and _ only (this is the mod's id).",
                  foreground="#666666").grid(row=2, column=1, columnspan=2, sticky="w", padx=(8, 0))
        ttk.Label(body, textvariable=self.path_var, foreground="#666666", wraplength=420).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.error = ttk.Label(body, text="", foreground="#c0392b", wraplength=420)
        self.error.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=3, sticky="e", pady=(14, 0))
        self.create_btn = ttk.Button(buttons, text="Create", command=self._create)
        self.create_btn.pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left")

        self.name_var.trace_add("write", lambda *_: self._validate())
        self.dir_var.trace_add("write", lambda *_: self._validate())
        self.bind("<Return>", lambda _e: self._create())
        self.bind("<Escape>", lambda _e: self.destroy())
        self._validate()
        _centre(self, parent)
        self.grab_set()
        name.focus_set()

    def _browse(self):
        folder = filedialog.askdirectory(parent=self, title="Choose where to create the mod folder",
                                         initialdir=self.dir_var.get() or None)
        if folder:
            self.dir_var.set(folder)

    def _validate(self) -> bool:
        name, parent = self.name_var.get().strip(), self.dir_var.get().strip()
        error = ""
        if not name:
            error = " "                       # nothing typed yet: disable Create, show no message
        elif not MOD_ID_RE.fullmatch(name):
            error = "The name can only use a-z, 0-9 and _ (no spaces or capitals)."
        elif not parent or not Path(parent).is_dir():
            error = "The location doesn't exist."
        elif (Path(parent) / name / "mod.ini").exists():
            error = "That folder already contains a mod. Choose another name, or use \"Edit existing mod\"."
        self.path_var.set(f"Will be created at: {Path(parent) / name}" if name and parent else "")
        self.error.configure(text=error.strip())
        self.create_btn.state(["!disabled"] if not error else ["disabled"])
        return not error

    def _create(self):
        if self._validate():
            self.result = (self.name_var.get().strip(), Path(self.dir_var.get().strip()))
            self.destroy()


def _centre(win: tk.Toplevel, parent: tk.Misc):
    win.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_reqwidth()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_reqheight()) // 3
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
