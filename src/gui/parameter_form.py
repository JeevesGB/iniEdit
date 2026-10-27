from __future__ import annotations
import re
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable
from core.schema import TRUE_WORDS, FileSpec, Parameter
from gui.tooltip import ToolTip

ERROR_FG = "#c0392b"
HELP_FG = "#666666"
ACTIVE_SCROLL: Callable | None = None

# Sections that get one shared gtbg composite at the bottom
_COMPOSITE_SECTIONS = {
    "maker": ("background", "logo", "icon"),
    "dealer": ("picture", "logo", "thumb"),
}

# Keys that should always span the full width (not sit in a 2-col grid)
_FULL_WIDTH_KEYS = {
    "description", "curve", "gears", "picture", "thumb", "logo",
    "icon", "background", "file", "donor", "label", "name",
}

_TYRE_RE = re.compile(r"(\d{3})[/\-](\d{2,3})Z?R?(\d{2})", re.I)


def parse_tyre_size(text: str) -> tuple[float, float, float] | None:
    """Parse 205/55R16, 205/55ZR16, 205-55-16 → (width_mm, aspect, rim_in)."""
    t = (text or "").strip().upper().replace(" ", "")
    if not t:
        return None
    m = _TYRE_RE.match(t)
    if not m:
        return None
    width, aspect, rim = float(m.group(1)), float(m.group(2)), float(m.group(3))
    if not (80 <= width <= 450 and 20 <= aspect <= 95 and 10 <= rim <= 28):
        return None
    return width, aspect, rim


def tyre_dimensions(width: float, aspect: float, rim: float) -> tuple[float, float]:
    """Return (overall_diameter_mm, sidewall_mm)."""
    sidewall = width * (aspect / 100.0)
    diameter = rim * 25.4 + 2.0 * sidewall
    return diameter, sidewall


class ParameterForm(ttk.Frame):
    def __init__(self, master, spec: FileSpec, on_change: Callable[[], None] | None = None,
                 lookup: Callable[[str], list[str]] | None = None,
                 on_browse: Callable[[Parameter], None] | None = None,
                 on_image_browse: Callable[[Parameter, tk.Variable], None] | None = None,
                 on_wheel_browse: Callable[[Parameter, tk.Variable], None] | None = None,
                 resolve_image: Callable[[str], Path | None] | None = None):
        super().__init__(master)
        self.lookup = lookup or (lambda _s: [])
        self.on_browse = on_browse
        self.on_image_browse = on_image_browse
        self.on_wheel_browse = on_wheel_browse
        self.resolve_image = resolve_image or (lambda _p: None)
        self.spec = spec
        self.params: dict[tuple[str, str], Parameter] = {
            (sec.name, p.key): p for sec in spec.sections for p in sec.parameters}
        self.on_change = on_change or (lambda: None)
        self.vars: dict[tuple[str, str], tk.Variable] = {}
        self.error_labels: dict[tuple[str, str], ttk.Label] = {}
        self.composite_labels: dict[str, ttk.Label] = {}
        self._composite_photos: dict[str, object] = {}
        self.tyre_canvas: tk.Canvas | None = None
        self.tyre_caption: ttk.Label | None = None
        self._suspend = False
        self.help_labels: list[ttk.Label] = []
        self.show_help = True
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
        for section in self.composite_labels:
            self._update_section_composite(section)
        self._update_tyre_preview()

    def set_help_visible(self, visible: bool) -> None:
        self.show_help = visible
        for label in self.help_labels:
            label.grid() if visible else label.grid_remove()

    def validate_all(self) -> int:
        count = 0
        for (section, key) in self.vars:
            count += self._validate(section, key)
        return count

    def _is_wide(self, param: Parameter) -> bool:
        if param.browse == "image":
            return True
        if param.type in ("list", "curve"):
            return True
        if param.key in _FULL_WIDTH_KEYS:
            return True
        if param.suggest_from:
            return True
        return False

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        canvas = tk.Canvas(self, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        inner = ttk.Frame(canvas, padding=(10, 8))
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

        def wheel(event):
            canvas.yview_scroll(-1 if (event.num == 4 or event.delta > 0) else 1, "units")

        def bind_wheel(_e):
            global ACTIVE_SCROLL
            ACTIVE_SCROLL = wheel
            canvas.bind_all("<MouseWheel>", wheel)
            canvas.bind_all("<Button-4>", wheel)
            canvas.bind_all("<Button-5>", wheel)

        def unbind_wheel(_e):
            global ACTIVE_SCROLL
            ACTIVE_SCROLL = None
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                canvas.unbind_all(seq)

        canvas.bind("<Enter>", bind_wheel)
        canvas.bind("<Leave>", unbind_wheel)

        inner.columnconfigure(0, weight=1)
        row = 0
        if self.spec.description:
            ttk.Label(inner, text=self.spec.description, foreground=HELP_FG, wraplength=720).grid(
                row=row, column=0, sticky="w", pady=(0, 6))
            row += 1

        for sec in self.spec.sections:
            if sec.kind != "fields":
                continue
            params = [p for p in sec.parameters if p.type != "curve" and not p.auto]
            if not params:
                continue
            frame = ttk.LabelFrame(inner, text=sec.title, padding=(10, 6))
            frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            frame.columnconfigure(1, weight=1, uniform="field")
            frame.columnconfigure(3, weight=1, uniform="field")
            row += 1
            r = 0
            if sec.description:
                ttk.Label(frame, text=sec.description, foreground=HELP_FG, wraplength=700).grid(
                    row=r, column=0, columnspan=4, sticky="w", pady=(0, 6))
                r += 1

            col = 0
            for param in params:
                wide = self._is_wide(param)
                if wide and col == 1:
                    col = 0
                    r += 1
                r, col = self._add_field(frame, r, col, sec.name, param, wide=wide)
                if wide:
                    col = 0
                    r += 1
                else:
                    col += 1
                    if col >= 2:
                        col = 0
                        r += 1
            if col == 1:
                r += 1

            if sec.name in _COMPOSITE_SECTIONS and any(p.browse == "image" for p in params):
                ttk.Separator(frame, orient="horizontal").grid(
                    row=r, column=0, columnspan=4, sticky="ew", pady=(8, 4))
                r += 1
                ttk.Label(frame, text="In-game preview", foreground=HELP_FG).grid(
                    row=r, column=0, columnspan=4, sticky="w")
                r += 1
                composite = ttk.Label(frame)
                composite.grid(row=r, column=0, columnspan=4, sticky="w", pady=(2, 2))
                self.composite_labels[sec.name] = composite
                self.after_idle(lambda s=sec.name: self._update_section_composite(s))

            if sec.name == "tires":
                ttk.Separator(frame, orient="horizontal").grid(
                    row=r, column=0, columnspan=4, sticky="ew", pady=(8, 4))
                r += 1
                ttk.Label(frame, text="Tyre size preview (side view, to scale with each other)",
                          foreground=HELP_FG).grid(row=r, column=0, columnspan=4, sticky="w")
                r += 1
                self.tyre_canvas = tk.Canvas(frame, width=540, height=200, highlightthickness=0,
                                             background="#1a1e24")
                self.tyre_canvas.grid(row=r, column=0, columnspan=4, sticky="w", pady=(2, 0))
                r += 1
                self.tyre_caption = ttk.Label(frame, text="", foreground=HELP_FG)
                self.tyre_caption.grid(row=r, column=0, columnspan=4, sticky="w", pady=(2, 2))
                self.after_idle(self._update_tyre_preview)

    def _add_field(self, frame, r: int, col: int, section: str, param: Parameter,
                   wide: bool = False) -> tuple[int, int]:
        ident = (section, param.key)
        base_col = 0 if wide else (0 if col == 0 else 2)

        label_text = param.label + (" *" if param.required else "")
        name_label = ttk.Label(frame, text=label_text)
        name_label.grid(row=r, column=base_col, sticky="nw",
                        padx=(0 if base_col == 0 else 12, 6), pady=(3, 0))

        cell = ttk.Frame(frame)
        span = 3 if wide else 1
        cell.grid(row=r, column=base_col + 1, columnspan=span, sticky="ew", pady=(3, 0))
        cell.columnconfigure(0, weight=1)

        if param.type == "bool":
            var: tk.Variable = tk.BooleanVar(value=param.default_text() == "yes")
            widget = ttk.Checkbutton(cell, variable=var)
            widget.grid(row=0, column=0, sticky="w")
        elif param.type == "choice":
            var = tk.StringVar(value=param.default_text())
            widget = ttk.Combobox(cell, textvariable=var, values=param.choices, state="readonly", width=14)
            widget.grid(row=0, column=0, sticky="w")
        elif param.suggestions or param.suggest_from:
            var = tk.StringVar(value=param.default_text())
            values = list(param.suggestions) + (self.lookup(param.suggest_from) if param.suggest_from else [])
            widget = ttk.Combobox(cell, textvariable=var, values=values, width=28)
            widget.grid(row=0, column=0, sticky="ew")
        else:
            var = tk.StringVar(value=param.default_text())
            width = 36 if wide else 14
            widget = ttk.Entry(cell, textvariable=var, width=width)
            widget.grid(row=0, column=0, sticky="ew")

        btn_col = 1
        if self.on_browse and (param.browse == "sound" or param.suggest_from.endswith(".label")):
            btn_text = (
                "Browse sounds…"
                if param.browse == "sound" or param.key == "sound_id"
                else "Browse disc cars…"
            )
            ttk.Button(cell, text=btn_text, command=lambda p=param: self.on_browse(p)).grid(
                row=0, column=btn_col, sticky="w", padx=(6, 0))
            btn_col += 1
        elif param.browse == "wheel" and self.on_wheel_browse:
            ttk.Button(
                cell, text="Browse wheels…",
                command=lambda p=param, v=var: self.on_wheel_browse(p, v),
            ).grid(row=0, column=btn_col, sticky="w", padx=(6, 0))
            btn_col += 1
        elif param.browse == "image" and self.on_image_browse:
            ttk.Button(cell, text="Browse…",
                       command=lambda p=param, v=var: self.on_image_browse(p, v)).grid(
                row=0, column=btn_col, sticky="w", padx=(6, 0))
            btn_col += 1
            if param.image_size:
                ttk.Label(cell, text=param.image_size, foreground=HELP_FG).grid(
                    row=0, column=btn_col, sticky="w", padx=(6, 0))
                btn_col += 1
        elif param.unit:
            ttk.Label(cell, text=param.unit, foreground=HELP_FG).grid(
                row=0, column=btn_col, sticky="w", padx=(6, 0))

        help_row = 1
        if param.help:
            ToolTip(name_label, param.help)
            ToolTip(widget, param.help)
            hl = ttk.Label(cell, text=param.help, foreground=HELP_FG, wraplength=340 if not wide else 640)
            hl.grid(row=help_row, column=0, columnspan=4, sticky="w")
            if not self.show_help:
                hl.grid_remove()
            self.help_labels.append(hl)
            help_row += 1

        err = ttk.Label(cell, text="", foreground=ERROR_FG)
        err.grid(row=help_row, column=0, columnspan=4, sticky="w")
        err.grid_remove()
        self.error_labels[ident] = err

        self.vars[ident] = var
        var.trace_add("write", lambda *_a, s=section, k=param.key: self._on_var(s, k))
        return r, col

    def _validate(self, section: str, key: str) -> int:
        param = self.params.get((section, key))
        var = self.vars[(section, key)]
        label = self.error_labels[(section, key)]
        error = None if param and param.type == "bool" else (param.validate(str(var.get())) if param else None)
        label.configure(text=error or "")
        label.grid() if error else label.grid_remove()
        return 1 if error else 0

    def _on_var(self, section: str, key: str):
        if self._suspend:
            return
        self._validate(section, key)
        if section in self.composite_labels:
            self._update_section_composite(section)
        if section == "tires" and key in ("front", "rear"):
            self._update_tyre_preview()
        self.on_change()

    # ------------------------------------------------------------------
    # Tyre size preview
    # ------------------------------------------------------------------
    def _update_tyre_preview(self) -> None:
        cv = self.tyre_canvas
        if cv is None:
            return
        cv.delete("all")

        front_raw = str(self.vars[("tires", "front")].get()) if ("tires", "front") in self.vars else ""
        rear_raw = str(self.vars[("tires", "rear")].get()) if ("tires", "rear") in self.vars else ""
        front = parse_tyre_size(front_raw)
        rear = parse_tyre_size(rear_raw)

        parts = []
        if front:
            d, sw = tyre_dimensions(*front)
            parts.append(("Front", front[0], front[1], front[2], d, sw, "#6db3f2"))
        if rear:
            d, sw = tyre_dimensions(*rear)
            parts.append(("Rear", rear[0], rear[1], rear[2], d, sw, "#f2b06d"))

        if not parts:
            cv.create_text(270, 85, text="Enter a size like 205/55R16", fill="#888888",
                           font=("Segoe UI", 10))
            if self.tyre_caption is not None:
                self.tyre_caption.configure(text="")
            return

        # Side view: circles scaled by overall diameter so proportions look right.
        max_d = max(p[4] for p in parts)
        scale = 120.0 / max_d  # largest tyre ~120 px tall

        slots = [150, 400] if len(parts) == 2 else [270]
        captions = []
        for i, (label, width, aspect, rim, diam, sidewall, color) in enumerate(parts):
            cx = slots[i] if i < len(slots) else 270
            self._draw_tyre_side(cv, cx, 88, width, aspect, rim, diam, sidewall, scale, color, label)
            captions.append(
                f"{label}: {width:.0f}/{aspect:.0f}R{rim:.0f}  →  "
                f"Ø {diam:.0f} mm · width {width:.0f} mm · sidewall {sidewall:.0f} mm"
            )

        if len(parts) == 2:
            delta = parts[1][4] - parts[0][4]
            if abs(delta) >= 1:
                captions.append(
                    f"Rear is {abs(delta):.0f} mm {'taller' if delta > 0 else 'shorter'} overall"
                )
            else:
                captions.append("Same overall diameter")
            # Width comparison
            wdelta = parts[1][1] - parts[0][1]
            if abs(wdelta) >= 1:
                captions.append(
                    f"Rear is {abs(wdelta):.0f} mm {'wider' if wdelta > 0 else 'narrower'}"
                )

        if self.tyre_caption is not None:
            self.tyre_caption.configure(text="  ·  ".join(captions))

    def _draw_tyre_side(self, cv: tk.Canvas, cx: float, cy: float,
                        width: float, aspect: float, rim: float,
                        diam: float, sidewall: float, scale: float,
                        color: str, label: str) -> None:
        """Side view: circular tyre (diameter), rim, diameter + width callouts."""
        # Outer tyre — true circle from overall diameter
        r = (diam * scale) / 2.0
        cv.create_oval(cx - r, cy - r, cx + r, cy + r,
                       outline=color, width=2, fill="#2a3038")

        # Rubber ring hint: slightly inset band
        inset = max(3.0, sidewall * scale * 0.15)
        cv.create_oval(cx - r + inset, cy - r + inset, cx + r - inset, cy + r - inset,
                       outline="#3d4450", width=1)

        # Rim circle
        rim_r = (rim * 25.4 * scale) / 2.0
        cv.create_oval(cx - rim_r, cy - rim_r, cx + rim_r, cy + rim_r,
                       outline="#bbbbbb", width=1, fill="#3a4048")
        # Hub
        hub_r = rim_r * 0.28
        cv.create_oval(cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r,
                       outline="#666666", fill="#1a1e24")
        # Simple 5-spoke hint
        import math
        for i in range(5):
            a = -math.pi / 2 + i * (2 * math.pi / 5)
            x2 = cx + math.cos(a) * rim_r * 0.92
            y2 = cy + math.sin(a) * rim_r * 0.92
            cv.create_line(cx, cy, x2, y2, fill="#555555", width=1)

        # Diameter dimension (vertical, left of tyre)
        dim_x = cx - r - 16
        cv.create_line(dim_x, cy - r, dim_x, cy + r, fill=color, arrow=tk.BOTH, width=1)
        cv.create_text(dim_x - 3, cy, text=f"Ø{diam:.0f}", fill=color, anchor="e",
                       font=("Segoe UI", 8))

        # Width as a small front-on bar under the tyre (depth into the page)
        # Scaled width bar, centred under the circle
        bar_w = width * scale
        # Keep bar readable but secondary to the circle
        bar_w = max(18.0, min(bar_w, r * 1.6))
        bar_h = 7
        by = cy + r + 18
        cv.create_rectangle(cx - bar_w / 2, by, cx + bar_w / 2, by + bar_h,
                            outline=color, fill="#2a3038", width=1)
        cv.create_line(cx - bar_w / 2, by + bar_h + 6, cx + bar_w / 2, by + bar_h + 6,
                       fill=color, arrow=tk.BOTH, width=1)
        cv.create_text(cx, by + bar_h + 8, text=f"width {width:.0f} mm", fill=color,
                       anchor="n", font=("Segoe UI", 8))

        # Labels above
        cv.create_text(cx, cy - r - 14, text=label, fill=color, anchor="s",
                       font=("Segoe UI", 9, "bold"))
        cv.create_text(cx, cy - r - 2, text=f"{width:.0f}/{aspect:.0f}R{rim:.0f}",
                       fill="#bbbbbb", anchor="s", font=("Segoe UI", 8))

    # ------------------------------------------------------------------
    # Image composite preview
    # ------------------------------------------------------------------
    def _gtbg_path(self) -> Path | None:
        candidates = []
        try:
            from gui.icons import ICON_DIR
            candidates.append(ICON_DIR / "gtbg.png")
        except Exception:
            pass
        here = Path(__file__).resolve().parent
        candidates.append(here / "icons" / "gtbg.png")
        candidates.append(here.parent / "gui" / "icons" / "gtbg.png")
        for p in candidates:
            if p.is_file():
                return p
        return None

    def _load_role_image(self, section: str, role: str):
        for (sec, key), param in self.params.items():
            if sec != section:
                continue
            if (param.image_role or key) != role:
                continue
            var = self.vars.get((sec, key))
            if var is None:
                return None
            raw = str(var.get()).strip()
            if not raw:
                return None
            path = self.resolve_image(raw)
            if path is None or not path.is_file():
                return None
            try:
                from PIL import Image
                return Image.open(path).convert("RGBA")
            except Exception:
                return None
        return None

    def _update_section_composite(self, section: str) -> None:
        label = self.composite_labels.get(section)
        if label is None:
            return
        roles = _COMPOSITE_SECTIONS.get(section, ())
        try:
            from PIL import Image, ImageTk
        except Exception:
            label.configure(image="", text="(Pillow not available)")
            self._composite_photos.pop(section, None)
            return

        frame_w, frame_h = 320, 224
        bg_path = self._gtbg_path()
        if bg_path is not None:
            base = Image.open(bg_path).convert("RGBA").resize((frame_w, frame_h), Image.LANCZOS)
        else:
            base = Image.new("RGBA", (frame_w, frame_h), (30, 36, 48, 255))
        composite = base.copy()

        for role in roles:
            img = self._load_role_image(section, role)
            if img is None:
                continue
            if role in ("background", "picture"):
                layer = img.resize((frame_w, frame_h), Image.LANCZOS)
                composite.paste(layer, (0, 0), layer)
            elif role == "logo":
                max_w, max_h = int(frame_w * 0.55), int(frame_h * 0.22)
                layer = img.copy()
                layer.thumbnail((max_w, max_h), Image.LANCZOS)
                x = (frame_w - layer.width) // 2
                y = int(frame_h * 0.06)
                composite.paste(layer, (x, y), layer)
            elif role in ("icon", "thumb"):
                layer = img.copy()
                layer.thumbnail((64, 34), Image.LANCZOS)
                x, y = 10, frame_h - layer.height - 10
                composite.paste(layer, (x, y), layer)

        photo = ImageTk.PhotoImage(composite)
        self._composite_photos[section] = photo
        label.configure(image=photo, text="")
