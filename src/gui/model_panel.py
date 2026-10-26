from __future__ import annotations
import queue
import shutil
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable
from core import modeltools, settings
from core.modeltools import ModelToolError
from gui.icons import load_icon

GLB = [("3D model (.glb)", "*.glb"), ("All files", "*.*")]
IMAGES = [("Pictures", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")]
BODY_LABELS = {"length_mm": "length", "width_mm": "width", "height_mm": "height",
               "wheelbase_mm": "wheelbase", "front_track_mm": "front track", "rear_track_mm": "rear track"}
HINT_FG = "#666666"

class ModelPanel(ttk.Frame):
    def __init__(self, master, app, prepare_script: Path):
        super().__init__(master, padding=12)
        self.app, self.prepare_script = app, prepare_script
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)
        self.blender_var = tk.StringVar(value=self._load_blender())
        self.status_var = tk.StringVar()
        self.dims_var = tk.StringVar(value="No sizes measured yet.")
        self.viewer_var = tk.StringVar()
        self.dims: dict[str, int] = {}
        self.buttons: list[ttk.Button] = []
        self._queue: queue.Queue = queue.Queue()
        self._done: Callable[[object], None] | None = None

        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        head.columnconfigure(1, weight=1)
        self.header_icon = load_icon("model_tools", 36)
        if self.header_icon is not None:
            ttk.Label(head, image=self.header_icon).grid(row=0, column=0, rowspan=2, padx=(0, 10))
        ttk.Label(head, text="Model tools", font=("TkDefaultFont", 13, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(head, textvariable=self.status_var, foreground=HINT_FG).grid(row=1, column=1, sticky="w")

        f = self._group(1, "1  Add your 3D body", "Pick the way that matches the file you have.")
        row = ttk.Frame(f)
        row.grid(row=1, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)
        self._choice(row, 0, "I have a finished .glb", "Copies it into the mod and measures it.",
                     "Choose .glb…", self.use_finished)
        self._choice(row, 1, "I have a CarConcept-style .glb", "Cleans it up with Blender, then does the same.",
                     "Choose model…", self.convert)
        bl = ttk.Frame(f)
        bl.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        bl.columnconfigure(1, weight=1)
        ttk.Label(bl, text="Blender (only for the second option):", foreground=HINT_FG).grid(row=0, column=0, sticky="w")
        ttk.Entry(bl, textvariable=self.blender_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(bl, text="Find…", command=self.browse_blender).grid(row=0, column=2)

        f = self._group(2, "2  Fill in the sizes", "The body's length, width and height (and wheelbase and tracks "
                        "after a Blender conversion) go into the car tab's body section.")
        ttk.Label(f, textvariable=self.dims_var).grid(row=1, column=0, sticky="w")
        bar = ttk.Frame(f)
        bar.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self._button(bar, "Measure the mod's body", self.measure_current).pack(side="left")
        self._button(bar, "Fill in car tab", self.apply_dims).pack(side="left", padx=8)

        f = self._group(3, "3  Dealer pictures", "Take a screenshot of the car in the game's car viewer, then pick it here.")
        bar = ttk.Frame(f)
        bar.grid(row=1, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)
        ttk.Entry(bar, textvariable=self.viewer_var, state="readonly").grid(row=0, column=0, sticky="ew")
        ttk.Button(bar, text="Copy viewer command", command=self.copy_viewer).grid(row=0, column=1, padx=(6, 0))
        self._button(f, "Choose screenshot and make pictures…", self.make_pictures).grid(
            row=2, column=0, sticky="w", pady=(6, 0))

        ttk.Label(self, text="What happened", foreground=HINT_FG).grid(row=4, column=0, sticky="w", pady=(6, 0))
        box = ttk.Frame(self)
        box.grid(row=5, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.log_text = tk.Text(box, height=6, wrap="word", state="disabled", font=("Consolas", 10))
        sb = ttk.Scrollbar(box, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.bind("<Map>", lambda _e: self._refresh())
        self.after(100, self._poll)

    def _group(self, row: int, title: str, note: str) -> ttk.LabelFrame:
        f = ttk.LabelFrame(self, text=title, padding=10)
        f.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        f.columnconfigure(0, weight=1)
        ttk.Label(f, text=note, foreground=HINT_FG, wraplength=900, justify="left").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        return f

    def _choice(self, parent, col: int, title: str, note: str, button: str, command: Callable):
        box = ttk.Frame(parent, padding=(0, 0, 12, 0))
        box.grid(row=0, column=col, sticky="nsew")
        ttk.Label(box, text=title, font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Label(box, text=note, foreground=HINT_FG, wraplength=380, justify="left").pack(anchor="w", pady=(0, 4))
        self._button(box, button, command).pack(anchor="w")

    def _button(self, parent, text: str, command: Callable) -> ttk.Button:
        b = ttk.Button(parent, text=text, command=command)
        self.buttons.append(b)
        return b

    def _load_blender(self) -> str:
        try:
            saved = settings.load().get("blender", "")
            if saved and Path(saved).is_file():
                return saved
        except (OSError, ValueError):
            pass
        return modeltools.find_blender()

    def browse_blender(self):
        path = filedialog.askopenfilename(title="Find the Blender program (blender.exe)")
        if path:
            self.blender_var.set(path)
            settings.update(blender=path)

    def _refresh(self):
        label = self.app.car_value("car", "label")
        self.viewer_var.set(f'GT3R_VIEWER="find=mod:{label},clean=1,yaw=2.35,pitch=0.14,zoom=0.75" '
                            "gt3r game.iso --screen cars --shot shot.png")
        root, model = self.app.mod_root(), self.app.car_value("model", "file")
        if not model:
            self.status_var.set("The car tab's Model file is empty, so the body can't be placed. Fill it in first.")
        elif root is None:
            self.status_var.set("The mod isn't saved yet. You'll be asked to save it when a file needs a place to go.")
        else:
            self.status_var.set(f"Files go into {root}")

    def _target(self, section: str, key: str, what: str) -> Path | None:
        rel = self.app.car_value(section, key)
        if not rel:
            messagebox.showinfo("Missing path", f"The car tab has no {what} set. Fill it in there first.")
            return None
        root = self.app.ensure_mod_folder()
        return root / rel if root else None

    def log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _say(self, text: str):
        self._queue.put(("line", text))

    def _async(self, work: Callable[[], object], done: Callable[[object], None] | None = None):
        for b in self.buttons:
            b.state(["disabled"])
        self._done = done

        def target():
            try:
                self._queue.put(("ok", work()))
            except ModelToolError as exc:
                self._queue.put(("err", str(exc)))
            except Exception as exc:  # unexpected: still show it
                self._queue.put(("err", f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=target, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "line":
                    self.log(payload)
                    continue
                for b in self.buttons:
                    b.state(["!disabled"])
                if kind == "err":
                    self.log("Problem: " + payload)
                    messagebox.showerror("Model tools", payload)
                elif self._done:
                    self._done(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def use_finished(self):
        src = filedialog.askopenfilename(title="Choose the finished .glb", filetypes=GLB)
        if not src:
            return
        dst = self._target("model", "file", "Model file")
        if dst is None:
            return
        src = Path(src)
        copy = src.resolve() != dst.resolve()
        if copy and dst.exists() and not messagebox.askyesno("Replace body?", f"{dst.name} already exists in the mod.\nReplace it?"):
            return

        def work():
            if copy:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                self._say(f"Copied {src.name} to {dst}")
            return modeltools.measure_glb(dst)

        self._async(work, self._measured)

    def convert(self):
        blender = self.blender_var.get().strip()
        if not blender or not Path(blender).is_file():
            messagebox.showinfo("Blender needed",
                                "This option runs Blender in the background. Use \"Find…\" to point to blender.exe "
                                "(a free download from blender.org).")
            return
        src = filedialog.askopenfilename(title="Choose the source model (CarConcept-style .glb)", filetypes=GLB)
        if not src:
            return
        dst = self._target("model", "file", "Model file")
        if dst is None:
            return
        if dst.exists() and not messagebox.askyesno("Replace body?", f"{dst.name} already exists in the mod.\nReplace it?"):
            return
        src, stage = Path(src), Path(tempfile.gettempdir()) / "gt3_mod_creator_stage1.glb"
        settings.update(blender=blender)

        def work():
            self._say("Step 1 of 3: cleaning up the model in Blender (this can take a minute)…")
            dims = modeltools.run_prepare(blender, self.prepare_script, src, stage,
                                          on_line=lambda l: l.startswith(("wheelbase", "TRIS", "UNMAPPED")) and self._say(l))
            self._say("Step 2 of 3: setting the game's materials…")
            self._say(modeltools.finish_glb(stage, dst))
            self._say("Step 3 of 3: measuring…")
            return dims, modeltools.measure_glb(dst)

        def done(res):
            dims, measured = res
            self.dims.update(dims)
            self._measured(measured)

        self._async(work, done)

    def measure_current(self):
        root, model = self.app.mod_root(), self.app.car_value("model", "file")
        path = root / model if root and model else None
        if path is None or not path.is_file():
            messagebox.showinfo("No body yet", "There is no body in the mod folder yet. Add one in step 1 first.")
            return
        self._async(lambda: modeltools.measure_glb(path), self._measured)

    def _measured(self, m: dict):
        self.dims.update({k: m[k] for k in ("length_mm", "width_mm", "height_mm")})
        self.log(f"Done. Body is {m['length_mm']} x {m['width_mm']} x {m['height_mm']} mm (length x width x height).")
        self.dims_var.set("Measured: " + ", ".join(f"{BODY_LABELS[k]} {v} mm" for k, v in self.dims.items() if k in BODY_LABELS))
        if messagebox.askyesno("Fill in the car tab?", self.dims_var.get() + "\n\nPut these in the car tab's body section?"):
            self.apply_dims()

    def apply_dims(self):
        if not self.dims:
            messagebox.showinfo("Nothing measured", "Add or measure a body first (steps 1 and 2).")
            return
        n = self.app.set_car_values({("body", k): str(v) for k, v in self.dims.items()})
        self.log(f"Filled in {n} value(s) in the car tab's body section.")

    def make_pictures(self):
        shot = filedialog.askopenfilename(title="Choose the car viewer screenshot", filetypes=IMAGES)
        if not shot:
            return
        pic = self._target("dealer", "picture", "Picture")
        thumb = self._target("dealer", "thumb", "Thumbnail") if pic else None
        if pic is None or thumb is None:
            return
        self._async(lambda: modeltools.make_pictures(shot, pic, thumb),
                    lambda s: self.log(f"Made the dealer picture and thumbnail ({s})."))

    def copy_viewer(self):
        self.clipboard_clear()
        self.clipboard_append(self.viewer_var.get())
        self.log("Viewer command copied. Run it next to the game, then choose the screenshot.")
