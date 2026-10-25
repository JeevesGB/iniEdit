"""Editable x:y curve with live matplotlib plot (generalised torque-curve editor)."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from core import curve as curve_mod
from core.schema import Parameter


class CurvePanel(ttk.Frame):
    def __init__(self, master, param: Parameter, on_change: Callable[[], None] | None = None):
        super().__init__(master, padding=6)
        self.param = param
        self.on_change = on_change or (lambda: None)
        self.points: list[curve_mod.Point] = []
        self.x_var = tk.StringVar()
        self.y_var = tk.StringVar()
        self.limit_var = tk.StringVar(value=str(param.default_display_limit))
        self._build()
        self.set_text(param.default_text(), notify=False)

    # ---- public API -------------------------------------------------
    def get_text(self) -> str:
        return curve_mod.format_curve(self.points)

    def set_text(self, text: str, notify: bool = True) -> None:
        self.points = sorted(curve_mod.parse_curve(text), key=lambda p: p[0])
        self._refresh_all(notify=notify)

    # ---- UI ---------------------------------------------------------
    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main = ttk.Panedwindow(self, orient="horizontal")
        main.grid(row=0, column=0, sticky="nsew")
        left, right = ttk.Frame(main, padding=6), ttk.Frame(main, padding=6)
        main.add(left, weight=1)
        main.add(right, weight=3)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        xl, yl = self.param.x_label, self.param.y_label
        controls = ttk.LabelFrame(left, text="Points", padding=8)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text=xl).grid(row=0, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(controls, textvariable=self.x_var, width=12).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(controls, text=yl).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(controls, textvariable=self.y_var, width=12).grid(row=1, column=1, sticky="ew", pady=3)
        for text, cmd in (("Add point", self.add_point), ("Update selected", self.update_point), ("Remove selected", self.remove_point)):
            ttk.Button(controls, text=text, command=cmd).grid(columnspan=2, sticky="ew", pady=2)

        table_frame = ttk.LabelFrame(left, text=f"Points (max {self.param.max_points})", padding=6)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(table_frame, columns=("x", "y"), show="headings", height=12)
        self.table.heading("x", text=xl.split("(")[0].strip() or "X")
        self.table.heading("y", text=yl.split("(")[0].strip() or "Y")
        self.table.column("x", width=85, anchor="e")
        self.table.column("y", width=105, anchor="e")
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self._on_select)

        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        plot_frame = ttk.LabelFrame(right, text="Live curve", padding=6)
        plot_frame.grid(row=0, column=0, sticky="nsew")
        plot_frame.rowconfigure(0, weight=1)
        plot_frame.columnconfigure(0, weight=1)
        self.figure = Figure(figsize=(7, 5), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar = NavigationToolbar2Tk(self.canvas, plot_frame, pack_toolbar=False)
        toolbar.update()
        toolbar.grid(row=1, column=0, sticky="ew")

        options = ttk.Frame(right)
        options.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(options, text="Display limit:").pack(side="left")
        ttk.Entry(options, textvariable=self.limit_var, width=9).pack(side="left", padx=6)
        ttk.Button(options, text="Update graph", command=self._refresh_plot).pack(side="left")
        ttk.Button(options, text="Load curve…", command=self.load_curve).pack(side="left", padx=(12, 4))
        ttk.Button(options, text="Export curve…", command=self.export_curve).pack(side="left")
        ttk.Button(options, text="Copy curve", command=self.copy_curve).pack(side="left", padx=4)

        summary = ttk.Frame(right)
        summary.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.peak_label = ttk.Label(summary, text="Peak: —")
        self.peak_label.pack(side="left")
        self.output_label = ttk.Label(summary, text="", padding=(20, 0))
        self.output_label.pack(side="left")

    # ---- editing ----------------------------------------------------
    def _read_point(self) -> curve_mod.Point | None:
        try:
            x = int(self.x_var.get().strip())
            y = float(self.y_var.get().strip())
            if x < 0 or y < 0:
                raise ValueError("Values must be zero or greater.")
            return x, y
        except ValueError as exc:
            messagebox.showerror("Invalid point", f"Enter a whole-number X and a valid non-negative Y.\n\nDetails: {exc}")
            return None

    def add_point(self):
        point = self._read_point()
        if point is None:
            return
        if len(self.points) >= self.param.max_points:
            messagebox.showwarning("Point limit", f"At most {self.param.max_points} points are supported.")
            return
        if any(p[0] == point[0] for p in self.points):
            messagebox.showerror("Duplicate X", "A point already exists there. Select it and use Update selected.")
            return
        self.points.append(point)
        self.points.sort(key=lambda p: p[0])
        self._refresh_all()

    def update_point(self):
        selection = self.table.selection()
        if not selection:
            messagebox.showinfo("Select a point", "Select a point in the table first.")
            return
        point = self._read_point()
        if point is None:
            return
        index = int(selection[0])
        if any(i != index and p[0] == point[0] for i, p in enumerate(self.points)):
            messagebox.showerror("Duplicate X", "Another point already exists there.")
            return
        self.points[index] = point
        self.points.sort(key=lambda p: p[0])
        self._refresh_all()

    def remove_point(self):
        selection = self.table.selection()
        if not selection:
            messagebox.showinfo("Select a point", "Select a point in the table first.")
            return
        del self.points[int(selection[0])]
        self._refresh_all()

    def _on_select(self, _event=None):
        selection = self.table.selection()
        if selection:
            x, y = self.points[int(selection[0])]
            self.x_var.set(str(x))
            self.y_var.set(f"{y:g}")

    # ---- refresh ----------------------------------------------------
    def _refresh_all(self, notify: bool = True):
        if self.points:                       # widen the graph so no point is cut off
            try:
                limit = int(self.limit_var.get().strip())
            except ValueError:
                limit = 0
            top = max(p[0] for p in self.points)
            if top > limit:
                self.limit_var.set(str(-(-top // 1000) * 1000))
        for item in self.table.get_children():
            self.table.delete(item)
        for i, (x, y) in enumerate(self.points):
            self.table.insert("", "end", iid=str(i), values=(x, f"{y:g}"))
        self._refresh_plot()
        if notify:
            self.on_change()

    def _refresh_plot(self):
        try:
            limit = int(self.limit_var.get().strip())
            if limit <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid display limit", "Display limit must be a positive whole number.")
            return
        p = self.param
        self.ax.clear()
        self.ax.set_title(p.title or p.label)
        self.ax.set_xlabel(p.x_label)
        self.ax.set_ylabel(p.y_label)
        self.ax.grid(True, alpha=0.28)
        self.ax.set_xlim(0, limit)
        if self.points:
            xs, ys = [q[0] for q in self.points], [q[1] for q in self.points]
            self.ax.plot(xs, ys, marker="o", linewidth=2, markersize=5, label=p.label)
            px, py = curve_mod.peak(self.points)
            self.ax.scatter([px], [py], marker="D", zorder=4, label="Peak")
            self.ax.annotate(f"{py:g} @ {px:,}", (px, py), xytext=(8, 9), textcoords="offset points", fontsize=9)
            self.ax.set_ylim(bottom=0, top=max(ys) * 1.18 if max(ys) > 0 else 1)
            self.peak_label.configure(text=f"Peak: {py:g} @ {px:,}")
            if p.power_readout:
                kw = curve_mod.power_kw(px, py)
                self.output_label.configure(text=f"Power at peak: {kw:.1f} kW / {curve_mod.kw_to_ps(kw):.1f} PS")
            self.ax.legend(loc="best")
        else:
            self.peak_label.configure(text="Peak: —")
            self.output_label.configure(text="")
        self.figure.tight_layout()
        self.canvas.draw_idle()

    # ---- import / export -------------------------------------------
    def copy_curve(self):
        if not self.points:
            messagebox.showwarning("No points", "Add at least one point before copying.")
            return
        self.clipboard_clear()
        self.clipboard_append(f"{self.param.key} = {self.get_text()}")
        self.update()

    def export_curve(self):
        if not self.points:
            messagebox.showwarning("No points", "Add at least one point before exporting.")
            return
        path = filedialog.asksaveasfilename(
            title="Export curve", defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("INI files", "*.ini"), ("All files", "*.*")],
            initialfile=f"{self.param.key}.txt",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(f"{self.param.key} = {self.get_text()}\n")
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))

    def load_curve(self):
        path = filedialog.askopenfilename(
            title="Load curve", filetypes=[("Text and INI files", "*.txt *.ini *.cfg"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                points = curve_mod.parse_curve(fh.read())
            curve_mod.validate_points(points, self.param.max_points)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not load curve", str(exc))
            return
        self.points = sorted(points, key=lambda p: p[0])
        self._refresh_all()

