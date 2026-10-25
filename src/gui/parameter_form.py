from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable
from core.schema import TRUE_WORDS, FileSpec, Parameter

ERROR_FG = "#c0392b"
HELP_FG = "#777777"


class ParameterForm(ttk.Frame):
    def __init__(self, master, spec: FileSpec, on_change: Callable[[], None] | None = None,
                 lookup: Callable[[str], list[str]] | None = None,
                 on_browse: Callable[[Parameter], None] | None = None):
        super().__init__(master)
        self.lookup = lookup or (lambda _s: [])
        self.on_browse = on_browse
        self.spec = spec
        self.params: dict[tuple[str, str], Parameter] = {
            (sec.name, p.key): p for sec in spec.sections for p in sec.parameters}
        self.on_change = on_change or (lambda: None)
        self.vars: dict[tuple[str, str], tk.Variable] = {}
        self.error_labels: dict[tuple[str, str], ttk.Label] = {}
        self._suspend = False
        self._build()

    def get_values(self) -> dict[str, dict[str, str]]:
        values: dict[str, dict[str, str]] = {}
        for (section, key), var in self.vars.items():
            param = self.params.get((section, key))
            if param and param.type == "bool":
                text = "yes" if var.get() else "no"
            else:
                text = str(var.get())
            values.setdefault(section, {})[key] = text
        return values

    def set_values(self, values: dict[str, dict[str, str]], fill_defaults: bool = True) -> None:
        self._suspend = True
        try:
            for (section, key), var in self.vars.items():
                param = self.params.get((section, key))
                raw = values.get(section, {}).get(key)
                if raw is None:
                    raw = param.default_text() if (param and fill_defaults) else ""
                if param and param.type == "bool":
                    var.set((raw.strip() or param.default_text()).lower() in TRUE_WORDS)
                else:
                    var.set(raw)
        finally:
            self._suspend = False
        self.validate_all()

    def validate_all(self) -> int:
        count = 0
        for (section, key), var in self.vars.items():
            count += self._validate(section, key)
        return count

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        canvas = tk.Canvas(self, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        inner = ttk.Frame(canvas, padding=10)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

        def wheel(event):
            canvas.yview_scroll(-1 if (event.num == 4 or event.delta > 0) else 1, "units")

        def bind_wheel(_e):
            canvas.bind_all("<MouseWheel>", wheel)
            canvas.bind_all("<Button-4>", wheel)
            canvas.bind_all("<Button-5>", wheel)

        def unbind_wheel(_e):
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                canvas.unbind_all(seq)

        canvas.bind("<Enter>", bind_wheel)
        canvas.bind("<Leave>", unbind_wheel)

        inner.columnconfigure(0, weight=1)
        row = 0
        if self.spec.description:
            ttk.Label(inner, text=self.spec.description, foreground=HELP_FG, wraplength=640).grid(
                row=row, column=0, sticky="w", pady=(0, 8))
            row += 1
        for sec in self.spec.sections:
            if sec.kind != "fields":
                continue
            params = [p for p in sec.parameters if p.type != "curve" and not p.auto]
            if not params:
                continue
            frame = ttk.LabelFrame(inner, text=sec.title, padding=10)
            frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            frame.columnconfigure(1, weight=1)
            row += 1
            r = 0
            if sec.description:
                ttk.Label(frame, text=sec.description, foreground=HELP_FG, wraplength=560).grid(
                    row=r, column=0, columnspan=3, sticky="w", pady=(0, 6))
                r += 1
            for param in params:
                r = self._add_row(frame, r, sec.name, param)

    def _add_row(self, frame, r: int, section: str, param: Parameter) -> int:
        ident = (section, param.key)
        label = param.label + (" *" if param.required else "")
        ttk.Label(frame, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=(4, 0))

        if param.type == "bool":
            var: tk.Variable = tk.BooleanVar(value=param.default_text() == "yes")
            widget = ttk.Checkbutton(frame, variable=var)
        elif param.type == "choice":
            var = tk.StringVar(value=param.default_text())
            widget = ttk.Combobox(frame, textvariable=var, values=param.choices, state="readonly", width=14)
        elif param.suggestions or param.suggest_from:
            var = tk.StringVar(value=param.default_text())
            values = list(param.suggestions) + (self.lookup(param.suggest_from) if param.suggest_from else [])
            widget = ttk.Combobox(frame, textvariable=var, values=values, width=32)
        else:
            var = tk.StringVar(value=param.default_text())
            widget = ttk.Entry(frame, textvariable=var)
        widget.grid(row=r, column=1, sticky="ew" if param.type not in ("bool", "choice") and not param.suggestions else "w", pady=(4, 0))
        if self.on_browse and param.suggest_from.endswith(".label"):
            ttk.Button(frame, text="Browse disc cars…", command=lambda p=param: self.on_browse(p)).grid(
                row=r, column=2, sticky="w", padx=(6, 0), pady=(4, 0))
        elif param.unit:
            ttk.Label(frame, text=param.unit, foreground=HELP_FG).grid(row=r, column=2, sticky="w", padx=(6, 0), pady=(4, 0))

        err = ttk.Label(frame, text="", foreground=ERROR_FG)
        err.grid(row=r + 1, column=1, columnspan=2, sticky="w")
        err.grid_remove()        
        self.error_labels[ident] = err
        next_row = r + 2
        if param.help:
            ttk.Label(frame, text=param.help, foreground=HELP_FG, wraplength=520).grid(
                row=next_row, column=1, columnspan=2, sticky="w")
            next_row += 1

        self.vars[ident] = var
        var.trace_add("write", lambda *_a, s=section, k=param.key: self._on_var(s, k))
        return next_row

    def _validate(self, section: str, key: str) -> int:
        param = self.params.get((section, key))
        var = self.vars[(section, key)]
        label = self.error_labels[(section, key)]
        error = None if param.type == "bool" else param.validate(str(var.get()))
        label.configure(text=error or "")
        label.grid() if error else label.grid_remove()
        return 1 if error else 0

    def _on_var(self, section: str, key: str):
        if self._suspend:
            return
        self._validate(section, key)
        self.on_change()
