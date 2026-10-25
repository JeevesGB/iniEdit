"""Main window: schema-driven GT3-revisited mod creator."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.discdata import DiscCars
from core.project import ModProject
from core.schema import FileSpec, Schema, SchemaError, load_schema
from gui.curve_panel import CurvePanel
from gui.disc_browser import DiscBrowser
from gui.model_panel import ModelPanel
from gui.icons import SAVE_ICON, TAB_ICONS, load_icon
from gui.parameter_form import ParameterForm
from gui.paints_panel import PaintsPanel
from gui.preview_panel import PreviewPanel

APP_NAME = "GT3 Mod Creator"
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DEFAULT_SCHEMA = BASE_DIR / "data" / "car_mod_schema.json"
DISC_CARS = BASE_DIR / "data" / "cars.json"


class ModCreatorApp(tk.Tk):
    def __init__(self, schema_path: Path = DEFAULT_SCHEMA):
        super().__init__()
        self._set_window_icon()
        self.geometry("1200x800")
        self.minsize(980, 640)
        self.status_var = tk.StringVar(value="Ready")
        self.mod_id_var = tk.StringVar(value="my_car_mod")
        self.comments_var = tk.BooleanVar(value=True)

        self.disc = DiscCars.load(DISC_CARS)
        self.schema: Schema | None = None
        self.schema_path = schema_path
        self.parent_dir: Path | None = None   # the "mods" folder the mod folder lives in
        self.dirty = False
        self.notebook: ttk.Notebook | None = None
        self.forms: dict[str, ParameterForm] = {}
        self.curve_panels: dict[tuple[str, str, str], CurvePanel] = {}
        self.paint_panels: dict[tuple[str, str], PaintsPanel] = {}
        self.include_vars: dict[str, tk.BooleanVar] = {}
        self.maker_hints: dict[str, ttk.Label] = {}
        self.extras: dict[str, dict[str, dict[str, str]]] = {}
        self._building = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        top = ttk.Frame(self, padding=(10, 8, 10, 0))
        top.grid(row=0, column=0, sticky="ew")
        self.save_icon = load_icon(SAVE_ICON, 20)
        ttk.Button(top, text="Save", image=self.save_icon, compound="left", command=self.save_mod).pack(
            side="left", padx=(0, 16))
        ttk.Label(top, text="Mod folder name (id):").pack(side="left")
        ttk.Entry(top, textvariable=self.mod_id_var, width=28).pack(side="left", padx=6)
        self.mod_id_error = ttk.Label(top, text="", foreground="#c0392b")
        self.mod_id_error.pack(side="left")
        self.mod_id_var.trace_add("write", lambda *_: self._changed())
        self.comments_var.trace_add("write", lambda *_: self._refresh_preview())
        ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken", padding=(8, 4)).grid(
            row=2, column=0, sticky="ew")
        self._build_menu()
        self.protocol("WM_DELETE_WINDOW", self.on_exit)
        for seq, cmd in (("<Control-n>", self.new_mod), ("<Control-o>", self.open_mod),
                         ("<Control-s>", self.save_mod), ("<Control-S>", self.save_mod_as)):
            self.bind(seq, lambda _e, c=cmd: c())

        try:
            self._build_ui(load_schema(schema_path))
        except SchemaError as exc:
            messagebox.showerror("Schema error", str(exc))
            raise SystemExit(1) from exc

    def _set_window_icon(self):
        """Title-bar / taskbar icon (gui/icons/ico.ico); the app runs fine without it."""
        ico = BASE_DIR / "gui" / "icons" / "ico.ico"
        try:
            self.iconbitmap(default=str(ico))
        except tk.TclError:      # missing file, or a platform that can't use .ico
            pass

    # ---- menu -------------------------------------------------------
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
        m.add_command(label="Exit", command=self.on_exit)
        bar.add_cascade(label="File", menu=m)
        o = tk.Menu(bar, tearoff=False)
        o.add_checkbutton(label="Write explanatory comments", variable=self.comments_var)
        o.add_separator()
        o.add_command(label="Load parameter schema…", command=self.choose_schema)
        o.add_command(label="Reset to built-in schema", command=lambda: self._switch_schema(DEFAULT_SCHEMA))
        bar.add_cascade(label="Options", menu=o)
        self.config(menu=bar)

    # ---- construction -----------------------------------------------
    def _build_ui(self, schema: Schema):
        self._building = True
        self.schema = schema
        if self.notebook is not None:
            self.notebook.destroy()
        self.forms.clear(), self.curve_panels.clear(), self.paint_panels.clear(), self.include_vars.clear()
        self.maker_hints.clear()
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

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
            form = ParameterForm(page, spec, on_change=self._changed, lookup=self.disc.lookup,
                                 on_browse=self._browse_donor if self.disc else None)
            form.grid(row=1, column=0, sticky="nsew")
            self.forms[spec.id] = form
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
        self.model_panel = ModelPanel(self.notebook, self, BASE_DIR / "tools" / "prepare.py")
        self._add_tab(self.model_panel, "Model tools", TAB_ICONS["model_tools"])
        self.preview = PreviewPanel(self.notebook, {s.id: f"{s.id}.ini" for s in schema.files})
        self._add_tab(self.preview, "preview", TAB_ICONS["preview"])
        self._building = False
        self._apply_project(ModProject(schema, self.disc))
        self.dirty, self.extras = False, {}
        self._update_title()
        self.status_var.set(f"Schema: {schema.name}")

    def _add_tab(self, widget, title: str, icon: str = ""):
        image = load_icon(icon, 18)
        if image is not None:
            self.notebook.add(widget, text=" " + title.lower(), image=image, compound="left")
        else:
            self.notebook.add(widget, text=title.lower())

    def _browse_donor(self, param):
        form = self.forms.get("car")
        if form is None:
            return
        dialog = DiscBrowser(self, self.disc, current=form.vars[("car", param.key)].get().strip())
        self.wait_window(dialog)
        if dialog.result:
            car, fill = dialog.result
            form.vars[("car", param.key)].set(car.label)
            if fill:
                for (section, key), value in (("drivetrain", "drive"), car.drive), (("body", "weight_kg"), f"{car.weight_kg:g}"):
                    if (section, key) in form.vars:
                        form.vars[(section, key)].set(value)

    # ---- helpers for the model tools tab ----------------------------
    def mod_root(self) -> Path | None:
        """The mod's folder once it has been saved (or opened), else None."""
        mod_id = self.mod_id_var.get().strip()
        return self.parent_dir / mod_id if self.parent_dir and mod_id else None

    def ensure_mod_folder(self) -> Path | None:
        """The mod's folder; offers to save the mod first if it has no folder yet."""
        if self.mod_root() is None:
            if not messagebox.askyesno("Save the mod first",
                                       "The files need a mod folder to go in. Save the mod now?"):
                return None
            if not self.save_mod():
                return None
        return self.mod_root()

    def car_value(self, section: str, key: str) -> str:
        """A value from the car file with placeholders filled in ('' if there is no car file)."""
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

    # ---- project <-> widgets ----------------------------------------
    def _collect(self) -> ModProject:
        project = ModProject(self.schema, self.disc)
        project.mod_id = self.mod_id_var.get().strip()
        for spec in self.schema.files:
            values = {s: dict(items) for s, items in self.forms[spec.id].get_values().items()}
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

    def _update_title(self):
        self.title(f"{'*' if self.dirty else ''}{self.mod_id_var.get() or 'Untitled'} — {APP_NAME}")

    # ---- file actions -----------------------------------------------
    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved changes", "Save changes before continuing?")
        if answer is None:
            return False
        return self.save_mod() if answer else True

    def new_mod(self):
        if not self._confirm_discard():
            return
        project = ModProject(self.schema, self.disc)
        project.mod_id = "my_car_mod"
        self.extras = {}
        self._apply_project(project)
        self.parent_dir, self.dirty = None, False
        self._update_title()

    def open_mod(self):
        if not self._confirm_discard():
            return
        folder = filedialog.askdirectory(title="Open a mod folder (the one containing mod.ini)")
        if not folder:
            return
        project = ModProject(self.schema, self.disc)
        try:
            notes = project.load_folder(folder, choose=self._pick_file)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            messagebox.showerror("Could not open mod", str(exc))
            return
        self._apply_project(project)
        self.parent_dir, self.dirty = Path(folder).parent, False
        self._update_title()
        extra = sum(len(v) for e in self.extras.values() for v in e.values())
        msg = f"Opened {folder}."
        if extra:
            msg += f" {extra} unrecognised entr{'y' if extra == 1 else 'ies'} kept as-is."
        self.status_var.set(" ".join([msg] + notes))

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
        self._update_title()
        self.status_var.set(f"Saved {len(written)} file(s) to {target}")
        stale = project.stale_files(parent, written)
        if stale:
            names = "\n".join(str(p.relative_to(target)) for p in stale)
            messagebox.showwarning("Other .ini files in the mod",
                                   "These files were not written and are still in the mod folder "
                                   f"(for example from an earlier label or maker name):\n\n{names}\n\n"
                                   "The game may load them as extra cars/makers; delete them if they're old.")
        return True

    def on_exit(self):
        if self._confirm_discard():
            self.destroy()
