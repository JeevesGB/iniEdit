"""Thumbnail grid to pick a disc rim id for [model] wheel."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from core.wheels import DiscWheel, DiscWheels

THUMB_PX = 72
COLS = 6


class WheelBrowser(tk.Toplevel):
    def __init__(self, master, wheels: DiscWheels, current: str = ""):
        super().__init__(master)
        self.title("Disc wheels: pick a rim")
        self.geometry("640x520")
        self.transient(master)
        self.wheels = wheels
        self.result: str | None = None
        self._photos: list[object] = []
        # Selection for highlight only — never "current" as a wheel id
        sel = (current or "").strip()
        self._selected: str | None = sel if sel and sel.lower() != "current" else None
        self.search_var = tk.StringVar()
        self._marker = DiscWheels.current_marker_path()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        bar = ttk.Frame(self, padding=(10, 10, 10, 4))
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="Search:").pack(side="left")
        entry = ttk.Entry(bar, textvariable=self.search_var, width=28)
        entry.pack(side="left", padx=6)
        ttk.Label(bar, text="rim id (e.g. enw010_b) · badge = currently selected",
                  foreground="#777777").pack(side="left")
        self.count = ttk.Label(bar, text="")
        self.count.pack(side="right")

        outer = ttk.Frame(self, padding=(10, 0))
        outer.grid(row=1, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(outer, highlightthickness=0, background="#1a1e24")
        scroll = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))

        def wheel(event):
            self.canvas.yview_scroll(-1 if (event.num == 4 or event.delta > 0) else 1, "units")

        self.canvas.bind("<Enter>", lambda _e: (
            self.canvas.bind_all("<MouseWheel>", wheel),
            self.canvas.bind_all("<Button-4>", wheel),
            self.canvas.bind_all("<Button-5>", wheel),
        ))
        self.canvas.bind("<Leave>", lambda _e: (
            self.canvas.unbind_all("<MouseWheel>"),
            self.canvas.unbind_all("<Button-4>"),
            self.canvas.unbind_all("<Button-5>"),
        ))

        foot = ttk.Frame(self, padding=10)
        foot.grid(row=2, column=0, sticky="ew")
        self.status = ttk.Label(foot, text="")
        self.status.pack(side="left")
        ttk.Button(foot, text="Use selected", command=self._accept).pack(side="left", padx=(12, 0))
        ttk.Button(foot, text="Cancel", command=self.destroy).pack(side="right")

        self.search_var.trace_add("write", lambda *_: self._fill())
        self._fill()
        entry.focus_set()
        self.bind("<Return>", lambda _e: self._accept())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _fill(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self._photos.clear()

        items = self.wheels.search(self.search_var.get())
        self.count.configure(text=f"{len(items)} of {len(self.wheels.wheels)} rims")

        try:
            from PIL import Image, ImageTk
            use_pil = True
        except Exception:
            use_pil = False

        for i, w in enumerate(items):
            r, c = divmod(i, COLS)
            cell = tk.Frame(self.inner, background="#1a1e24", padx=4, pady=4)
            cell.grid(row=r, column=c, sticky="nsew")

            selected = self._selected == w.id
            border = tk.Frame(cell, background="#6db3f2" if selected else "#333840", padx=2, pady=2)
            border.pack()
            hold = tk.Frame(border, background="#252a32")
            hold.pack()

            # Thumbnail layer
            img_label = tk.Label(hold, background="#252a32")
            photo = self._make_photo(w, use_pil, selected=selected)
            if photo is not None:
                self._photos.append(photo)
                img_label.configure(image=photo)
            else:
                img_label.configure(text="?", fg="#888888", width=8, height=4)
            img_label.pack()

            name = tk.Label(hold, text=w.id, background="#252a32", foreground="#dddddd",
                            font=("Segoe UI", 8))
            name.pack()

            def on_click(_e, wid=w.id):
                self._selected = wid
                self.status.configure(text=f"Selected: {wid}")
                self._fill()

            def on_double(_e, wid=w.id):
                self._selected = wid
                self._accept()

            for widget in (border, hold, img_label, name):
                widget.bind("<Button-1>", on_click)
                widget.bind("<Double-1>", on_double)

        if self._selected:
            self.status.configure(text=f"Selected: {self._selected}")
        else:
            self.status.configure(text="Click a rim, double-click to confirm")

    def _make_photo(self, w: DiscWheel, use_pil: bool, selected: bool = False):
        """Rim thumbnail; if selected and current.png exists, composite the marker on top."""
        if w.thumb is None or not w.thumb.is_file():
            return None
        try:
            if use_pil:
                from PIL import Image, ImageTk
                im = Image.open(w.thumb).convert("RGBA")
                im.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
                canvas = Image.new("RGBA", (THUMB_PX, THUMB_PX), (37, 42, 50, 255))
                x = (THUMB_PX - im.width) // 2
                y = (THUMB_PX - im.height) // 2
                canvas.paste(im, (x, y), im)

                # Selection badge: overlay current.png (indicator only, not a rim id)
                if selected and self._marker is not None:
                    try:
                        badge = Image.open(self._marker).convert("RGBA")
                        # small badge in the corner
                        badge.thumbnail((THUMB_PX // 3, THUMB_PX // 3), Image.LANCZOS)
                        bx = THUMB_PX - badge.width - 2
                        by = 2
                        canvas.paste(badge, (bx, by), badge)
                    except Exception:
                        pass
                return ImageTk.PhotoImage(canvas)
            return tk.PhotoImage(file=str(w.thumb))
        except Exception:
            return None

    def _accept(self):
        if not self._selected or self._selected.lower() == "current":
            return
        self.result = self._selected
        self.destroy()
