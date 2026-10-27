from __future__ import annotations
import os
import re
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from core import settings
from gui import icons as icons_mod, theme, tooltip
from core.discdata import DiscCars
from core.project import ModProject
from core.schema import FileSpec, Schema, SchemaError, load_schema
from gui.curve_panel import CurvePanel
from gui.disc_browser import DiscBrowser
from gui.gear_panel import GearPanel
from gui.guide import GuideWindow
from gui.model_panel import ModelPanel
from gui.icons import SAVE_ICON, TAB_ICONS, load_icon
from gui.parameter_form import ParameterForm
from gui.paints_panel import PaintsPanel
from gui.preview_panel import PreviewPanel
from gui.start_dialog import NewModDialog, StartDialog

APP_NAME = "GT3 Mod Creator"
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DEFAULT_SCHEMA = BASE_DIR / "data" / "car_mod_schema.json"
DISC_CARS = BASE_DIR / "data" / "cars.json"
BANNER_BG, BANNER_FG = "#fff6d6", "#5a4a00"
TIPS = {
    # torque curve tab
    "Apply  (Enter)": "Change the selected point to the values above (or add a point if none is selected).",
    "Add as new point": "Add a point with the rpm and torque typed above.",
    "Remove": "Remove the selected point(s) or gear.",
    "Split segment": "Add a point halfway between the selected point and the next one.",
    "Undo": "Undo the last change (Ctrl+Z).",
    "Redo": "Redo (Ctrl+Y).",
    "Scale": "Multiply every torque value by the percentage (105 = 5% more).",
    "Shift": "Move every point up or down the rev range by this many rpm.",
    "Smooth": "Average each point with its neighbours. The first and last points stay put.",
    "Generate from specs\u2026": "Build a curve from peak torque, peak power, idle and rev limiter.",
    "End at rev limiter": "Remove points past the rev limiter and end the curve exactly on it.",
    "Paste": "Paste rpm:Nm text, or two spreadsheet columns, from the clipboard.",
    "Load\u2026": "Load a curve from a .txt, .ini or .csv file.",
    "Export\u2026": "Save the curve as .txt, .ini or .csv.",
    "Copy": "Copy this to the clipboard.",
    "Reset": "Go back to the default curve.",
    "Show power": "Draw the power curve on a second axis.",
    # gearbox tab
    "Add gear": "Add another gear below the last one.",
    "Sort 1st \u2192 top": "Order the ratios from largest (1st) to smallest (top).",
    "Generate gears": "Make this many gears between the 1st and top ratio.",
    "Set final drive": "Work out the final drive that gives the top speed at the chosen rpm.",
}
TOOLBAR_TIPS = {
    "Save": "Save the mod's .ini files (Ctrl+S).",
    "Open folder": "Show the mod folder in the file browser.",
}
TIPS_TEXT = ("Getting started:  1) fill in the Mod and Car tabs (* = required)   "
             "2) add your 3D model under Model tools   3) press Save, and check the Preview tab.")


class ModCreatorApp(tk.Tk):
    def __init__(self, schema_path: Path = DEFAULT_SCHEMA):
        super().__init__()
        theme.init_scale(self)
        icons_mod.SCALE = theme.SCALE
        self.theme_var = tk.StringVar(value=settings.get("theme", "xp") if settings.get("theme", "xp") in theme.THEMES else "xp")
        theme.apply(self, self.theme_var.get())
        self._set_window_icon()
        self.geometry(f"{theme.px(1200)}x{theme.px(800)}")
        self.minsize(theme.px(980), theme.px(640))
        self.help_var = tk.BooleanVar(value=bool(settings.get("show_help", True)))
        self.saved_var = tk.StringVar(value="Not saved yet")
        self.last_saved: str | None = None
        self.status_var = tk.StringVar(value="Ready")
        self.mod_id_var = tk.StringVar(value="my_car_mod")
        self.comments_var = tk.BooleanVar(value=True)

        self.disc = DiscCars.load(DISC_CARS)
        self.schema: Schema | None = None
        self.schema_path = schema_path
        self.parent_dir: Path | None = None   
        self.dirty = False
        self.notebook: ttk.Notebook | None = None
        self.forms: dict[str, ParameterForm] = {}
        self.curve_panels: dict[tuple[str, str, str], CurvePanel] = {}
        self.gear_panels: dict[str, GearPanel] = {}
        self.paint_panels: dict[tuple[str, str], PaintsPanel] = {}
        self.include_vars: dict[str, tk.BooleanVar] = {}
        self.maker_hints: dict[str, ttk.Label] = {}
        self.form_pages: dict[str, ttk.Frame] = {}  
        self.tab_base: dict[str, str] = {}          
        self.issues: list[str] = []
        self.extras: dict[str, dict[str, dict[str, str]]] = {}
        self._building = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        top = ttk.Frame(self, padding=(10, 8, 10, 0))
        top.grid(row=0, column=0, sticky="ew")
        self.save_icon = load_icon(SAVE_ICON, 20)
        ttk.Button(top, text="Save", image=self.save_icon, compound="left", command=self.save_mod).pack(
            side="left", padx=(0, 16))
        ttk.Label(top, text="Mod folder name (id):").pack(side="left")
        ttk.Entry(top, textvariable=self.mod_id_var, width=28).pack(side="left", padx=6)
        self.mod_id_error = ttk.Label(top, text="", foreground="#c0392b")
        self.mod_id_error.pack(side="left")
        self.problems_btn = ttk.Button(top, text="No problems", command=self.show_problems, state="disabled")
        self.problems_btn.pack(side="right")
        loc = ttk.Frame(self, padding=(10, 4, 10, 0))
        loc.grid(row=1, column=0, sticky="ew")
        self.location_var = tk.StringVar()
        ttk.Label(loc, textvariable=self.location_var, foreground="#666666").pack(side="left")
        self.folder_btn = ttk.Button(loc, text="Open folder", command=self.open_folder, state="disabled")
        self.folder_btn.pack(side="left", padx=10)
        self.banner = tk.Frame(self, bg=BANNER_BG, padx=10, pady=6)
        tk.Label(self.banner, text=TIPS_TEXT, bg=BANNER_BG, fg=BANNER_FG, justify="left", anchor="w",
                 wraplength=820).pack(side="left", fill="x", expand=True)
        ttk.Button(self.banner, text="Dismiss", command=self.hide_banner).pack(side="right")
        ttk.Button(self.banner, text="Quick guide", command=self.show_guide).pack(side="right", padx=6)
        self.banner.grid(row=2, column=0, sticky="ew", padx=8, pady=(6, 0))
        if settings.load().get("hide_tips"):
            self.banner.grid_remove()
        self.mod_id_var.trace_add("write", lambda *_: self._changed())
        self.comments_var.trace_add("write", lambda *_: self._refresh_preview())
        status = ttk.Frame(self)
        status.grid(row=4, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.status_var, anchor="w", relief="sunken", padding=(8, 4)).grid(
            row=0, column=0, sticky="ew")
        ttk.Label(status, textvariable=self.saved_var, anchor="e", relief="sunken", padding=(10, 4), width=24).grid(
            row=0, column=1, sticky="ew")
        self._build_menu()
        self.protocol("WM_DELETE_WINDOW", self.on_exit)
        for seq, cmd in (("<F1>", self.show_guide), ("<Control-n>", self.new_mod), ("<Control-o>", self.open_mod),
                         ("<Control-s>", self.save_mod), ("<Control-S>", self.save_mod_as)):
            self.bind(seq, lambda _e, c=cmd: c())

        tooltip.attach_by_text(self, TOOLBAR_TIPS)
        tooltip.attach(self.problems_btn, "List everything that needs attention. Double-click an item to jump to it.")
        try:
            self._build_ui(load_schema(schema_path))
        except SchemaError as exc:
            messagebox.showerror("Schema error", str(exc))
            raise SystemExit(1) from exc
        self._restore_window()
        self.after(150, self._startup_prompt)     

    def _startup_prompt(self):
        while True:
            dialog = StartDialog(self, settings.recent_mods())
            self.wait_window(dialog)
            if dialog.result == "new" and self.new_mod():
                return
            if dialog.result == "open" and self.open_mod():
                return
            if dialog.result == "recent" and self.open_mod(dialog.folder):
                return
            if dialog.result is None:            
                return

    def _set_window_icon(self):
        ico = BASE_DIR / "gui" / "icons" / "ico.ico"
        try:
            self.iconbitmap(default=str(ico))
        except tk.TclError:     
            pass

    def _build_menu(self):
        bar = tk.Menu(self)
        m = tk.Menu(bar, tearoff=False)
        m.add_command(label="New mod", accelerator="Ctrl+N", command=self.new_mod)
        m.add_command(label="Open mod folder…", accelerator="Ctrl+O", command=self.open_mod)
        m.add_command(label="Open single .ini file…", command=self.open_single)
        m.add_separator()
        m.add_command(label="Save mod", accelerator="Ctrl+S", command=self.save_mod)
        m.add_command(label="Save mod to folder…", accelerator="Ctrl+Shift+S", command=self.save_mod_as)
        m.add_separator()
        m.add_command(label="Show mod folder in file browser", command=self.open_folder)
        m.add_separator()
        m.add_command(label="Exit", command=self.on_exit)
        bar.add_cascade(label="File", menu=m)
        o = tk.Menu(bar, tearoff=False)
        o.add_checkbutton(label="Write explanatory comments", variable=self.comments_var)
        o.add_separator()
        o.add_checkbutton(label="Show help text under fields", variable=self.help_var, command=self._toggle_help)
        t = tk.Menu(o, tearoff=False)
        for key, label in theme.THEMES.items():
            t.add_radiobutton(label=label, value=key, variable=self.theme_var, command=self._set_theme)
        o.add_cascade(label="Theme", menu=t)
        o.add_separator()
        o.add_command(label="Load parameter schema…", command=self.choose_schema)
        o.add_command(label="Reset to built-in schema", command=lambda: self._switch_schema(DEFAULT_SCHEMA))
        bar.add_cascade(label="Options", menu=o)
        h = tk.Menu(bar, tearoff=False)
        h.add_command(label="Quick guide", accelerator="F1", command=self.show_guide)
        h.add_command(label="Show getting-started tips", command=self.show_banner)
        bar.add_cascade(label="Help", menu=h)
        self.config(menu=bar)

    def _build_ui(self, schema: Schema):
        self._building = True
        self.schema = schema
        if self.notebook is not None:
            self.notebook.destroy()
        self.forms.clear(), self.curve_panels.clear(), self.paint_panels.clear(), self.include_vars.clear()
        self.gear_panels.clear()
        self.maker_hints.clear(), self.form_pages.clear(), self.tab_base.clear()
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=3, column=0, sticky="nsew", padx=8, pady=8)

        for spec in schema.files:
            page = ttk.Frame(self.notebook)
            page.columnconfigure(0, weight=1)
            page.rowconfigure(1, weight=1)
            if spec.optional:
                var = tk.BooleanVar(value=True)
                var.trace_add("write", lambda *_: self._changed())
                self.include_vars[spec.id] = var
                bar = ttk.Frame(page)
                bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
                ttk.Checkbutton(bar, text=f"Include a {spec.title.lower()} file in this mod", variable=var).pack(side="left")
                hint = ttk.Label(bar, text="", foreground="#a05a00")
                hint.pack(side="left", padx=12)
                self.maker_hints[spec.id] = hint
            form = ParameterForm(
                page, spec,
                on_change=self._changed,
                lookup=self.disc.lookup,
                on_browse=self._browse_donor if self.disc else None,
                on_image_browse=self._browse_image,
                resolve_image=self._resolve_image_path,
            )
            form.grid(row=1, column=0, sticky="nsew")
            self.forms[spec.id] = form
            self.form_pages[spec.id] = page
            self._add_tab(page, spec.title, TAB_ICONS.get(spec.id, ""))

        for spec in schema.files:
            for sec in spec.sections:
                if sec.kind == "paints":
                    panel = PaintsPanel(self.notebook, sec.paint_defaults, on_change=self._changed)
                    self.paint_panels[(spec.id, sec.name)] = panel
                    self._add_tab(panel, sec.title, TAB_ICONS.get(sec.name, ""))
                for param in sec.parameters:
                    if param.type == "curve":
                        panel = CurvePanel(self.notebook, param, on_change=self._changed)
                        self.curve_panels[(spec.id, sec.name, param.key)] = panel
                        self._add_tab(panel, param.label, TAB_ICONS.get(param.type, ""))
                        self._link_powertrain(spec.id, panel)
        for form in self.forms.values():
            form.set_help_visible(self.help_var.get())
        self.model_panel = ModelPanel(self.notebook, self, BASE_DIR / "tools" / "prepare.py")
        self._add_tab(self.model_panel, "Model tools", TAB_ICONS["model_tools"])
        self.preview = PreviewPanel(self.notebook, {s.id: f"{s.id}.ini" for s in schema.files})
        self._add_tab(self.preview, "preview", TAB_ICONS["preview"])
        self._building = False
        self._apply_project(ModProject(schema, self.disc))
        self.dirty, self.extras = False, {}
        tooltip.attach_by_text(self.notebook, TIPS)
        theme.restyle_canvases(self.notebook)
        self._update_title()
        self.status_var.set(f"Schema: {schema.name}")

    def _link_powertrain(self, file_id: str, curve_panel: CurvePanel):
        form = self.forms.get(file_id)
        if form is None:
            return
        limit, idle = form.vars.get(("powertrain", "max_rpm")), form.vars.get(("powertrain", "idle_rpm"))

        def push(*_):
            def num(var):
                text = str(var.get()).strip() if var is not None else ""
                return int(text) if text.isdigit() and int(text) > 0 else None
            curve_panel.set_limits(num(limit), num(idle))

        for var in (limit, idle):
            if var is not None:
                var.trace_add("write", push)
        push()
        if all(key in form.vars for key in GearPanel.NEEDED):
            gears = GearPanel(self.notebook, form, get_curve=lambda: list(curve_panel.points))
            self.gear_panels[file_id] = gears
            self._add_tab(gears, "Gearbox", TAB_ICONS["gearbox"])
            curve_panel.on_change = self._curve_changed(curve_panel.on_change, gears)

    @staticmethod
    def _curve_changed(original, gears: GearPanel):
        def changed():
            original()
            gears.schedule_refresh()
        return changed

    def _add_tab(self, widget, title: str, icon: str = ""):
        self.tab_base[str(widget)] = title.lower()
        image = load_icon(icon, 18)
        if image is not None:
            self.notebook.add(widget, text=" " + title.lower(), image=image, compound="left")
        else:
            self.notebook.add(widget, text=title.lower())

    def _browse_donor(self, param):
        """Disc-car picker for donor or sound_id (same list, different purpose)."""
        form = self.forms.get("car")
        if form is None or not self.disc:
            return
        purpose = "sound" if (param.browse == "sound" or param.key == "sound_id") else "donor"
        # sound_id lives under [powertrain]; donor under [car]
        section = "powertrain" if purpose == "sound" else "car"
        ident = (section, param.key)
        current = ""
        if ident in form.vars:
            current = form.vars[ident].get().strip()
        elif (param.key,) and any(k == param.key for (_, k) in form.vars):
            for (sec, key), var in form.vars.items():
                if key == param.key:
                    current = var.get().strip()
                    section = sec
                    ident = (sec, key)
                    break

        dialog = DiscBrowser(self, self.disc, current=current, purpose=purpose)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        if purpose == "sound":
            # result is numeric sound bank id string, or "" to clear
            form.vars[ident].set(dialog.result if dialog.result is not None else "")
            return
        car, fill = dialog.result
        form.vars[ident].set(car.label)
        # Always set Drive from the donor (user can change it afterwards).
        if ("drivetrain", "drive") in form.vars and car.drive:
            form.vars[("drivetrain", "drive")].set(car.drive)
        # Optional: also copy curb weight when requested.
        if fill and ("body", "weight_kg") in form.vars:
            form.vars[("body", "weight_kg")].set(f"{car.weight_kg:g}")

    def _resolve_image_path(self, raw: str) -> Path | None:
        """Turn a typed path into a filesystem path under the mod (or absolute).

        Bare names like ``logo.png`` are treated as ``images/logo.png``.
        Paths already starting with ``images/`` or absolute paths are used as-is.
        """
        text = (raw or "").strip().replace("\\", "/")
        if not text:
            return None
        p = Path(text)
        if p.is_absolute():
            return p if p.is_file() else None
        root = self.mod_root()
        if root is None:
            return None
        # Prefer as written
        candidate = root / text
        if candidate.is_file():
            return candidate
        # Bare filename → images/<name>
        if "/" not in text and "\\" not in text:
            under = root / "images" / text
            if under.is_file():
                return under
        return candidate if candidate.exists() else None

    def _browse_image(self, param, var: tk.Variable) -> None:
        """Pick an image, copy it into the mod's images/ folder, set a relative path."""
        root = self.ensure_mod_folder()
        if root is None:
            return
        images_dir = root / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        initial = images_dir
        current = str(var.get()).strip().replace("\\", "/")
        if current:
            resolved = self._resolve_image_path(current)
            if resolved and resolved.is_file():
                initial = resolved.parent

        path = filedialog.askopenfilename(
            title=f"Choose {param.label or 'image'}",
            initialdir=str(initial),
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                ("PNG", "*.png"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        src = Path(path)
        # Always land in images/ with a clean relative path
        dest_name = src.name
        dest = images_dir / dest_name
        try:
            if src.resolve() != dest.resolve():
                if dest.exists():
                    if not messagebox.askyesno(
                        "Replace image?",
                        f"{dest_name} already exists in images/.\nReplace it?",
                    ):
                        # Still point at the existing file
                        var.set(f"images/{dest_name}")
                        return
                import shutil
                shutil.copy2(src, dest)
        except OSError as exc:
            messagebox.showerror("Could not copy image", str(exc))
            return
        # Store as images/<name> so it works even if the user later types a bare name
        var.set(f"images/{dest_name}")

    def mod_root(self) -> Path | None:
        mod_id = self.mod_id_var.get().strip()
        return self.parent_dir / mod_id if self.parent_dir and mod_id else None

    def ensure_mod_folder(self) -> Path | None:
        if self.mod_root() is None:
            if not messagebox.askyesno("Save the mod first",
                                       "The files need a mod folder to go in. Save the mod now?"):
                return None
            if not self.save_mod():
                return None
        return self.mod_root()

    def car_value(self, section: str, key: str) -> str:
        if self.schema is None or "car" not in self.forms:
            return ""
        return self._collect().resolved_docs()["car"].get(section, key).strip()

    def set_car_values(self, values: dict[tuple[str, str], str]) -> int:
        form, n = self.forms.get("car"), 0
        for (section, key), value in values.items():
            if form is not None and (section, key) in form.vars:
                form.vars[(section, key)].set(value)
                n += 1
        return n

    def choose_schema(self):
        path = filedialog.askopenfilename(title="Load parameter schema", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if path:
            self._switch_schema(Path(path))

    def _switch_schema(self, path: Path):
        if not self._confirm_discard():
            return
        try:
            self._build_ui(load_schema(path))
            self.schema_path = path
        except SchemaError as exc:
            messagebox.showerror("Schema error", str(exc))

    def _normalize_image_path(self, raw: str) -> str:
        """Prefer images/<name> when the user typed only a filename."""
        text = (raw or "").strip().replace("\\", "/")
        if not text or text.startswith("images/") or Path(text).is_absolute() or "/" in text:
            return text
        # Bare filename → images/<name>
        return f"images/{text}"

    def _collect(self) -> ModProject:
        project = ModProject(self.schema, self.disc)
        project.mod_id = self.mod_id_var.get().strip()
        for spec in self.schema.files:
            values = {s: dict(items) for s, items in self.forms[spec.id].get_values().items()}
            # Normalize bare image filenames to images/<name>
            for sec in spec.sections:
                for param in sec.parameters:
                    if param.browse == "image" and sec.name in values and param.key in values[sec.name]:
                        values[sec.name][param.key] = self._normalize_image_path(values[sec.name][param.key])
            for (fid, section, key), panel in self.curve_panels.items():
                if fid == spec.id:
                    values.setdefault(section, {})[key] = panel.get_text()
            for (fid, section), panel in self.paint_panels.items():
                if fid == spec.id:
                    values[section] = panel.get_paints()
            for section, items in self.extras.get(spec.id, {}).items():
                for key, value in items.items():
                    values.setdefault(section, {}).setdefault(key, value)
            project.docs[spec.id].values = values
            project.include[spec.id] = self.include_vars[spec.id].get() if spec.id in self.include_vars else True
        return project

    def _apply_project(self, project: ModProject):
        self._building = True
        try:
            self.mod_id_var.set(project.mod_id or self.mod_id_var.get())
            for spec in self.schema.files:
                doc = project.docs[spec.id]
                self.forms[spec.id].set_values(doc.values, fill_defaults=False)
                if spec.id in self.include_vars:
                    self.include_vars[spec.id].set(project.include[spec.id])
                for (fid, section, key), panel in self.curve_panels.items():
                    if fid == spec.id:
                        panel.set_text(doc.get(section, key), notify=False)
                for (fid, section), panel in self.paint_panels.items():
                    if fid == spec.id:
                        panel.set_paints(doc.values.get(section, {}), notify=False)
                self.extras[spec.id] = doc.unknown_entries(spec)
        finally:
            self._building = False
        self._refresh_preview()

    def _changed(self):
        if self._building or self.schema is None:
            return
        self.dirty = True
        self._update_title()
        self._refresh_preview()

    def _refresh_preview(self):
        if self._building or self.schema is None or not hasattr(self, "preview"):
            return
        project = self._collect()
        rendered = project.render(comments=self.comments_var.get())
        for spec in self.schema.files:
            if spec.id in rendered:
                rel, text = rendered[spec.id]
                self.preview.show(spec.id, text, rel)
            else:
                self.preview.show_disabled(spec.id)
        issues = project.validate()
        maker = project.docs["car"].get("car", "maker").strip() if "car" in project.docs else ""
        for hint in self.maker_hints.values():
            hint.configure(text=f"'{maker}' already has cars on the disc, so it may not need its own maker file."
                           if self.disc and self.disc.has_maker(maker) else "")
        mod_issue = next((i for i in issues if i.startswith("Mod folder name")), "")
        self.mod_id_error.configure(text=mod_issue.replace("Mod folder name: ", ""))
        self.status_var.set("All values valid." if not issues else f"{len(issues)} issue(s). First: {issues[0]}")
        self.issues = issues
        self.problems_btn.configure(text=f"Problems ({len(issues)})" if issues else "No problems")
        self.problems_btn.state(["!disabled"] if issues else ["disabled"])
        self._update_badges(issues)

    def _tab_for_issue(self, issue: str):
        if self.schema is None:
            return None
        low = issue.lower()
        for spec in self.schema.files:
            prefix = f"{spec.title}: ".lower()
            if not low.startswith(prefix):
                continue
            rest = issue[len(prefix):]
            for (fid, section, key), panel in self.curve_panels.items():
                if fid == spec.id and f"[{section}] {key}" in rest:
                    return panel
            for (fid, section), panel in self.paint_panels.items():
                if fid == spec.id and rest.startswith(f"[{section}]"):
                    return panel
            if spec.id in self.gear_panels and any(f"[drivetrain] {k}" in rest for k in ("gears", "final_drive", "reverse")):
                return self.gear_panels[spec.id]
            return self.form_pages.get(spec.id)
        return None

    def _update_badges(self, issues: list[str]):
        counts: dict[str, int] = {}
        for issue in issues:
            widget = self._tab_for_issue(issue)
            if widget is not None:
                counts[str(widget)] = counts.get(str(widget), 0) + 1
        for path, base in self.tab_base.items():
            n = counts.get(path, 0)
            try:
                self.notebook.tab(path, text=" " + base + (f"  \u26a0 {n}" if n else ""))
            except tk.TclError:
                pass

    def show_problems(self):
        if not self.issues:
            return
        win = tk.Toplevel(self)
        win.title("Problems")
        win.transient(self)
        ttk.Label(win, text="Double-click a problem to go to it. Problems never stop you saving.",
                  padding=(10, 10, 10, 4)).pack(anchor="w")
        box = tk.Listbox(win, width=90, height=min(16, len(self.issues)), exportselection=False)
        for issue in self.issues:
            box.insert("end", issue)
        box.pack(fill="both", expand=True, padx=10)

        def go(_event=None):
            sel = box.curselection()
            widget = self._tab_for_issue(self.issues[sel[0]]) if sel else None
            if widget is not None:
                self.notebook.select(widget)
                win.destroy()

        box.bind("<Double-1>", go)
        box.bind("<Return>", go)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=8)
        win.bind("<Escape>", lambda _e: win.destroy())

    def show_guide(self):
        GuideWindow(self)

    def hide_banner(self):
        self.banner.grid_remove()
        settings.update(hide_tips=True)

    def show_banner(self):
        self.banner.grid()
        settings.update(hide_tips=False)

    def _update_location(self):
        if not hasattr(self, "location_var"):
            return
        root = self.mod_root()
        if root is None:
            text = "Not saved yet: Save will ask where to put the mod folder."
        elif root.is_dir():
            text = f"Mod folder: {root}"
        else:
            text = f"Will be created at: {root}"
        self.location_var.set(text)
        self.folder_btn.state(["!disabled"] if root is not None and root.is_dir() else ["disabled"])

    def open_folder(self):
        root = self.mod_root()
        if root is None or not root.is_dir():
            messagebox.showinfo("No folder yet", "The mod folder doesn't exist yet. Save the mod first.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(root)                      # noqa: S606 (Windows only)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(root)])
        except OSError as exc:
            messagebox.showerror("Could not open the folder", str(exc))

    def _update_title(self):
        self.title(f"{'*' if self.dirty else ''}{self.mod_id_var.get() or 'Untitled'} — {APP_NAME}")
        if self.dirty:
            self.saved_var.set("\u25cf Unsaved changes")
        else:
            self.saved_var.set(f"\u2714 Saved at {self.last_saved}" if self.last_saved else "Not saved yet")
        self._update_location()

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved changes", "Save changes before continuing?")
        if answer is None:
            return False
        return self.save_mod() if answer else True

    def new_mod(self) -> bool:
        if not self._confirm_discard():
            return False
        dialog = NewModDialog(self, initial_dir=self.parent_dir or settings.last_parent())
        self.wait_window(dialog)
        if dialog.result is None:
            return False
        mod_id, parent = dialog.result
        project = ModProject(self.schema, self.disc)
        project.mod_id = mod_id
        try:
            root = project.create_work_folders(parent)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not create the mod folder", str(exc))
            return False
        self.extras = {}
        self._apply_project(project)
        self.parent_dir, self.dirty = parent, True    # nothing saved yet: ask before closing
        settings.update(last_parent=str(parent))
        if self.notebook is not None:
            self.notebook.select(0)
        self._update_title()
        self.status_var.set(f"Created {root} with folders: {', '.join(project.work_folders())}. "
                            "Fill in the Mod and Car tabs, then press Save.")
        return True

    def open_mod(self, folder: str | Path | None = None) -> bool:
        if not self._confirm_discard():
            return False
        folder = folder or filedialog.askdirectory(title="Open a mod folder (the one containing mod.ini)")
        if not folder:
            return False
        project = ModProject(self.schema, self.disc)
        try:
            notes = project.load_folder(folder, choose=self._pick_file)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            messagebox.showerror("Could not open mod", str(exc))
            return False
        self._apply_project(project)
        self.parent_dir, self.dirty = Path(folder).parent, False
        self._update_title()
        settings.add_recent(folder)
        extra = sum(len(v) for e in self.extras.values() for v in e.values())
        msg = f"Opened {folder}."
        if extra:
            msg += f" {extra} unrecognised entr{'y' if extra == 1 else 'ies'} kept as-is."
        self.status_var.set(" ".join([msg] + notes))
        return True

    def open_single(self):
        path = filedialog.askopenfilename(title="Open a single .ini", filetypes=[("INI files", "*.ini"), ("All files", "*.*")])
        if not path:
            return
        project = self._collect()
        try:
            fid = project.load_single(path)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            messagebox.showerror("Could not open file", str(exc))
            return
        self._apply_project(project)
        self.dirty = True
        self._update_title()
        self.status_var.set(f"Loaded {Path(path).name} into the {self.schema.file(fid).title} tab.")

    def _pick_file(self, spec: FileSpec, candidates: list[Path]) -> Path | None:
        dialog = tk.Toplevel(self)
        dialog.title(f"Which {spec.title.lower()} file?")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text=f"Several {spec.title.lower()} files found. Choose one to edit:", padding=10).pack()
        box = tk.Listbox(dialog, height=min(10, len(candidates)), width=48, exportselection=False)
        for p in candidates:
            box.insert("end", p.name)
        box.selection_set(0)
        box.pack(padx=10)
        result: list[Path | None] = [None]

        def ok(_e=None):
            sel = box.curselection()
            result[0] = candidates[sel[0]] if sel else candidates[0]
            dialog.destroy()

        box.bind("<Double-1>", ok)
        ttk.Button(dialog, text="Open", command=ok).pack(pady=10)
        self.wait_window(dialog)
        return result[0]

    def save_mod(self) -> bool:
        return self._save(self.parent_dir) if self.parent_dir else self.save_mod_as()

    def save_mod_as(self) -> bool:
        folder = filedialog.askdirectory(title="Choose the mods folder to create the mod folder in")
        return bool(folder) and self._save(Path(folder), ask_overwrite=True)

    def _save(self, parent: Path, ask_overwrite: bool = False) -> bool:
        project = self._collect()
        issues = project.validate()
        if issues:
            shown = "\n".join(issues[:12]) + (f"\n…and {len(issues) - 12} more" if len(issues) > 12 else "")
            if not messagebox.askyesno("Validation issues", f"Some values need attention:\n\n{shown}\n\nSave anyway?"):
                return False
        if not project.mod_id:
            messagebox.showerror("Can't save", "Enter a mod folder name first.")
            return False
        target = parent / project.mod_id
        if ask_overwrite and (target / "mod.ini").exists():
            if not messagebox.askyesno("Folder exists", f"{target} already contains a mod.\nOverwrite its .ini files? "
                                                       "(images and models are left alone)"):
                return False
        try:
            written = project.save(parent, comments=self.comments_var.get())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Save failed", str(exc))
            return False
        self.parent_dir, self.dirty = parent, False
        self.last_saved = datetime.now().strftime("%H:%M")
        self._update_title()
        settings.add_recent(target)
        self.status_var.set(f"Saved {len(written)} file(s) to {target}")
        stale = project.stale_files(parent, written)
        if stale:
            names = "\n".join(str(p.relative_to(target)) for p in stale)
            messagebox.showwarning("Other .ini files in the mod",
                                   "These files were not written and are still in the mod folder "
                                   f"(for example from an earlier label or maker name):\n\n{names}\n\n"
                                   "The game may load them as extra cars/makers; delete them if they're old.")
        return True

    def _toggle_help(self):
        settings.update(show_help=bool(self.help_var.get()))
        for form in self.forms.values():
            form.set_help_visible(self.help_var.get())

    def _set_theme(self):
        name = self.theme_var.get()
        settings.update(theme=name)
        theme.apply(self, name)
        theme.restyle_canvases(self)
        theme.restyle_figures(*self.curve_panels.values(), *self.gear_panels.values())
        self.status_var.set(f"Theme: {theme.THEMES[name]}. Some widgets finish updating when you next restart.")

    def _save_window_state(self):
        try:
            tab = self.notebook.select()
            settings.update(geometry=self.geometry() if self.state() != "zoomed" else settings.get("geometry", ""),
                            zoomed=self.state() == "zoomed", last_tab=self.tab_base.get(tab, ""))
        except tk.TclError:
            pass

    def _restore_window(self):
        match = re.fullmatch(r"(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?", str(settings.get("geometry", "")))
        if match:
            w, h = int(match[1]), int(match[2])
            w, h = min(w, self.winfo_screenwidth()), min(h, self.winfo_screenheight())
            geo = f"{max(w, theme.px(980))}x{max(h, theme.px(640))}"
            if match[3] and match[4]:
                x, y = int(match[3]), int(match[4])
                if -20 <= x <= self.winfo_screenwidth() - 120 and 0 <= y <= self.winfo_screenheight() - 120:
                    geo += f"{x:+d}{y:+d}"
            self.geometry(geo)
        if settings.get("zoomed"):
            try:
                self.state("zoomed")
            except tk.TclError:
                pass
        wanted = settings.get("last_tab", "")
        for path, base in self.tab_base.items():
            if wanted and base == wanted and path != str(getattr(self, "preview", "")):
                try:
                    self.notebook.select(path)
                except tk.TclError:
                    pass

    def on_exit(self):
        if self._confirm_discard():
            self._save_window_state()
            self.destroy()
