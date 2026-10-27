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
        self.update_idletasks()
        w, h = 640, 520
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.wheels = wheels
        self.result: str | None = None
        sel = (current or "").strip()
        self._selected: str | None = sel if sel and sel.lower() != "current" else None
        self.search_var = tk.StringVar()
        self._marker_path = DiscWheels.current_marker_path()

        # Performance: build each thumb PhotoImage once, reuse forever
        self._photo_cache: dict[str, object] = {}   # id -> PhotoImage (plain)
        self._photo_sel_cache: dict[str, object] = {}  # id -> PhotoImage (with badge)
        self._cell_widgets: dict[str, dict] = {}    # id -> {border, img_label, ...}
        self._visible_ids: list[str] = []
        self._search_after: str | None = None
        self._use_pil = False
        try:
            from PIL import Image, ImageTk  # noqa: F401
            self._use_pil = True
        except Exception:
            pass

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        bar = ttk.Frame(self, padding=(10, 10, 10, 4))
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="Search:").pack(side="left")
        entry = ttk.Entry(bar, textvariable=self.search_var, width=28)
        entry.pack(side="left", padx=6)
        ttk.Label(bar, text="rim id · badge = selected", foreground="#777777").pack(side="left")
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

        self.inner = tk.Frame(self.canvas, background="#1a1e24")
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))

        def on_wheel(event):
            self.canvas.yview_scroll(-1 if (event.num == 4 or event.delta > 0) else 1, "units")

        self.canvas.bind("<Enter>", lambda _e: (
            self.canvas.bind_all("<MouseWheel>", on_wheel),
            self.canvas.bind_all("<Button-4>", on_wheel),
            self.canvas.bind_all("<Button-5>", on_wheel),
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

        # Debounced search — avoid rebuilding on every keystroke
        self.search_var.trace_add("write", self._on_search)
        self.after(10, self._rebuild)  # first paint after window maps
        entry.focus_set()
        self.bind("<Return>", lambda _e: self._accept())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _on_search(self, *_args):
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.after(150, self._rebuild)

    def _get_photo(self, w: DiscWheel, selected: bool):
        """Return a cached PhotoImage; build once per id (+ selected variant)."""
        cache = self._photo_sel_cache if selected else self._photo_cache
        if w.id in cache:
            return cache[w.id]
        photo = self._build_photo(w, selected)
        if photo is not None:
            cache[w.id] = photo
        return photo

    def _build_photo(self, w: DiscWheel, selected: bool):
        if w.thumb is None or not w.thumb.is_file():
            return None
        try:
            if self._use_pil:
                from PIL import Image, ImageTk
                im = Image.open(w.thumb).convert("RGBA")
                im.thumbnail((THUMB_PX, THUMB_PX), Image.BILINEAR)  # faster than LANCZOS
                canvas = Image.new("RGBA", (THUMB_PX, THUMB_PX), (37, 42, 50, 255))
                x = (THUMB_PX - im.width) // 2
                y = (THUMB_PX - im.height) // 2
                canvas.paste(im, (x, y), im)
                if selected and self._marker_path is not None:
                    try:
                        badge = Image.open(self._marker_path).convert("RGBA")
                        badge.thumbnail((THUMB_PX // 3, THUMB_PX // 3), Image.BILINEAR)
                        canvas.paste(badge, (THUMB_PX - badge.width - 2, 2), badge)
                    except Exception:
                        pass
                return ImageTk.PhotoImage(canvas)
            return tk.PhotoImage(file=str(w.thumb))
        except Exception:
            return None

    def _rebuild(self):
        """Full grid rebuild (search change or first open)."""
        self._search_after = None
        for child in self.inner.winfo_children():
            child.destroy()
        self._cell_widgets.clear()

        items = self.wheels.search(self.search_var.get())
        self._visible_ids = [w.id for w in items]
        self.count.configure(text=f"{len(items)} of {len(self.wheels.wheels)} rims")

        for i, w in enumerate(items):
            r, c = divmod(i, COLS)
            cell = tk.Frame(self.inner, background="#1a1e24", padx=3, pady=3)
            cell.grid(row=r, column=c, sticky="nsew")

            selected = self._selected == w.id
            border = tk.Frame(cell, background="#6db3f2" if selected else "#333840", padx=2, pady=2)
            border.pack()
            hold = tk.Frame(border, background="#252a32")
            hold.pack()

            img_label = tk.Label(hold, background="#252a32")
            photo = self._get_photo(w, selected=selected)
            if photo is not None:
                img_label.configure(image=photo)
            else:
                img_label.configure(text="?", fg="#888888", width=8, height=4)
            img_label.pack()

            name = tk.Label(hold, text=w.id, background="#252a32", foreground="#dddddd",
                            font=("Segoe UI", 8))
            name.pack()

            self._cell_widgets[w.id] = {
                "wheel": w,
                "border": border,
                "img_label": img_label,
            }

            def on_click(_e, wid=w.id):
                self._select(wid)

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

        # Pre-warm a few more photos in the background so scrolling feels instant
        self.after(1, lambda: self._prewarm(items[:24]))

    def _prewarm(self, items: list[DiscWheel]):
        for w in items:
            if w.id not in self._photo_cache:
                self._get_photo(w, selected=False)

    def _select(self, wid: str):
        """Update selection without rebuilding the whole grid."""
        prev = self._selected
        if prev == wid:
            return
        self._selected = wid
        self.status.configure(text=f"Selected: {wid}")

        # Un-highlight previous
        if prev and prev in self._cell_widgets:
            cell = self._cell_widgets[prev]
            cell["border"].configure(background="#333840")
            photo = self._get_photo(cell["wheel"], selected=False)
            if photo is not None:
                cell["img_label"].configure(image=photo)

        # Highlight new
        if wid in self._cell_widgets:
            cell = self._cell_widgets[wid]
            cell["border"].configure(background="#6db3f2")
            photo = self._get_photo(cell["wheel"], selected=True)
            if photo is not None:
                cell["img_label"].configure(image=photo)

    def _accept(self):
        if not self._selected or self._selected.lower() == "current":
            return
        self.result = self._selected
        self.destroy()
