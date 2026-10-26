from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable
import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from core import curve as curve_mod
from core import gearing
from gui import theme

HINT_FG, ERROR_FG, WARN_FG = "#777777", "#c0392b", "#a05a00"
VIEWS = ("Engine speed vs road speed", "Drive force vs road speed")
TOP_SPEED_AT = ("Rev limiter", "Peak power")


class GearPanel(ttk.Frame):
    """Gearbox editor. It edits the same fields as the car tab (the variables are shared),
    so either place can be used and they never disagree."""

    NEEDED = (("drivetrain", "gears"), ("drivetrain", "final_drive"), ("drivetrain", "reverse"))

    def __init__(self, master, form, get_curve: Callable[[], list[curve_mod.Point]]):
        super().__init__(master, padding=6)
        self.form, self.get_curve = form, get_curve
        v = form.vars
        self.gears_var = v[("drivetrain", "gears")]
        self.final_var = v[("drivetrain", "final_drive")]
        self.reverse_var = v[("drivetrain", "reverse")]
        self.optional = {name: v.get(key) for name, key in (
            ("max_rpm", ("powertrain", "max_rpm")), ("idle", ("powertrain", "idle_rpm")),
            ("front", ("tires", "front")), ("rear", ("tires", "rear")), ("drive", ("drivetrain", "drive")))}
        self.view_var = tk.StringVar(value=VIEWS[0])
        self.count_var = tk.StringVar(value="5")
        self.first_var = tk.StringVar(value="3.50")
        self.top_var = tk.StringVar(value="0.80")
        self.spacing_var = tk.StringVar(value=list(gearing.SPACINGS)[1])
        self.preset_var = tk.StringVar(value="Choose a preset…")
        self.speed_var = tk.StringVar(value="200")
        self.speed_at_var = tk.StringVar(value=TOP_SPEED_AT[0])
        self.msg_var = tk.StringVar()
        self._after: str | None = None
        self._editor: ttk.Entry | None = None
        self._dirty = True
        self._build()
        for var in (self.gears_var, self.final_var, self.reverse_var, *[x for x in self.optional.values() if x]):
            var.trace_add("write", lambda *_: self.schedule_refresh())
        self.bind("<Map>", lambda _e: self.schedule_refresh(0))

    # ------------------------------------------------------------------ data
    def _gears(self) -> list[float]:
        return gearing.parse_gears(self.gears_var.get())

    def _number(self, var, default: float | None = None) -> float | None:
        try:
            return float(str(var.get()).strip().replace(",", "."))
        except (ValueError, AttributeError):
            return default

    def _setting(self, name: str) -> str:
        var = self.optional.get(name)
        return str(var.get()).strip() if var is not None else ""

    def _redline(self) -> int | None:
        value = self._setting("max_rpm")
        return int(value) if value.isdigit() and int(value) > 0 else None

    def _tyre(self) -> tuple[str, str, float | None]:
        drive = self._setting("drive").upper()
        side, key = ("front", "front") if drive in ("FF", "4WD", "") else ("rear", "rear")
        size = self._setting(key)
        return side, size, gearing.tyre_radius_m(size)

    def _set_gears(self, gears: list[float]):
        self.gears_var.set(gearing.format_gears(gears))

    def _peak_power_rpm(self) -> int | None:
        pts = self.get_curve()
        return max(pts, key=lambda p: p[0] * p[1])[0] if pts else None

    # ------------------------------------------------------------------ layout
    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main = ttk.Panedwindow(self, orient="horizontal")
        main.grid(row=0, column=0, sticky="nsew")
        left, right = ttk.Frame(main, padding=6), ttk.Frame(main, padding=6)
        main.add(left, weight=2)
        main.add(right, weight=3)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        box = ttk.LabelFrame(left, text="Gearbox", padding=6)
        box.grid(row=0, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        cols = ("gear", "ratio", "step", "overall", "speed", "drop")
        self.table = ttk.Treeview(box, columns=cols, show="headings", height=8, selectmode="browse")
        for col, text, width in (("gear", "Gear", 44), ("ratio", "Ratio", 62), ("step", "Step", 52),
                                 ("overall", "Overall", 62), ("speed", "km/h at limit", 86), ("drop", "rpm after shift", 96)):
            self.table.heading(col, text=text)
            self.table.column(col, width=width, anchor="center" if col == "gear" else "e", stretch=True)
        self.table.grid(row=0, column=0, sticky="nsew")
        self.table.tag_configure("reverse", foreground=HINT_FG)
        self.table.tag_configure("bad", foreground=ERROR_FG)
        self.table.bind("<Double-1>", self._begin_edit)
        self.table.bind("<<TreeviewSelect>>", lambda _e: self._plot())
        self.table.bind("<Delete>", lambda _e: self.remove_gear())
        ttk.Label(box, text="Double-click a ratio to edit it. Step = ratio between this gear and the next.",
                  foreground=HINT_FG, wraplength=430).grid(row=1, column=0, sticky="w", pady=(4, 4))
        buttons = ttk.Frame(box)
        buttons.grid(row=2, column=0, sticky="ew")
        ttk.Button(buttons, text="Add gear", command=self.add_gear).pack(side="left")
        ttk.Button(buttons, text="Remove", command=self.remove_gear).pack(side="left", padx=4)
        ttk.Button(buttons, text="Sort 1st → top", command=self.sort_gears).pack(side="left")
        fields = ttk.Frame(box)
        fields.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for col, (label, var, hint) in enumerate((("Final drive", self.final_var, ""), ("Reverse", self.reverse_var, ""))):
            ttk.Label(fields, text=label).grid(row=0, column=col * 2, sticky="w", padx=(0 if col == 0 else 14, 4))
            ttk.Spinbox(fields, textvariable=var, from_=0.5, to=20, increment=0.05, width=8).grid(row=0, column=col * 2 + 1)

        gen = ttk.LabelFrame(left, text="Build a gearbox", padding=8)
        gen.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        gen.columnconfigure(5, weight=1)
        ttk.Label(gen, text="Gears").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(gen, textvariable=self.count_var, from_=3, to=8, width=4).grid(row=0, column=1, padx=(4, 12))
        ttk.Label(gen, text="1st").grid(row=0, column=2, sticky="w")
        ttk.Entry(gen, textvariable=self.first_var, width=6).grid(row=0, column=3, padx=(4, 12))
        ttk.Label(gen, text="Top").grid(row=0, column=4, sticky="w")
        ttk.Entry(gen, textvariable=self.top_var, width=6).grid(row=0, column=5, padx=4, sticky="w")
        ttk.Combobox(gen, textvariable=self.spacing_var, values=list(gearing.SPACINGS), state="readonly",
                     width=26).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(gen, text="Generate gears", command=self.generate).grid(row=1, column=4, columnspan=2, sticky="w",
                                                                           padx=4, pady=(6, 0))
        preset = ttk.Combobox(gen, textvariable=self.preset_var, values=list(gearing.PRESETS), state="readonly", width=26)
        preset.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        preset.bind("<<ComboboxSelected>>", lambda _e: self.apply_preset())
        ttk.Label(gen, text="starting point (gears, final, reverse)", foreground=HINT_FG).grid(
            row=2, column=4, columnspan=2, sticky="w", padx=4, pady=(6, 0))
        ttk.Separator(gen).grid(row=3, column=0, columnspan=6, sticky="ew", pady=8)
        ttk.Label(gen, text="Top speed").grid(row=4, column=0, sticky="w")
        ttk.Entry(gen, textvariable=self.speed_var, width=6).grid(row=4, column=1, padx=(4, 2))
        ttk.Label(gen, text="km/h at").grid(row=4, column=2, sticky="w")
        ttk.Combobox(gen, textvariable=self.speed_at_var, values=TOP_SPEED_AT, state="readonly", width=11).grid(
            row=4, column=3, columnspan=2, padx=4, sticky="w")
        ttk.Button(gen, text="Set final drive", command=self.set_final_for_speed).grid(row=4, column=5, sticky="w")

        self.msg = ttk.Label(left, textvariable=self.msg_var, foreground=HINT_FG, wraplength=470, justify="left")
        self.msg.grid(row=2, column=0, sticky="w", pady=(6, 0))

        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        top = ttk.Frame(right)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(top, text="Chart:").pack(side="left")
        combo = ttk.Combobox(top, textvariable=self.view_var, values=VIEWS, state="readonly", width=30)
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._plot())
        plot = ttk.LabelFrame(right, text="Gearing", padding=6)
        plot.grid(row=1, column=0, sticky="nsew")
        plot.rowconfigure(0, weight=1)
        plot.columnconfigure(0, weight=1)
        self.figure = Figure(figsize=(6, 5), dpi=100, layout="constrained")
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        tb = NavigationToolbar2Tk(self.canvas, plot, pack_toolbar=False)
        tb.update()
        theme.paint_toolbar(tb)
        tb.grid(row=1, column=0, sticky="ew")
        self.summary = ttk.Label(right, text="", justify="left", wraplength=520)
        self.summary.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.warn = ttk.Label(right, text="", foreground=WARN_FG, justify="left", wraplength=520)
        self.warn.grid(row=3, column=0, sticky="w", pady=(2, 0))

    def _say(self, text: str, error: bool = False):
        self.msg_var.set(text)
        self.msg.configure(foreground=ERROR_FG if error else HINT_FG)

    # ------------------------------------------------------------------ actions
    def add_gear(self):
        gears = self._gears()
        new = round(gears[-1] * 0.85, 2) if gears else 3.5
        if len(gears) >= 10:
            self._say("That is plenty of gears (the maximum here is 10).", error=True)
            return
        self._set_gears(gears + [max(new, 0.1)])
        self._say("Added a gear; double-click its ratio to set it.")

    def remove_gear(self):
        gears = self._gears()
        if len(gears) <= 1:
            self._say("A car needs at least one gear.", error=True)
            return
        sel = self.table.selection()
        idx = int(sel[0]) if sel and sel[0].isdigit() and int(sel[0]) < len(gears) else len(gears) - 1
        del gears[idx]
        self._set_gears(gears)

    def sort_gears(self):
        self._set_gears(sorted(self._gears(), reverse=True))

    def apply_preset(self):
        gears, final, reverse = gearing.PRESETS[self.preset_var.get()]
        self._set_gears(gears)
        self.final_var.set(f"{final:.2f}")
        self.reverse_var.set(f"{reverse:.2f}")
        self.count_var.set(str(len(gears)))
        self.first_var.set(gearing.fmt_ratio(gears[0]))
        self.top_var.set(gearing.fmt_ratio(gears[-1]))
        self._say(f"Applied “{self.preset_var.get()}”. Adjust the ratios, then use Top speed to fit the final drive.")

    def generate(self):
        try:
            count = int(float(self.count_var.get()))
            first = float(self.first_var.get().replace(",", "."))
            top = float(self.top_var.get().replace(",", "."))
            if not 1 <= count <= 10 or first <= 0 or top <= 0:
                raise ValueError
        except ValueError:
            self._say("Enter a number of gears (1-10) and positive ratios for 1st and top gear.", error=True)
            return
        if top >= first and count > 1:
            self._say("Top gear's ratio must be smaller than 1st gear's.", error=True)
            return
        self._set_gears(gearing.generate_gears(count, first, top, gearing.SPACINGS[self.spacing_var.get()]))
        self._say(f"Generated {count} gears. Double-click any ratio to fine-tune it.")

    def set_final_for_speed(self):
        gears, redline = self._gears(), self._redline()
        _side, size, radius = self._tyre()
        try:
            speed = float(self.speed_var.get().replace(",", "."))
            if speed <= 0:
                raise ValueError
        except ValueError:
            self._say("Enter the top speed you are aiming for in km/h.", error=True)
            return
        if not gears or radius is None or redline is None:
            self._say("Needs gear ratios, a valid tyre size (car tab) and the rev limiter (car tab).", error=True)
            return
        rpm = redline
        if self.speed_at_var.get() == TOP_SPEED_AT[1]:
            rpm = self._peak_power_rpm() or redline
        final = gearing.final_drive_for_top_speed(speed, rpm, gears[-1], radius)
        if not 0.5 <= final <= 20:
            self._say(f"That would need a final drive of {final:.2f}, outside the sensible 0.5-20 range.", error=True)
            return
        self.final_var.set(f"{final:.2f}")
        self._say(f"Final drive set to {final:.2f}: {speed:g} km/h in top gear at {rpm:,} rpm.")

    # ------------------------------------------------------------------ inline editing
    def _begin_edit(self, event):
        row, col = self.table.identify_row(event.y), self.table.identify_column(event.x)
        gears = self._gears()
        if not row or col != "#2" or not row.isdigit() or int(row) >= len(gears):
            return
        self._end_edit(False)
        bbox = self.table.bbox(row, col)
        if not bbox:
            return
        editor = ttk.Entry(self.table, justify="right")
        editor.insert(0, gearing.fmt_ratio(gears[int(row)]))
        editor.select_range(0, "end")
        editor.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        editor.focus_set()
        editor.bind("<Return>", lambda _e: self._end_edit(True))
        editor.bind("<Escape>", lambda _e: self._end_edit(False))
        editor.bind("<FocusOut>", lambda _e: self._end_edit(True))
        self._editor, self._row = editor, int(row)

    def _end_edit(self, commit: bool):
        editor, self._editor = self._editor, None
        if editor is None:
            return
        text = editor.get().strip().replace(",", ".")
        editor.destroy()
        if not commit:
            return
        gears = self._gears()
        try:
            value = float(text)
            if not 0.1 <= value <= 20:
                raise ValueError
        except ValueError:
            self._say("A gear ratio must be a number between 0.1 and 20.", error=True)
            return
        if self._row < len(gears) and abs(gears[self._row] - value) > 1e-9:
            gears[self._row] = value
            self._set_gears(gears)

    # ------------------------------------------------------------------ refresh
    def schedule_refresh(self, delay: int = 120):
        self._dirty = True
        if self._after is not None:
            self.after_cancel(self._after)
        self._after = self.after(delay, self._refresh)

    def _refresh(self):
        self._after = None
        if not self.winfo_viewable():          # redraw when the tab is shown instead
            return
        self._dirty = False
        gears, final = self._gears(), self._number(self.final_var, 0.0) or 0.0
        redline = self._redline()
        side, size, radius = self._tyre()
        reverse = self._number(self.reverse_var)
        selected = self.table.selection()
        self.table.delete(*self.table.get_children())
        for i, g in enumerate(gears):
            step = f"{g / gears[i + 1]:.2f}" if i + 1 < len(gears) and gears[i + 1] > 0 else ""
            overall = f"{g * final:.2f}" if final else ""
            speed = drop = ""
            if radius and redline and final:
                speed = f"{gearing.speed_kmh(redline, g, final, radius):.0f}"
                if i + 1 < len(gears):
                    drop = f"{gearing.rpm_at(gearing.speed_kmh(redline, g, final, radius), gears[i + 1], final, radius):,.0f}"
            bad = i + 1 < len(gears) and gears[i + 1] >= g
            self.table.insert("", "end", iid=str(i), tags=("bad",) if bad else (),
                              values=(i + 1, gearing.fmt_ratio(g), step, overall, speed, drop))
        if reverse:
            self.table.insert("", "end", iid="R", tags=("reverse",), values=(
                "R", gearing.fmt_ratio(reverse), "", f"{reverse * final:.2f}" if final else "", "", ""))
        if selected and self.table.exists(selected[0]):
            self.table.selection_set(selected[0])

        notes = gearing.issues(gears)
        if radius is None:
            notes.append(f"Tyre size “{size}” isn't valid (e.g. 205/55R16), so speeds can't be worked out.")
        if redline is None:
            notes.append("Set the rev limiter on the car tab to see speeds.")
        if not final:
            notes.append("Final drive is empty or not a number.")
        self.warn.configure(text="\n".join("⚠ " + n for n in notes))
        if gears and radius and redline and final:
            top = gearing.speed_kmh(redline, gears[-1], final, radius)
            first = gearing.speed_kmh(redline, gears[0], final, radius)
            spread = gears[0] / gears[-1] if gears[-1] else 0
            self.summary.configure(
                text=f"Top gear at the rev limiter: {top:.0f} km/h ({top * 0.621371:.0f} mph)   •   "
                     f"1st gear tops out at {first:.0f} km/h   •   ratio spread {spread:.2f}\n"
                     f"Using the {side} tyres {size} (rolling radius {radius * 1000:.0f} mm); "
                     f"overall top gear {gears[-1] * final:.2f}:1.")
        else:
            self.summary.configure(text="")
        self._plot()

    def _plot(self):
        gears, final = self._gears(), self._number(self.final_var, 0.0) or 0.0
        redline, radius = self._redline(), self._tyre()[2]
        idle = self._setting("idle")
        idle = int(idle) if idle.isdigit() and 0 < int(idle) < (redline or 10 ** 9) else 1000
        fig = self.figure
        fig.clear()
        ax = fig.add_subplot(111)
        if not (gears and final and radius and redline):
            ax.text(0.5, 0.5, "Fill in gears, final drive, tyre size\nand rev limiter to see the chart",
                    ha="center", va="center", transform=ax.transAxes, color="#999999")
            ax.set_axis_off()
            self.canvas.draw_idle()
            return
        sel = self.table.selection()
        chosen = int(sel[0]) if sel and sel[0].isdigit() and int(sel[0]) < len(gears) else None
        pts = self.get_curve()
        force_view = self.view_var.get() == VIEWS[1]
        cmap = matplotlib.rcParams["axes.prop_cycle"].by_key()["color"]
        if force_view and not pts:
            ax.text(0.5, 0.5, "The torque curve is empty", ha="center", va="center", transform=ax.transAxes)
            self.canvas.draw_idle()
            return
        top_speed = 0.0
        for i, g in enumerate(gears):
            colour, width = cmap[i % len(cmap)], 3.0 if i == chosen else 1.8
            alpha = 1.0 if chosen in (None, i) else 0.45
            lo = idle
            if force_view:
                xs, ys = gearing.tractive_curve(pts, g, final, radius, lo, redline)
            else:
                xs = [gearing.speed_kmh(r, g, final, radius) for r in (lo, redline)]
                ys = [lo, redline]
            top_speed = max(top_speed, max(xs))
            ax.plot(xs, ys, color=colour, linewidth=width, alpha=alpha)
            ax.annotate(str(i + 1), (xs[-1], ys[-1]), xytext=(4, 0), textcoords="offset points", color=colour,
                        fontsize=10, fontweight="bold", va="center")
            if i + 1 < len(gears) and not force_view:         # the rpm drop when you shift up
                nxt = gearing.rpm_at(xs[-1], gears[i + 1], final, radius)
                ax.plot([xs[-1], xs[-1]], [redline, nxt], color=colour, linestyle=":", linewidth=1.2, alpha=alpha)
        if force_view:
            ax.set_ylabel("Drive force at the wheels (N, estimated)")
            ax.set_ylim(bottom=0)
        else:
            ax.axhline(redline, color="#c0392b", linestyle="--", linewidth=1.2)
            ax.set_ylabel("Engine speed (RPM)")
            ax.set_ylim(0, redline * 1.08)
            peak = self._peak_power_rpm()
            if peak:
                ax.axhline(peak, color="#e07b00", linestyle=":", linewidth=1.2)
                ax.annotate("peak power", (0, peak), xytext=(4, 3), textcoords="offset points", fontsize=8, color="#e07b00")
        ax.set_xlabel("Road speed (km/h)")
        ax.set_xlim(0, top_speed * 1.08)
        ax.set_title("Drive force in each gear" if force_view else "Engine speed in each gear")
        ax.grid(True, alpha=0.28)
        self.canvas.draw_idle()
