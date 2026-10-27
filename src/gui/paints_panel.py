from __future__ import annotations
import re
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Callable
from core.schema import HEX_COLOR

# Lines like: Name = #RRGGBB   or   Name=#RRGGBB   or   Name #RRGGBB
_LINE_RE = re.compile(
    r"^\s*(?P<name>[^=;#]+?)\s*(?:=|\s)\s*(?P<hex>#[0-9A-Fa-f]{6})\s*(?:[;#].*)?$"
)


def parse_paint_text(text: str) -> list[tuple[str, str]]:
    """Parse a paint list from free text. Skips blanks and pure comments."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#") and "=" not in line and " #" not in line:
            # allow "# comment" only when not a hex colour line
            if line.startswith("#") and not HEX_COLOR.fullmatch(line.split()[0] if line.split() else ""):
                continue
            if not line or line.startswith(";"):
                continue
        # strip trailing comments after colour
        m = _LINE_RE.match(line)
        if not m:
            # try "Name = #RRGGBB ; comment"
            if "=" in line:
                left, right = line.split("=", 1)
                name = left.strip()
                colour = right.split(";")[0].split("#", 1)
                # right may be " #9B1B24" or "#9B1B24"
                hex_part = right.strip().split()[0].split(";")[0] if right.strip() else ""
                if not HEX_COLOR.fullmatch(hex_part):
                    # find first #RRGGBB in the line
                    hm = re.search(r"#[0-9A-Fa-f]{6}", right)
                    if not hm:
                        continue
                    hex_part = hm.group(0)
                if name and name.isascii() and "=" not in name and ";" not in name:
                    key = name
                    if key not in seen:
                        seen.add(key)
                        out.append((key, hex_part.upper()))
            continue
        name = m.group("name").strip()
        colour = m.group("hex").upper()
        if not name or not name.isascii() or "=" in name or ";" in name:
            continue
        if name not in seen:
            seen.add(name)
            out.append((name, colour))
    return out


class PaintsPanel(ttk.Frame):
    def __init__(self, master, defaults: dict[str, str], on_change: Callable[[], None] | None = None):
        super().__init__(master, padding=10)
        self.defaults = dict(defaults)
        self.on_change = on_change or (lambda: None)
        self.paints: list[tuple[str, str]] = []
        self.name_var = tk.StringVar()
        self.hex_var = tk.StringVar(value="#888888")
        self._suspend_swatch = False
        self._build()
        self.set_paints(self.defaults, notify=False)

    def get_paints(self) -> dict[str, str]:
        return dict(self.paints)

    def set_paints(self, paints: dict[str, str], notify: bool = True) -> None:
        self.paints = list(paints.items())
        self._refresh(notify)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(
            self, foreground="#777777", wraplength=720,
            text="Colours in the dealer / garage picker, in order. Written as Name = #RRGGBB. "
                 "Empty list = omit the [paints] section.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        # ---- main list ----
        list_frame = ttk.LabelFrame(self, text="Paint list", padding=8)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        cols = ("swatch", "name", "hex")
        self.table = ttk.Treeview(
            list_frame, columns=cols, show="headings", height=14, selectmode="extended",
        )
        self.table.heading("swatch", text="")
        self.table.heading("name", text="Name")
        self.table.heading("hex", text="Hex")
        self.table.column("swatch", width=36, anchor="center", stretch=False)
        self.table.column("name", width=260, anchor="w")
        self.table.column("hex", width=90, anchor="center")
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self._on_select)
        self.table.bind("<Double-1>", lambda _e: self._focus_name())
        self.table.bind("<Delete>", lambda _e: self.remove_paint())

        # list toolbar
        tools = ttk.Frame(list_frame)
        tools.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(tools, text="↑ Up", width=8, command=lambda: self.move(-1)).pack(side="left")
        ttk.Button(tools, text="↓ Down", width=8, command=lambda: self.move(1)).pack(side="left", padx=(4, 0))
        ttk.Button(tools, text="Remove", width=8, command=self.remove_paint).pack(side="left", padx=(8, 0))
        ttk.Separator(tools, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(tools, text="Load from file…", command=self.load_from_file).pack(side="left")
        ttk.Button(tools, text="Save to file…", command=self.save_to_file).pack(side="left", padx=(4, 0))
        ttk.Button(tools, text="Reset defaults", command=self.reset).pack(side="right")

        # ---- editor ----
        side = ttk.LabelFrame(self, text="Edit paint", padding=10)
        side.grid(row=1, column=1, sticky="ns")
        side.columnconfigure(1, weight=1)

        ttk.Label(side, text="Name").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.name_entry = ttk.Entry(side, textvariable=self.name_var, width=26)
        self.name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 4))

        ttk.Label(side, text="Colour").grid(row=1, column=0, sticky="w", pady=4)
        hex_entry = ttk.Entry(side, textvariable=self.hex_var, width=10)
        hex_entry.grid(row=1, column=1, sticky="w", pady=4)
        self.swatch = tk.Label(side, width=6, height=2, relief="groove", bg="#888888", cursor="hand2")
        self.swatch.grid(row=1, column=2, sticky="e", padx=(8, 0), pady=4)
        self.swatch.bind("<Button-1>", lambda _e: self.pick_colour())
        self.hex_var.trace_add("write", lambda *_: self._update_swatch())

        ttk.Button(side, text="Pick colour…", command=self.pick_colour).grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        ttk.Button(side, text="Add as new", command=self.add_paint).grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=2)
        ttk.Button(side, text="Update selected", command=self.update_paint).grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=2)

        ttk.Separator(side, orient="horizontal").grid(row=5, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(
            side, foreground="#777777", wraplength=200,
            text="Load accepts lines like:\n  Carmine Red = #9B1B24\n"
                 "One paint per line. Existing names are updated; new names are appended.",
        ).grid(row=6, column=0, columnspan=3, sticky="w")

        self.count_label = ttk.Label(self, text="", foreground="#777777")
        self.count_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _focus_name(self):
        self.name_entry.focus_set()
        self.name_entry.selection_range(0, "end")

    def _update_swatch(self):
        if self._suspend_swatch:
            return
        value = self.hex_var.get().strip()
        if HEX_COLOR.fullmatch(value):
            try:
                self.swatch.configure(bg=value)
            except tk.TclError:
                pass

    def _tag_for(self, colour: str) -> str:
        return f"c_{colour[1:].lower()}"

    def _ensure_tag(self, colour: str) -> str:
        tag = self._tag_for(colour)
        # Tint the row; pick readable text colour from luminance
        try:
            r = int(colour[1:3], 16)
            g = int(colour[3:5], 16)
            b = int(colour[5:7], 16)
            # perceived luminance
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            fg = "#111111" if lum > 0.55 else "#f5f5f5"
            self.table.tag_configure(tag, background=colour, foreground=fg)
        except (tk.TclError, ValueError):
            pass
        return tag

    def _read(self) -> tuple[str, str] | None:
        name, colour = self.name_var.get().strip(), self.hex_var.get().strip()
        if not name:
            messagebox.showerror("Invalid paint", "Give the paint a name.", parent=self)
        elif not name.isascii() or "=" in name or ";" in name:
            messagebox.showerror("Invalid paint", "Use plain ASCII for the name, without '=' or ';'.", parent=self)
        elif not HEX_COLOR.fullmatch(colour):
            messagebox.showerror("Invalid paint", "The colour must look like #RRGGBB, e.g. #9B1B24.", parent=self)
        else:
            return name, colour.upper()
        return None

    def pick_colour(self):
        current = self.hex_var.get().strip()
        _rgb, chosen = colorchooser.askcolor(
            color=current if HEX_COLOR.fullmatch(current) else None, parent=self,
        )
        if chosen:
            self.hex_var.set(chosen.upper())

    def _selected_indices(self) -> list[int]:
        out = []
        for iid in self.table.selection():
            try:
                out.append(int(iid))
            except ValueError:
                pass
        return sorted(out)

    def _selected_one(self) -> int | None:
        idxs = self._selected_indices()
        return idxs[0] if len(idxs) == 1 else None

    def add_paint(self):
        paint = self._read()
        if paint is None:
            return
        if any(n == paint[0] for n, _ in self.paints):
            messagebox.showerror(
                "Duplicate paint",
                "A paint with that name exists. Select it and use Update selected.",
                parent=self,
            )
            return
        self.paints.append(paint)
        self._refresh()
        self.table.selection_set(str(len(self.paints) - 1))
        self.table.see(str(len(self.paints) - 1))

    def update_paint(self):
        index = self._selected_one()
        if index is None:
            messagebox.showinfo("Update paint", "Select one paint in the list to update.", parent=self)
            return
        paint = self._read()
        if paint is None:
            return
        if any(i != index and n == paint[0] for i, (n, _) in enumerate(self.paints)):
            messagebox.showerror("Duplicate paint", "Another paint already uses that name.", parent=self)
            return
        self.paints[index] = paint
        self._refresh()
        self.table.selection_set(str(index))

    def remove_paint(self):
        idxs = self._selected_indices()
        if not idxs:
            return
        for i in reversed(idxs):
            if 0 <= i < len(self.paints):
                del self.paints[i]
        self._refresh()

    def move(self, delta: int):
        index = self._selected_one()
        if index is None:
            return
        target = index + delta
        if target < 0 or target >= len(self.paints):
            return
        self.paints[index], self.paints[target] = self.paints[target], self.paints[index]
        self._refresh()
        self.table.selection_set(str(target))
        self.table.see(str(target))

    def reset(self):
        if messagebox.askyesno("Reset paints", "Replace the list with the default paints?", parent=self):
            self.set_paints(self.defaults)

    def load_from_file(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Load paint list",
            filetypes=[
                ("Paint / text files", "*.txt *.paints *.ini *.cfg"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except OSError as e:
            messagebox.showerror("Load paints", f"Could not read file:\n{e}", parent=self)
            return

        # If the file looks like a full car.ini, prefer the [paints] section only
        lower = text.lower()
        if "[paints]" in lower:
            start = lower.index("[paints]")
            rest = text[start + len("[paints]"):]
            # cut at next section
            m = re.search(r"\n\s*\[", rest)
            text = rest[:m.start()] if m else rest

        parsed = parse_paint_text(text)
        if not parsed:
            messagebox.showwarning(
                "Load paints",
                "No paints found.\n\nExpected lines like:\n  Carmine Red = #9B1B24",
                parent=self,
            )
            return

        # Merge: update existing names, append new ones (preserve order of file for new)
        by_name = {n: i for i, (n, _) in enumerate(self.paints)}
        added = updated = 0
        for name, colour in parsed:
            if name in by_name:
                self.paints[by_name[name]] = (name, colour)
                updated += 1
            else:
                by_name[name] = len(self.paints)
                self.paints.append((name, colour))
                added += 1
        self._refresh()
        messagebox.showinfo(
            "Load paints",
            f"Loaded {len(parsed)} paint(s) from file.\n{added} added, {updated} updated.",
            parent=self,
        )

    def save_to_file(self):
        if not self.paints:
            messagebox.showinfo("Save paints", "The list is empty.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save paint list",
            defaultextension=".txt",
            filetypes=[
                ("Text file", "*.txt"),
                ("Paint list", "*.paints"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        lines = [f"{name} = {colour}" for name, colour in self.paints]
        try:
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as e:
            messagebox.showerror("Save paints", f"Could not write file:\n{e}", parent=self)

    def _on_select(self, _event=None):
        index = self._selected_one()
        if index is None or not (0 <= index < len(self.paints)):
            return
        name, colour = self.paints[index]
        self._suspend_swatch = True
        try:
            self.name_var.set(name)
            self.hex_var.set(colour)
        finally:
            self._suspend_swatch = False
        self._update_swatch()

    def _refresh(self, notify: bool = True):
        self.table.delete(*self.table.get_children())
        for i, (name, colour) in enumerate(self.paints):
            tag = self._ensure_tag(colour)
            # First column is a solid colour chip via row tag background
            self.table.insert("", "end", iid=str(i), values=("████", name, colour), tags=(tag,))
        self.count_label.configure(
            text=f"{len(self.paints)} paint(s)" + ("" if self.paints else " — [paints] will be omitted on save")
        )
        if notify:
            self.on_change()
