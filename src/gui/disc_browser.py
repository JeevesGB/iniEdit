"""Searchable table of the disc's cars, used to pick a donor."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.discdata import DiscCar, DiscCars

COLUMNS = (("label", "Label", 190), ("name", "Name", 210), ("maker", "Maker", 110), ("year", "Year", 50),
           ("drive", "Drive", 50), ("power_ps", "PS", 50), ("torque_nm", "Nm", 55), ("weight_kg", "kg", 55),
           ("price", "Price", 80))


class DiscBrowser(tk.Toplevel):
    """Modal dialog. After it closes, ``result`` is ``(car, fill_extras)`` or None."""

    def __init__(self, master, disc: DiscCars, current: str = ""):
        super().__init__(master)
        self.title("Disc cars: pick a donor")
        self.geometry("980x560")
        self.transient(master)
        self.disc = disc
        self.result: tuple[DiscCar, bool] | None = None
        self.search_var = tk.StringVar()
        self._sort_key, self._sort_rev = "label", False
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        bar = ttk.Frame(self, padding=(10, 10, 10, 4))
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="Search:").pack(side="left")
        entry = ttk.Entry(bar, textvariable=self.search_var, width=34)
        entry.pack(side="left", padx=6)
        ttk.Label(bar, foreground="#777777", text="label, name, maker, drive (FR, MR, 4WD…), year").pack(side="left")
        self.count = ttk.Label(bar, text="")
        self.count.pack(side="right")

        frame = ttk.Frame(self, padding=(10, 0))
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for key, title, width in COLUMNS:
            self.table.heading(key, text=title, command=lambda k=key: self._sort(k))
            self.table.column(key, width=width, anchor="w" if key in ("label", "name", "maker") else "e")
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<Double-1>", lambda _e: self._accept(False))

        buttons = ttk.Frame(self, padding=10)
        buttons.grid(row=2, column=0, sticky="ew")
        ttk.Button(buttons, text="Use as donor", command=lambda: self._accept(False)).pack(side="left")
        ttk.Button(buttons, text="Use as donor + copy its drive and weight", command=lambda: self._accept(True)).pack(
            side="left", padx=8)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")

        self.search_var.trace_add("write", lambda *_: self._fill())
        self._fill(select=current)
        entry.focus_set()
        self.bind("<Return>", lambda _e: self._accept(False))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _sort(self, key: str):
        self._sort_rev = not self._sort_rev if key == self._sort_key else False
        self._sort_key = key
        self._fill()

    def _fill(self, select: str = ""):
        cars = self.disc.search(self.search_var.get())
        cars.sort(key=lambda c: (getattr(c, self._sort_key) if hasattr(c, self._sort_key) else 0,
                                 c.label), reverse=self._sort_rev)
        self.table.delete(*self.table.get_children())
        for c in cars:
            self.table.insert("", "end", iid=c.label, values=(
                c.label, c.name, c.maker, c.year or "", c.drive, f"{c.power_ps:g}" if c.power_ps else "",
                f"{c.torque_nm:.0f}" if c.torque_kgfm else "", f"{c.weight_kg:g}", f"{c.price:,}"))
        self.count.configure(text=f"{len(cars)} of {len(self.disc.cars)} cars")
        if select and self.table.exists(select):
            self.table.selection_set(select)
            self.table.see(select)

    def _accept(self, fill: bool):
        sel = self.table.selection()
        if sel:
            self.result = (self.disc.by_label[sel[0]], fill)
            self.destroy()
