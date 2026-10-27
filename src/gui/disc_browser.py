from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from core.discdata import DiscCar, DiscCars

COLUMNS_DONOR = (
    ("label", "Label", 190), ("name", "Name", 210), ("maker", "Maker", 110), ("year", "Year", 50),
    ("drive", "Drive", 50), ("power_ps", "PS", 50), ("torque_nm", "Nm", 55), ("weight_kg", "kg", 55),
    ("price", "Price", 80),
)
COLUMNS_SOUND = (
    ("sound_id", "Sound ID", 80), ("label", "Car label", 160), ("name", "Name", 200),
    ("maker", "Maker", 100), ("year", "Year", 50), ("drive", "Drive", 50),
    ("power_ps", "PS", 50), ("model", "Model", 80),
)


class DiscBrowser(tk.Toplevel):
    """Pick a disc car. purpose='donor' or 'sound' changes titles, columns and return value."""

    def __init__(self, master, disc: DiscCars, current: str = "", purpose: str = "donor"):
        super().__init__(master)
        self.purpose = purpose if purpose in ("donor", "sound") else "donor"
        self.title({
            "donor": "Disc cars: pick a donor",
            "sound": "Disc cars: pick an engine sound bank",
        }[self.purpose])
        self.geometry("980x560")
        self.transient(master)
        self.disc = disc
        # donor -> (DiscCar, fill: bool) | None
        # sound -> str (numeric id or "") | None
        self.result = None
        self.search_var = tk.StringVar()
        self._sort_key = "sound_id" if self.purpose == "sound" else "label"
        self._sort_rev = False
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        cols = COLUMNS_SOUND if self.purpose == "sound" else COLUMNS_DONOR

        bar = ttk.Frame(self, padding=(10, 10, 10, 4))
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="Search:").pack(side="left")
        entry = ttk.Entry(bar, textvariable=self.search_var, width=34)
        entry.pack(side="left", padx=6)
        hint = {
            "donor": "label, name, maker, drive (FR, MR, 4WD…), year",
            "sound": "Picks the car's engine sound bank id (numeric). Blank = use donor.",
        }[self.purpose]
        ttk.Label(bar, foreground="#777777", text=hint).pack(side="left")
        self.count = ttk.Label(bar, text="")
        self.count.pack(side="right")

        frame = ttk.Frame(self, padding=(10, 0))
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        for key, title, width in cols:
            self.table.heading(key, text=title, command=lambda k=key: self._sort(k))
            self.table.column(key, width=width, anchor="w" if key in ("label", "name", "maker", "model") else "e")
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<Double-1>", lambda _e: self._accept(False))

        buttons = ttk.Frame(self, padding=10)
        buttons.grid(row=2, column=0, sticky="ew")
        if self.purpose == "donor":
            ttk.Button(buttons, text="Use as donor", command=lambda: self._accept(False)).pack(side="left")
            ttk.Button(buttons, text="Use as donor + copy weight",
                       command=lambda: self._accept(True)).pack(side="left", padx=8)
        else:
            ttk.Button(buttons, text="Use this sound ID", command=lambda: self._accept(False)).pack(side="left")
            ttk.Button(buttons, text="Clear (use donor sound)", command=self._clear).pack(side="left", padx=8)
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
        if self.purpose == "sound":
            # Prefer cars that have a known sound_id; still list others at the end
            cars.sort(key=lambda c: (0 if c.sound_id else 1, -c.sound_id if not self._sort_rev else c.sound_id,
                                     c.label))
            if self._sort_key != "sound_id":
                cars.sort(key=lambda c: (getattr(c, self._sort_key) if hasattr(c, self._sort_key) else 0,
                                         c.label), reverse=self._sort_rev)
        else:
            cars.sort(key=lambda c: (getattr(c, self._sort_key) if hasattr(c, self._sort_key) else 0,
                                     c.label), reverse=self._sort_rev)
        self.table.delete(*self.table.get_children())
        for c in cars:
            if self.purpose == "sound":
                sid = f"{c.sound_id:05d}" if c.sound_id else "—"
                self.table.insert("", "end", iid=c.label, values=(
                    sid, c.label, c.name, c.maker, c.year or "", c.drive,
                    f"{c.power_ps:g}" if c.power_ps else "", c.model))
            else:
                self.table.insert("", "end", iid=c.label, values=(
                    c.label, c.name, c.maker, c.year or "", c.drive,
                    f"{c.power_ps:g}" if c.power_ps else "",
                    f"{c.torque_nm:.0f}" if c.torque_kgfm else "",
                    f"{c.weight_kg:g}", f"{c.price:,}"))
        known = sum(1 for c in self.disc.cars if c.sound_id) if self.purpose == "sound" else len(self.disc.cars)
        if self.purpose == "sound":
            self.count.configure(text=f"{len(cars)} shown · {known} with sound id of {len(self.disc.cars)}")
        else:
            self.count.configure(text=f"{len(cars)} of {len(self.disc.cars)} cars")
        # select by label or by numeric sound id
        if select:
            if self.table.exists(select):
                self.table.selection_set(select)
                self.table.see(select)
            elif self.purpose == "sound" and select.isdigit():
                for c in self.disc.cars:
                    if c.sound_id == int(select) and self.table.exists(c.label):
                        self.table.selection_set(c.label)
                        self.table.see(c.label)
                        break

    def _accept(self, fill: bool):
        sel = self.table.selection()
        if not sel:
            return
        car = self.disc.by_label[sel[0]]
        if self.purpose == "donor":
            self.result = (car, fill)
            self.destroy()
            return
        # sound: store the numeric bank id, not the car label/name
        if not car.sound_id:
            from tkinter import messagebox
            messagebox.showwarning(
                "No sound id for this car",
                f"“{car.label}” has no engine sound_id in cars.json.\n\n"
                "cars.json needs a sound_id field per car (from the disc engine table).\n"
                "Regenerate it with:\n"
                "  gt3tool <iso> db <outdir>\n"
                "then merge sound_id from engines.csv into data/cars.json.\n\n"
                "You can still type a numeric id by hand (e.g. 42).",
                parent=self,
            )
            return
        self.result = str(car.sound_id)
        self.destroy()

    def _clear(self):
        self.result = ""
        self.destroy()
