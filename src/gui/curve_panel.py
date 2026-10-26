from __future__ import annotations
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from core import curve as curve_mod
from core.schema import Parameter
from gui import theme

HINT = ("Drag a point to move it  •  click empty space to add one  •  right-click a point to remove it  "
        "•  hold Shift to move vertically only  •  arrow keys nudge the selection  •  Ctrl+Z / Ctrl+Y")
ERROR_FG, HINT_FG, WARN_FG = "#c0392b", "#777777", "#a05a00"
TORQUE_C, POWER_C, LIMIT_C = "#1f77b4", "#e07b00", "#c0392b"
PICK_PX = 11
UNDO_DEPTH = 100


class CurvePanel(ttk.Frame):
    def __init__(self, master, param: Parameter, on_change: Callable[[], None] | None = None):
        super().__init__(master, padding=6)
        self.param = param
        self.on_change = on_change or (lambda: None)
        self.points: list[curve_mod.Point] = []
        self.max_rpm: int | None = None
        self.idle_rpm: int | None = None
        self._undo: list[list[curve_mod.Point]] = []
        self._redo: list[list[curve_mod.Point]] = []
        self._drag: int | None = None
        self._drag_ylim: tuple[float, float] | None = None
        self._editor: ttk.Entry | None = None
        self._selecting = False
        self.x_var = tk.StringVar()
        self.y_var = tk.StringVar()
        self.limit_var = tk.StringVar(value=str(param.default_display_limit))
        self.unit_var = tk.StringVar(value="kW")
        self.show_power_var = tk.BooleanVar(value=True)
        self.snap_x_var = tk.StringVar(value="100")
        self.snap_y_var = tk.StringVar(value="1")
        self.scale_var = tk.StringVar(value="105")
        self.shift_var = tk.StringVar(value="500")
        self.hint_var = tk.StringVar(value=HINT)
        self._build()
        self.set_text(param.default_text(), notify=False)

    def get_text(self) -> str:
        return curve_mod.format_curve(self.points)

    def set_text(self, text: str, notify: bool = True) -> None:
        self.points = sorted(curve_mod.parse_curve(text), key=lambda p: p[0])
        self._undo.clear()
        self._redo.clear()
        self._refresh_all(notify=notify)

    def set_limits(self, max_rpm: int | None, idle_rpm: int | None) -> None:
        if (max_rpm, idle_rpm) == (self.max_rpm, self.idle_rpm):
            return
        self.max_rpm, self.idle_rpm = max_rpm, idle_rpm
        self._refresh_all(notify=False)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main = ttk.Panedwindow(self, orient="horizontal")
        main.grid(row=0, column=0, sticky="nsew")
        left, right = ttk.Frame(main, padding=6), ttk.Frame(main, padding=6)
        main.add(left, weight=1)
        main.add(right, weight=4)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        xl, yl = self.param.x_label, self.param.y_label
        controls = ttk.LabelFrame(left, text="Selected point", padding=8)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text=xl).grid(row=0, column=0, columnspan=2, sticky="w")
        xe = ttk.Entry(controls, textvariable=self.x_var, width=12)
        xe.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(controls, text=yl).grid(row=2, column=0, columnspan=2, sticky="w")
        ye = ttk.Entry(controls, textvariable=self.y_var, width=12)
        ye.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        for entry in (xe, ye):
            entry.bind("<Return>", lambda _e: self.apply_entry())
        ttk.Button(controls, text="Apply  (Enter)", command=self.apply_entry).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Button(controls, text="Add as new point", command=self.add_point).grid(
            row=5, column=0, sticky="ew", pady=2, padx=(0, 3))
        ttk.Button(controls, text="Remove", command=self.remove_selected).grid(row=5, column=1, sticky="ew", pady=2)
        ttk.Button(controls, text="Split segment", command=self.split_segment).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=2)

        table_frame = ttk.LabelFrame(left, text=f"Points (max {self.param.max_points})", padding=6)
        table_frame.grid(row=1, column=0, sticky="nsew")
        self.table_frame = table_frame
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(table_frame, columns=("x", "y", "p"), show="headings", height=12,
                                  selectmode="extended")
        self.table.heading("x", text="RPM")
        self.table.heading("y", text="Nm")
        self.table.heading("p", text="kW")
        self.table.column("x", width=60, anchor="e")
        self.table.column("y", width=62, anchor="e")
        self.table.column("p", width=62, anchor="e")
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self._on_select)
        self.table.bind("<Double-1>", self._begin_cell_edit)
        ttk.Label(table_frame, text="Double-click a number to edit it.", foreground=HINT_FG).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        plot_frame = ttk.LabelFrame(right, text="Live curve", padding=6)
        plot_frame.grid(row=0, column=0, sticky="nsew")
        plot_frame.rowconfigure(0, weight=1)
        plot_frame.columnconfigure(0, weight=1)
        self.figure = Figure(figsize=(7, 5), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.widget = self.canvas.get_tk_widget()
        self.widget.configure(takefocus=1)
        self.widget.grid(row=0, column=0, sticky="nsew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, plot_frame, pack_toolbar=False)
        self.toolbar.update()
        theme.paint_toolbar(self.toolbar)
        self.toolbar.grid(row=1, column=0, sticky="ew")
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("axes_leave_event", lambda _e: self._set_cursor(""))

        view = ttk.Frame(right)
        view.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Checkbutton(view, text="Show power", variable=self.show_power_var, command=self._refresh_plot).pack(side="left")
        unit = ttk.Combobox(view, textvariable=self.unit_var, values=curve_mod.POWER_UNITS, width=4, state="readonly")
        unit.pack(side="left", padx=(4, 14))
        unit.bind("<<ComboboxSelected>>", lambda _e: self._refresh_all(notify=False))
        ttk.Label(view, text="Snap to:").pack(side="left")
        ttk.Combobox(view, textvariable=self.snap_x_var, values=("1", "10", "50", "100", "250", "500"),
                     width=5).pack(side="left", padx=(4, 2))
        ttk.Label(view, text="rpm,").pack(side="left")
        ttk.Combobox(view, textvariable=self.snap_y_var, values=("0.1", "0.5", "1", "5", "10"),
                     width=4).pack(side="left", padx=(4, 2))
        ttk.Label(view, text="Nm").pack(side="left")
        ttk.Label(view, text="Graph width:").pack(side="left", padx=(14, 0))
        limit = ttk.Entry(view, textvariable=self.limit_var, width=7)
        limit.pack(side="left", padx=4)
        limit.bind("<Return>", lambda _e: self._refresh_plot())
        limit.bind("<FocusOut>", lambda _e: self._refresh_plot())
        ttk.Label(view, text="rpm").pack(side="left")

        tools = ttk.LabelFrame(right, text="Curve tools", padding=6)
        tools.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        row1 = ttk.Frame(tools)
        row1.pack(fill="x")
        self.undo_btn = ttk.Button(row1, text="Undo", width=7, command=self.undo)
        self.undo_btn.pack(side="left")
        self.redo_btn = ttk.Button(row1, text="Redo", width=7, command=self.redo)
        self.redo_btn.pack(side="left", padx=(4, 14))
        ttk.Label(row1, text="Torque").pack(side="left")
        se = ttk.Entry(row1, textvariable=self.scale_var, width=5)
        se.pack(side="left", padx=3)
        ttk.Label(row1, text="%").pack(side="left")
        ttk.Button(row1, text="Scale", width=7, command=self.do_scale).pack(side="left", padx=(3, 14))
        ttk.Label(row1, text="Move all by").pack(side="left")
        sh = ttk.Entry(row1, textvariable=self.shift_var, width=6)
        sh.pack(side="left", padx=3)
        ttk.Label(row1, text="rpm").pack(side="left")
        ttk.Button(row1, text="Shift", width=7, command=self.do_shift).pack(side="left", padx=(3, 14))
        ttk.Button(row1, text="Smooth", width=8, command=self.do_smooth).pack(side="left")
        row2 = ttk.Frame(tools)
        row2.pack(fill="x", pady=(6, 0))
        ttk.Button(row2, text="Generate from specs…", command=self.open_generator).pack(side="left")
        self.trim_btn = ttk.Button(row2, text="End at rev limiter", command=self.do_fit_limit)
        self.trim_btn.pack(side="left", padx=4)
        ttk.Button(row2, text="Paste", width=7, command=self.paste_curve).pack(side="left")
        ttk.Button(row2, text="Load…", width=7, command=self.load_curve).pack(side="left", padx=4)
        ttk.Button(row2, text="Export…", width=8, command=self.export_curve).pack(side="left")
        ttk.Button(row2, text="Copy", width=6, command=self.copy_curve).pack(side="left", padx=4)
        ttk.Button(row2, text="Reset", width=6, command=self.reset_curve).pack(side="left")
        for entry in (se, sh):
            entry.bind("<Return>", lambda _e: None)

        summary = ttk.Frame(right)
        summary.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.peak_label = ttk.Label(summary, text="Peak torque: —")
        self.peak_label.pack(side="left")
        self.output_label = ttk.Label(summary, text="", padding=(20, 0))
        self.output_label.pack(side="left")
        self.warn_label = ttk.Label(summary, text="", foreground=WARN_FG)
        self.warn_label.pack(side="left")
        self.hint_label = ttk.Label(right, textvariable=self.hint_var, foreground=HINT_FG, wraplength=760)
        self.hint_label.grid(row=4, column=0, sticky="w", pady=(4, 0))

        for w in (self.widget, self.table, xe, ye):
            self._bind_keys(w)
        self.widget.bind("<Delete>", lambda _e: self.remove_selected())
        self.widget.bind("<BackSpace>", lambda _e: self.remove_selected())
        self.table.bind("<Delete>", lambda _e: self.remove_selected())
        for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0), ("Up", 0, 1), ("Down", 0, -1)):
            self.widget.bind(f"<{key}>", lambda _e, a=dx, b=dy: self._nudge(a, b))

    def _bind_keys(self, widget):
        widget.bind("<Control-z>", lambda _e: (self.undo(), "break")[1])
        widget.bind("<Control-y>", lambda _e: (self.redo(), "break")[1])
        widget.bind("<Control-Z>", lambda _e: (self.redo(), "break")[1])

    def _say(self, text: str = "", error: bool = False):
        self.hint_var.set(text or HINT)
        self.hint_label.configure(foreground=ERROR_FG if error else HINT_FG)

    def _snap(self, var: tk.StringVar, default: float) -> float:
        try:
            value = float(var.get().replace(",", "."))
            return value if value > 0 else default
        except ValueError:
            return default

    def _selected(self) -> list[int]:
        return sorted(int(i) for i in self.table.selection() if int(i) < len(self.points))

    def _push_undo(self):
        self._undo.append(list(self.points))
        del self._undo[:-UNDO_DEPTH]
        self._redo.clear()

    def _commit(self, new_points: list[curve_mod.Point], select: list[curve_mod.Point] | None = None,
                push: bool = True):
        if push:
            self._push_undo()
        self.points = sorted(new_points, key=lambda p: p[0])
        keep = [self.points.index(p) for p in (select or []) if p in self.points]
        self._refresh_all(select=keep)

    def undo(self):
        if not self._undo:
            self._say("Nothing to undo.")
            return
        self._redo.append(list(self.points))
        self.points = self._undo.pop()
        self._refresh_all()

    def redo(self):
        if not self._redo:
            self._say("Nothing to redo.")
            return
        self._undo.append(list(self.points))
        self.points = self._redo.pop()
        self._refresh_all()

    def _check_x(self, x: int, ignore: int | None = None) -> bool:
        if any(i != ignore and p[0] == x for i, p in enumerate(self.points)):
            self._say(f"There is already a point at {x:,} rpm. Select it to change it.", error=True)
            return False
        return True

    def _read_entry(self) -> curve_mod.Point | None:
        try:
            x = int(round(float(self.x_var.get().strip().replace(",", ""))))
            y = float(self.y_var.get().strip().replace(",", "."))
            if x < 0 or y < 0:
                raise ValueError("values must be zero or greater")
            return x, round(y, 2)
        except ValueError:
            self._say("Enter the rpm as a whole number and the torque as a number (zero or more).", error=True)
            return None

    def apply_entry(self):
        point = self._read_entry()
        if point is None:
            return
        sel = self._selected()
        if len(sel) == 1:
            if not self._check_x(point[0], ignore=sel[0]):
                return
            pts = list(self.points)
            pts[sel[0]] = point
            self._commit(pts, select=[point])
            self._say()
        else:
            self.add_point()

    def add_point(self):
        point = self._read_entry()
        if point is None:
            return
        if len(self.points) >= self.param.max_points:
            self._say(f"At most {self.param.max_points} points are supported.", error=True)
            return
        if not self._check_x(point[0]):
            return
        self._commit(self.points + [point], select=[point])
        self._say()

    def remove_selected(self):
        sel = self._selected()
        if not sel:
            self._say("Select a point first (click it in the table or on the graph).", error=True)
            return
        if len(sel) >= len(self.points):
            self._say("A curve needs at least one point.", error=True)
            return
        self._commit([p for i, p in enumerate(self.points) if i not in sel])
        self._say()

    def split_segment(self):
        sel = self._selected()
        if not sel:
            self._say("Select a point; a new one is added halfway to the next point.", error=True)
            return
        i = sel[0]
        if i >= len(self.points) - 1:
            self._say("The last point has no next point to split towards.", error=True)
            return
        if len(self.points) >= self.param.max_points:
            self._say(f"At most {self.param.max_points} points are supported.", error=True)
            return
        (x0, y0), (x1, y1) = self.points[i], self.points[i + 1]
        mid = ((x0 + x1) // 2, round((y0 + y1) / 2, 1))
        if not self._check_x(mid[0]):
            return
        self._commit(self.points + [mid], select=[mid])

    def _nudge(self, dx: int, dy: int):
        sel = self._selected()
        if not sel:
            return "break"
        sx, sy = self._snap(self.snap_x_var, 100), self._snap(self.snap_y_var, 1)
        pts = list(self.points)
        moved = []
        for i in sel:
            x, y = pts[i]
            nx, ny = max(0, int(round(x + dx * sx))), max(0.0, round(y + dy * sy, 2))
            if any(j != i and j not in sel and p[0] == nx for j, p in enumerate(pts)):
                continue
            pts[i] = (nx, ny)
            moved.append(pts[i])
        if moved and len({p[0] for p in pts}) == len(pts):
            self._commit(pts, select=moved)
        return "break"

    def do_scale(self):
        try:
            percent = float(self.scale_var.get().replace(",", "."))
            if percent <= 0:
                raise ValueError
        except ValueError:
            self._say("Scale: enter a percentage above zero, e.g. 105 for +5 %.", error=True)
            return
        if self.points:
            self._commit(curve_mod.scale_torque(self.points, percent))
            self._say(f"Torque scaled to {percent:g} %.")

    def do_shift(self):
        try:
            delta = int(round(float(self.shift_var.get().replace(",", ""))))
        except ValueError:
            self._say("Shift: enter a whole number of rpm (negative moves the curve down).", error=True)
            return
        if self.points and delta:
            self._commit(curve_mod.shift_rpm(self.points, delta))
            self._say(f"Curve moved by {delta:+,} rpm.")

    def do_smooth(self):
        if len(self.points) < 3:
            self._say("Smoothing needs at least three points.", error=True)
            return
        self._commit(curve_mod.smooth(self.points))
        self._say("Smoothed (end points unchanged).")

    def do_fit_limit(self):
        if not self.max_rpm:
            self._say("Set the rev limiter on the car tab first.", error=True)
            return
        if self.points:
            self._commit(curve_mod.fit_to_limit(self.points, self.max_rpm, self.param.max_points))
            self._say(f"Curve now ends exactly at the rev limiter ({self.max_rpm:,} rpm).")

    def reset_curve(self):
        if self.points and not messagebox.askyesno("Reset curve", "Replace the curve with the default one?",
                                                   parent=self):
            return
        self._commit(curve_mod.parse_curve(self.param.default_text()))

    def paste_curve(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        points = curve_mod.parse_loose(text)
        if not points:
            self._say("The clipboard has no rpm/torque pairs. Copy 'rpm:Nm' text or two spreadsheet columns.", error=True)
            return
        try:
            curve_mod.validate_points(points, self.param.max_points)
        except ValueError as exc:
            self._say(f"Paste failed: {exc}", error=True)
            return
        self._commit(points)
        self._say(f"Pasted {len(points)} points.")

    def open_generator(self):
        GeneratorDialog(self, self)

    def set_generated(self, points: list[curve_mod.Point]):
        self._commit(points)
        self._say(f"Generated {len(points)} points. Fine-tune them on the graph (Undo restores the old curve).")

    def _on_select(self, _event=None):
        if self._selecting:
            return
        sel = self._selected()
        if sel:
            x, y = self.points[sel[0]]
            self.x_var.set(str(x))
            self.y_var.set(f"{y:g}")
        self._refresh_plot()

    def _begin_cell_edit(self, event):
        if self.table.identify_region(event.x, event.y) != "cell":
            return
        col = self.table.identify_column(event.x)
        row = self.table.identify_row(event.y)
        if not row or col not in ("#1", "#2"):
            return
        self._end_cell_edit(commit=True)
        bbox = self.table.bbox(row, col)
        if not bbox:
            return
        index, which = int(row), 0 if col == "#1" else 1
        editor = ttk.Entry(self.table, justify="right")
        editor.insert(0, f"{self.points[index][which]:g}")
        editor.select_range(0, "end")
        editor.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        editor.focus_set()
        editor.bind("<Return>", lambda _e: self._end_cell_edit(True))
        editor.bind("<Escape>", lambda _e: self._end_cell_edit(False))
        editor.bind("<FocusOut>", lambda _e: self._end_cell_edit(True))
        self._editor, self._editing = editor, (index, which)

    def _end_cell_edit(self, commit: bool):
        editor, self._editor = self._editor, None
        if editor is None:
            return
        index, which = self._editing
        text = editor.get().strip().replace(",", ".")
        editor.destroy()
        if not commit or index >= len(self.points):
            return
        try:
            value = float(text)
            if value < 0:
                raise ValueError
            x, y = self.points[index]
            new = (int(round(value)), y) if which == 0 else (x, round(value, 2))
        except ValueError:
            self._say("That is not a valid number (it must be zero or more).", error=True)
            return
        if new == self.points[index] or not self._check_x(new[0], ignore=index):
            return
        pts = list(self.points)
        pts[index] = new
        self._commit(pts, select=[new])

    def _display(self, point: curve_mod.Point) -> tuple[float, float]:
        return self.ax.transData.transform(point)

    def _hit(self, event) -> int | None:
        best, best_d = None, PICK_PX * theme.SCALE
        for i, p in enumerate(self.points):
            px, py = self._display(p)
            d = ((px - event.x) ** 2 + (py - event.y) ** 2) ** 0.5
            if d <= best_d:
                best, best_d = i, d
        return best

    def _in_plot(self, event) -> bool:
        return event.x is not None and self.ax.bbox.contains(event.x, event.y)

    def _data(self, event, shift_only_from: curve_mod.Point | None = None) -> curve_mod.Point:
        x, y = self.ax.transData.inverted().transform((event.x, event.y))
        sx, sy = self._snap(self.snap_x_var, 100), self._snap(self.snap_y_var, 1)
        nx, ny = max(0, int(round(round(x / sx) * sx))), max(0.0, round(round(y / sy) * sy, 2))
        if shift_only_from is not None:
            nx = shift_only_from[0]
        return nx, ny

    def _set_cursor(self, cursor: str):
        try:
            self.widget.configure(cursor=cursor)
        except tk.TclError:
            pass

    def _on_press(self, event):
        self.widget.focus_set()
        self._end_cell_edit(commit=True)
        if self.toolbar.mode or not self._in_plot(event):
            return
        hit = self._hit(event)
        if event.button == 3:
            if hit is not None:
                self.table.selection_set(str(hit))
                self.remove_selected()
            return
        if event.button != 1:
            return
        if hit is None:
            if len(self.points) >= self.param.max_points:
                self._say(f"At most {self.param.max_points} points are supported.", error=True)
                return
            new = self._data(event)
            if not self._check_x(new[0]):
                return
            self._push_undo()
            self.points.append(new)
            self.points.sort(key=lambda p: p[0])
            hit = self.points.index(new)
        else:
            self._push_undo()
        self._drag = hit
        self._drag_ylim = self.ax.get_ylim()
        self._select_rows([hit])
        self._set_cursor("fleur")
        self._redraw_drag()

    def _on_motion(self, event):
        if self._drag is None:
            if self.toolbar.mode or not self._in_plot(event):
                self._set_cursor("")
                return
            hit = self._hit(event)
            self._set_cursor("hand2" if hit is not None else "crosshair")
            self._show_tooltip(hit, event)
            return
        if event.x is None:
            return
        i = self._drag
        locked = event.key == "shift"
        x, y = self._data(event, shift_only_from=self.points[i] if locked else None)
        lo = self.points[i - 1][0] + 1 if i > 0 else 0
        hi = self.points[i + 1][0] - 1 if i < len(self.points) - 1 else 10 ** 6
        x = min(max(x, lo), hi)
        self.points[i] = (x, y)
        self._redraw_drag()

    def _on_release(self, event):
        if self._drag is None:
            return
        i, self._drag, self._drag_ylim = self._drag, None, None
        self._set_cursor("")
        if self._undo and self._undo[-1] == self.points:    
            self._undo.pop()
        self._refresh_all(select=[i])
        self._say()

    def _redraw_drag(self):
        i = self._drag
        if i is None:
            return
        x, y = self.points[i]
        self.x_var.set(str(x))
        self.y_var.set(f"{y:g}")
        row = str(i)
        if self.table.exists(row):
            self.table.item(row, values=self._row_values(x, y))
        self._refresh_plot()
        self._say(f"{x:,} rpm  •  {y:g} Nm  •  {curve_mod.power_in(self.unit_var.get(), x, y):.1f} {self.unit_var.get()}")

    def _show_tooltip(self, hit: int | None, event):
        ann = getattr(self, "_tip", None)
        if ann is None:
            return
        if hit is None:
            if ann.get_visible():
                ann.set_visible(False)
                self.canvas.draw_idle()
            return
        x, y = self.points[hit]
        unit = self.unit_var.get()
        ann.set_text(f"{x:,} rpm\n{y:g} Nm\n{curve_mod.power_in(unit, x, y):.1f} {unit}")
        ann.xy = (x, y)
        ann.set_visible(True)
        self.canvas.draw_idle()

    def _select_rows(self, indexes: list[int]):
        self._selecting = True
        try:
            rows = [str(i) for i in indexes if self.table.exists(str(i))]
            self.table.selection_set(rows)
            if rows:
                self.table.see(rows[0])
        finally:
            self._selecting = False

    def _row_values(self, x, y):
        return (x, f"{y:g}", f"{curve_mod.power_in(self.unit_var.get(), x, y):.1f}")

    def _display_limit(self) -> int:
        try:
            value = int(float(self.limit_var.get().strip().replace(",", "")))
            if value > 0:
                return value
        except ValueError:
            pass
        return self.param.default_display_limit

    def _refresh_all(self, notify: bool = True, select: list[int] | None = None):
        if select is None:
            select = self._selected()
        tops = [p[0] for p in self.points] + ([self.max_rpm] if self.max_rpm else [])
        if tops and max(tops) > self._display_limit():           # widen so nothing is cut off
            self.limit_var.set(str(-(-max(tops) // 1000) * 1000))
        self._selecting = True
        try:
            self.table.heading("p", text=self.unit_var.get())
            for item in self.table.get_children():
                self.table.delete(item)
            for i, (x, y) in enumerate(self.points):
                self.table.insert("", "end", iid=str(i), values=self._row_values(x, y))
            keep = [str(i) for i in select if i < len(self.points)]
            if keep:
                self.table.selection_set(keep)
        finally:
            self._selecting = False
        self.table_frame.configure(text=f"Points ({len(self.points)} of {self.param.max_points})")
        self.undo_btn.state(["!disabled"] if self._undo else ["disabled"])
        self.redo_btn.state(["!disabled"] if self._redo else ["disabled"])
        self.trim_btn.state(["!disabled"] if self.max_rpm else ["disabled"])
        self._refresh_plot()
        if notify:
            self.on_change()

    def _refresh_plot(self):
        p, unit = self.param, self.unit_var.get()
        limit = self._display_limit()
        self.figure.clear()
        self._tip = None
        self.ax = ax = self.figure.add_subplot(111)
        ax.set_title(p.title or p.label)
        ax.set_xlabel(p.x_label)
        ax.set_ylabel(p.y_label, color=TORQUE_C)
        ax.grid(True, alpha=0.28)
        ax.set_xlim(0, limit)
        handles = []
        if self.max_rpm:
            ax.axvline(self.max_rpm, color=LIMIT_C, linestyle="--", linewidth=1.3)
            if self.max_rpm < limit:
                ax.axvspan(self.max_rpm, limit, color=LIMIT_C, alpha=0.07)
            ax.annotate(f"rev limiter {self.max_rpm:,}", (self.max_rpm, 1), xycoords=("data", "axes fraction"),
                        xytext=(-4, -4), textcoords="offset points", ha="right", va="top", fontsize=8, color=LIMIT_C)
        if self.idle_rpm and self.idle_rpm < limit:
            ax.axvline(self.idle_rpm, color="#888888", linestyle=":", linewidth=1)
            ax.annotate("idle", (self.idle_rpm, 0), xycoords=("data", "axes fraction"), xytext=(3, 4),
                        textcoords="offset points", fontsize=8, color="#888888")
        if self.points:
            xs, ys = [q[0] for q in self.points], [q[1] for q in self.points]
            handles += ax.plot(xs, ys, marker="o", linewidth=2, markersize=6, color=TORQUE_C, label=p.label, zorder=3)
            sel = self._selected()
            if sel:
                ax.scatter([xs[i] for i in sel], [ys[i] for i in sel], s=150, facecolors="none",
                           edgecolors="#222222", linewidths=1.8, zorder=5)
            px, py = curve_mod.peak(self.points)
            ax.annotate(f"{py:g} Nm @ {px:,}", (px, py), xytext=(8, 9), textcoords="offset points", fontsize=9,
                        color=TORQUE_C)
            top = max(ys) * 1.18 if max(ys) > 0 else 1
            ax.set_ylim(self._drag_ylim if self._drag_ylim else (0, top))
            self.peak_label.configure(text=f"Peak torque: {py:g} Nm @ {px:,} rpm")
            if p.power_readout:
                pk_rpm, pk_nm = max(self.points, key=lambda q: q[0] * q[1])
                val = curve_mod.power_in(unit, pk_rpm, pk_nm)
                other = "PS" if unit != "PS" else "kW"
                self.output_label.configure(
                    text=f"Peak power: {val:.1f} {unit} @ {pk_rpm:,} rpm  ({curve_mod.power_in(other, pk_rpm, pk_nm):.0f} {other})")
                pk = (pk_rpm, val)
                if self.show_power_var.get():
                    ax2 = ax.twinx()
                    first, last = xs[0], xs[-1]
                    grid = [first + (last - first) * i / 120 for i in range(121)]
                    pw = [curve_mod.power_in(unit, r, curve_mod.interpolate(self.points, r)) for r in grid]
                    handles += ax2.plot(grid, pw, color=POWER_C, linewidth=1.8, linestyle="--", label=f"Power ({unit})")
                    ax2.scatter([pk[0]], [val], marker="D", color=POWER_C, zorder=4)
                    ax2.set_ylabel(f"Power ({unit})", color=POWER_C)
                    ax2.set_ylim(0, (max(pw) * 1.18) if max(pw) > 0 else 1)
                    ax2.tick_params(axis="y", colors=POWER_C)
            else:
                self.output_label.configure(text="")
            ax.legend(handles=handles, loc="lower right", fontsize=9)
            self._tip = ax.annotate("", (0, 0), xytext=(14, 14), textcoords="offset points", fontsize=9, zorder=10,
                                    bbox=dict(boxstyle="round,pad=0.35", fc="#ffffe0", ec="#888888"), annotation_clip=False)
            self._tip.set_visible(False)
        else:
            self.peak_label.configure(text="Peak torque: —")
            self.output_label.configure(text="")
            ax.set_ylim(0, 200)
            ax.text(0.5, 0.5, "Click here to add the first point", transform=ax.transAxes, ha="center", color="#999999")
        warn = ""
        if self.points and self.max_rpm:
            last = max(q[0] for q in self.points)
            if last > self.max_rpm:
                warn = f"⚠ curve goes past the rev limiter ({self.max_rpm:,}). Use “End at rev limiter”."
            elif last < self.max_rpm:
                warn = f"Curve ends {self.max_rpm - last:,} rpm below the rev limiter."
        self.warn_label.configure(text=warn, padding=(20, 0) if warn else 0)
        self.figure.set_layout_engine("constrained")
        self.canvas.draw_idle()

    def copy_curve(self):
        if not self.points:
            self._say("Add at least one point before copying.", error=True)
            return
        self.clipboard_clear()
        self.clipboard_append(f"{self.param.key} = {self.get_text()}")
        self.update()
        self._say("Copied to the clipboard.")

    def export_curve(self):
        if not self.points:
            messagebox.showwarning("No points", "Add at least one point before exporting.")
            return
        path = filedialog.asksaveasfilename(
            title="Export curve", defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("INI files", "*.ini"), ("All files", "*.*")],
            initialfile=f"{self.param.key}.txt",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                if path.lower().endswith(".csv"):
                    fh.write("rpm,torque_nm,power_kw\n")
                    for x, y in self.points:
                        fh.write(f"{x},{y:g},{curve_mod.power_kw(x, y):.2f}\n")
                else:
                    fh.write(f"{self.param.key} = {self.get_text()}\n")
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))

    def load_curve(self):
        path = filedialog.askopenfilename(
            title="Load curve", filetypes=[("Text, INI and CSV files", "*.txt *.ini *.cfg *.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                points = curve_mod.parse_loose(fh.read())
            curve_mod.validate_points(points, self.param.max_points)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not load curve", str(exc))
            return
        self._commit(points)


class GeneratorDialog(tk.Toplevel):

    def __init__(self, master, panel: CurvePanel):
        super().__init__(master)
        self.panel = panel
        self.title("Generate a torque curve")
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        pts = panel.points
        pk_t = curve_mod.peak(pts) or (4500, 180.0)
        pk_p = curve_mod.peak_power(pts) or (6500, 110.0)
        self.vars = {
            "tq": tk.StringVar(value=f"{pk_t[1]:g}"), "tq_rpm": tk.StringVar(value=str(pk_t[0])),
            "pw": tk.StringVar(value=f"{pk_p[1]:.0f}"), "pw_rpm": tk.StringVar(value=str(pk_p[0])),
            "unit": tk.StringVar(value="kW"),
            "idle": tk.StringVar(value=str(panel.idle_rpm or 850)),
            "limit": tk.StringVar(value=str(panel.max_rpm or max(pk_p[0] + 1000, 7000))),
        }
        body = ttk.Frame(self, padding=14)
        body.grid()
        ttk.Label(body, text="Enter the figures from the car's spec sheet.\nThe curve is built to hit both peaks.",
                  foreground=HINT_FG).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        rows = (("Peak torque", "tq", "Nm", "at", "tq_rpm"), ("Peak power", "pw", None, "at", "pw_rpm"))
        for r, (label, key, unit, at, rkey) in enumerate(rows, start=1):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(body, textvariable=self.vars[key], width=8).grid(row=r, column=1, padx=4)
            if unit:
                ttk.Label(body, text=unit).grid(row=r, column=2, sticky="w")
            else:
                ttk.Combobox(body, textvariable=self.vars["unit"], values=curve_mod.POWER_UNITS, width=4,
                             state="readonly").grid(row=r, column=2, sticky="w")
            ttk.Label(body, text=f"{at}").grid(row=r, column=3, padx=(8, 4))
            ttk.Entry(body, textvariable=self.vars[rkey], width=7).grid(row=r, column=4)
            ttk.Label(body, text="rpm").grid(row=r, column=5, padx=(3, 0))
        ttk.Label(body, text="Idle speed").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(body, textvariable=self.vars["idle"], width=8).grid(row=3, column=1, padx=4)
        ttk.Label(body, text="rpm").grid(row=3, column=2, sticky="w")
        ttk.Label(body, text="Rev limiter").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(body, textvariable=self.vars["limit"], width=8).grid(row=4, column=1, padx=4)
        ttk.Label(body, text="rpm").grid(row=4, column=2, sticky="w")
        self.error = ttk.Label(body, text="", foreground=ERROR_FG, wraplength=380, justify="left")
        self.error.grid(row=5, column=0, columnspan=6, sticky="w", pady=(8, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=6, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Generate", command=self.generate).pack(side="right", padx=6)
        self.bind("<Return>", lambda _e: self.generate())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def generate(self):
        v = self.vars
        try:
            tq, pw = float(v["tq"].get().replace(",", ".")), float(v["pw"].get().replace(",", "."))
            tq_rpm, pw_rpm = int(float(v["tq_rpm"].get())), int(float(v["pw_rpm"].get()))
            idle, limit = int(float(v["idle"].get())), int(float(v["limit"].get()))
            if min(tq, pw) <= 0:
                raise ValueError("Torque and power must be above zero.")
            kw = pw * {"kW": 1.0, "PS": 1 / 1.3596216, "hp": curve_mod.KW_PER_HP}[v["unit"].get()]
            points = curve_mod.generate(tq, tq_rpm, kw, pw_rpm, idle, limit, self.panel.param.max_points)
        except ValueError as exc:
            self.error.configure(text=str(exc) if str(exc) and "could not convert" not in str(exc)
                                 else "Please fill every box with a number.")
            return
        self.panel.set_generated(points)
        self.destroy()
