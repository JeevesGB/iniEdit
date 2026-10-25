"""Editor for the free-form ``[paints]`` list: ``Name = #RRGGBB`` entries."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from typing import Callable

from core.schema import HEX_COLOR


class PaintsPanel(ttk.Frame):
    def __init__(self, master, defaults: dict[str, str], on_change: Callable[[], None] | None = None):
        super().__init__(master, padding=10)
        self.defaults = dict(defaults)
        self.on_change = on_change or (lambda: None)
        self.paints: list[tuple[str, str]] = []
        self.name_var = tk.StringVar()
        self.hex_var = tk.StringVar(value="#888888")
        self._build()
        self.set_paints(self.defaults, notify=False)

    # ---- public API -------------------------------------------------
    def get_paints(self) -> dict[str, str]:
        return dict(self.paints)

    def set_paints(self, paints: dict[str, str], notify: bool = True) -> None:
        self.paints = list(paints.items())
        self._refresh(notify)

    # ---- UI ---------------------------------------------------------
    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, foreground="#777777", wraplength=640,
                  text="Colours offered by the garage / colour picker, written as Name = #RRGGBB. "
                       "Leave the list empty to leave out the [paints] section.").grid(row=0, column=0, sticky="w", pady=(0, 8))

        frame = ttk.Frame(self)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(frame, columns=("name", "hex"), show="headings", height=12, selectmode="browse")
        self.table.heading("name", text="Paint name")
        self.table.heading("hex", text="Colour")
        self.table.column("name", width=280)
        self.table.column("hex", width=110, anchor="center")
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self._on_select)

        side = ttk.LabelFrame(self, text="Selected / new paint", padding=10)
        side.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        side.columnconfigure(1, weight=1)
        ttk.Label(side, text="Name").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(side, textvariable=self.name_var, width=24).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(side, text="Colour").grid(row=1, column=0, sticky="w", pady=3)
        hex_entry = ttk.Entry(side, textvariable=self.hex_var, width=10)
        hex_entry.grid(row=1, column=1, sticky="w", pady=3)
        self.swatch = tk.Label(side, width=4, relief="sunken", bg="#888888")
        self.swatch.grid(row=1, column=1, sticky="e", pady=3)
        self.hex_var.trace_add("write", lambda *_: self._update_swatch())
        for r, (text, cmd) in enumerate((("Pick colour…", self.pick_colour), ("Add paint", self.add_paint),
                                         ("Update selected", self.update_paint), ("Remove selected", self.remove_paint),
                                         ("Move up", lambda: self.move(-1)), ("Move down", lambda: self.move(1)),
                                         ("Reset to default paints", self.reset)), start=2):
            ttk.Button(side, text=text, command=cmd).grid(row=r, column=0, columnspan=2, sticky="ew", pady=2)

    def _update_swatch(self):
        value = self.hex_var.get().strip()
        if HEX_COLOR.fullmatch(value):
            self.swatch.configure(bg=value)

    # ---- editing ----------------------------------------------------
    def _read(self) -> tuple[str, str] | None:
        name, colour = self.name_var.get().strip(), self.hex_var.get().strip()
        if not name:
            messagebox.showerror("Invalid paint", "Give the paint a name.")
        elif not name.isascii() or "=" in name or ";" in name:
            messagebox.showerror("Invalid paint", "Use plain ASCII for the name, without '=' or ';'.")
        elif not HEX_COLOR.fullmatch(colour):
            messagebox.showerror("Invalid paint", "The colour must look like #RRGGBB, e.g. #9B1B24.")
        else:
            return name, colour.upper()
        return None

    def pick_colour(self):
        current = self.hex_var.get().strip()
        _rgb, chosen = colorchooser.askcolor(color=current if HEX_COLOR.fullmatch(current) else None, parent=self)
        if chosen:
            self.hex_var.set(chosen.upper())

    def _selected(self) -> int | None:
        sel = self.table.selection()
        return int(sel[0]) if sel else None

    def add_paint(self):
        paint = self._read()
        if paint is None:
            return
        if any(n == paint[0] for n, _ in self.paints):
            messagebox.showerror("Duplicate paint", "A paint with that name exists. Select it and use Update selected.")
            return
        self.paints.append(paint)
        self._refresh()

    def update_paint(self):
        index = self._selected()
        if index is None:
            messagebox.showinfo("Select a paint", "Select a paint in the list first.")
            return
        paint = self._read()
        if paint is None:
            return
        if any(i != index and n == paint[0] for i, (n, _) in enumerate(self.paints)):
            messagebox.showerror("Duplicate paint", "Another paint already has that name.")
            return
        self.paints[index] = paint
        self._refresh(select=index)

    def remove_paint(self):
        index = self._selected()
        if index is not None:
            del self.paints[index]
            self._refresh()

    def move(self, step: int):
        index = self._selected()
        if index is None or not 0 <= index + step < len(self.paints):
            return
        self.paints[index], self.paints[index + step] = self.paints[index + step], self.paints[index]
        self._refresh(select=index + step)

    def reset(self):
        if messagebox.askyesno("Reset paints", "Replace the list with the default paints?"):
            self.set_paints(self.defaults)

    def _on_select(self, _e=None):
        index = self._selected()
        if index is not None:
            self.name_var.set(self.paints[index][0])
            self.hex_var.set(self.paints[index][1])

    def _refresh(self, notify: bool = True, select: int | None = None):
        for item in self.table.get_children():
            self.table.delete(item)
        for i, (name, colour) in enumerate(self.paints):
            tag = f"c{i}"
            self.table.insert("", "end", iid=str(i), values=(name, colour), tags=(tag,))
            if HEX_COLOR.fullmatch(colour):
                self.table.tag_configure(tag, background=colour, foreground="#000000" if _is_light(colour) else "#FFFFFF")
        if select is not None:
            self.table.selection_set(str(select))
        if notify:
            self.on_change()


def _is_light(colour: str) -> bool:
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) > 140
