from __future__ import annotations
import math
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable
import numpy as np
from PIL import Image, ImageTk
from core import modeltools
from core.modeltools import ModelToolError
from gui.gl_renderer import GLRenderer, overlay_lines
from gui.parameter_form import parse_tyre_size, tyre_dimensions

GL_MAX_TRIANGLES = 400_000      # OpenGL path: effectively 'show everything'
SOFT_MAX_TRIANGLES = 6000       # software path: keep it usable

HINT_FG = "#777777"
BG = (26, 30, 36)
BODY_RGB = (150, 165, 180)
BODY_EDGE = (40, 44, 50)
WHEEL_RGB = (232, 184, 74)
GRID_RGB = (42, 48, 56)


class ModelViewPanel(ttk.Frame):

    def __init__(
        self,
        master,
        get_model_path: Callable[[], Path | None],
        get_layout: Callable[[], dict],
    ):
        super().__init__(master, padding=6)
        self.get_model_path = get_model_path
        self.get_layout = get_layout
        self._verts: np.ndarray | None = None  # (N,3) xyz
        self._uvs: np.ndarray | None = None    # (N,2) uv
        self._faces: np.ndarray | None = None  # (M,3) int
        self._face_tex: np.ndarray | None = None  # (M,) texture index
        self._face_color: np.ndarray | None = None  # (M,3) base colour 0-1
        self._textures: list = []  # RGB arrays or None
        self._path: Path | None = None
        self._photo: ImageTk.PhotoImage | None = None

        # Camera
        self._yaw = -0.9
        self._pitch = 0.32
        self._dist = 6.0
        self._target = np.zeros(3)
        self._drag: tuple[int, int] | None = None
        self._orbiting = False
        self._render_after: str | None = None
        self._pending_fast = False
        self._canvas_img: int | None = None
        self._last_status = ""
        self._mesh_dirty = True
        self._gl: GLRenderer | None = None
        self._gl_error = ""

        self._build()
        self._init_gl()
        self.bind("<Map>", lambda _e: self.refresh())
        self.bind("<Destroy>", self._on_destroy)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(bar, text="Refresh view", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Top", command=lambda: self._preset(0.0, math.pi / 2 - 0.02)).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Side", command=lambda: self._preset(0.0, 0.05)).pack(side="left", padx=4)
        ttk.Button(bar, text="Rear", command=lambda: self._preset(math.pi / 2, 0.08)).pack(side="left", padx=4)
        ttk.Button(bar, text="3/4", command=lambda: self._preset(-0.9, 0.32)).pack(side="left", padx=4)
        self.status = ttk.Label(bar, text="", foreground=HINT_FG)
        self.status.pack(side="left", padx=(12, 0))

        self.canvas = tk.Canvas(self, background="#1a1e24", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _e: self._schedule_render())
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)          # Windows
        self.canvas.bind("<Button-4>", lambda e: self._on_wheel_linux(-1))
        self.canvas.bind("<Button-5>", lambda e: self._on_wheel_linux(1))

        self.info = ttk.Label(self, text="", foreground=HINT_FG, wraplength=720, justify="left")
        self.info.grid(row=2, column=0, sticky="w", pady=(6, 0))

    def _preset(self, yaw: float, pitch: float):
        self._yaw, self._pitch = yaw, pitch
        self._fit_distance()
        self._render()

    def refresh(self):
        path = self.get_model_path()
        old_path = self._path
        notes: list[str] = []
        if path is None or not path.is_file():
            self._verts = self._uvs = self._faces = None
            self._face_tex = self._face_color = None
            self._textures = []
            self._path = None
            notes.append("No model file found. Set [model] file on the Car tab (or use Model tools).")
        elif path != self._path:
            try:
                verts, uvs, faces, face_tex, face_color, textures = modeltools.load_glb_mesh(
                    path, max_triangles=GL_MAX_TRIANGLES if self._gl else SOFT_MAX_TRIANGLES,
                )
                self._verts = np.asarray(verts, dtype=np.float32)
                self._uvs = np.asarray(uvs, dtype=np.float32)
                self._faces = np.asarray(faces, dtype=np.int32)
                self._face_tex = np.asarray(face_tex, dtype=np.int32)
                self._face_color = np.asarray(face_color, dtype=np.float32)
                self._textures = textures
                self._path = path
                ntex = sum(1 for t in textures if t is not None)
                if ntex:
                    notes.append(f"Loaded {ntex} texture(s).")
                self._fit_camera()
            except ModelToolError as e:
                self._verts = self._uvs = self._faces = None
                self._face_tex = self._face_color = None
                self._textures = []
                self._path = None
                notes.append(str(e))
            except Exception as e:
                self._verts = self._uvs = self._faces = None
                self._face_tex = self._face_color = None
                self._textures = []
                self._path = None
                notes.append(f"Could not read model: {e}")

        if self._path != old_path:
            self._mesh_dirty = True

        layout = self.get_layout() or {}
        self._last_layout = layout
        self._last_notes = notes
        self._render()

    def _fit_camera(self):
        if self._verts is None or len(self._verts) == 0:
            self._target = np.zeros(3)
            self._dist = 6.0
            return
        mins = self._verts.min(axis=0)
        maxs = self._verts.max(axis=0)
        self._target = ((mins + maxs) * 0.5).astype(np.float32)
        extent = float(np.max(maxs - mins)) or 2.0
        self._dist = max(extent * 1.8, 0.5)
        self._yaw = -0.9
        self._pitch = 0.32

    def _fit_distance(self):
        if self._verts is None or len(self._verts) == 0:
            return
        extent = float(np.linalg.norm(self._verts.max(axis=0) - self._verts.min(axis=0))) or 2.0
        self._dist = max(self._dist, extent * 0.8)

    def _on_press(self, event):
        self._drag = (event.x, event.y)
        self._orbiting = True

    def _on_drag(self, event):
        if self._drag is None:
            return
        dx = event.x - self._drag[0]
        dy = event.y - self._drag[1]
        self._drag = (event.x, event.y)
        self._yaw -= dx * 0.008
        self._pitch += dy * 0.008
        self._pitch = max(-1.2, min(1.2, self._pitch))
        self._schedule_render(fast=True)

    def _on_release(self, _event=None):
        self._drag = None
        self._orbiting = False
        self._render_now(fast=False)

    def _on_wheel(self, event):
        delta = -1 if event.delta > 0 else 1
        self._dist *= 1.1 ** delta
        self._dist = max(0.3, min(80.0, self._dist))
        self._schedule_render()

    def _on_wheel_linux(self, direction: int):
        self._dist *= 1.1 ** direction
        self._dist = max(0.3, min(80.0, self._dist))
        self._schedule_render()

    def _camera_matrix(self) -> tuple[np.ndarray, np.ndarray]:
        cy, sy = math.cos(self._yaw), math.sin(self._yaw)
        cp, sp = math.cos(self._pitch), math.sin(self._pitch)
        offset = np.array([sy * cp, sp, cy * cp], dtype=np.float32)
        n_off = float(np.linalg.norm(offset)) or 1.0
        offset = offset / n_off
        eye = self._target + offset * self._dist
        z_axis = (self._target - eye).astype(np.float32)
        z_axis /= float(np.linalg.norm(z_axis)) + 1e-8
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        x_axis = np.cross(z_axis, up)
        n = float(np.linalg.norm(x_axis))
        if n < 1e-6:
            up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            x_axis = np.cross(z_axis, up)
            n = float(np.linalg.norm(x_axis))
        x_axis /= n + 1e-8
        y_axis = np.cross(x_axis, z_axis)
        rot = np.stack([x_axis, y_axis, z_axis], axis=0)  # world → cam
        return eye, rot

    def _init_gl(self):
        try:
            self._gl = GLRenderer()
            self._gl_error = ""
        except Exception as exc:          # no moderngl, no driver, VM, ...
            self._gl = None
            self._gl_error = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__

    def _release_gl(self):
        if self._gl is not None:
            try:
                self._gl.release()
            except Exception:
                pass
        self._gl = None

    def _on_destroy(self, event):
        if event.widget is self:
            self._release_gl()

    def _schedule_render(self, fast: bool = False):
        self._pending_fast = fast
        if self._render_after is None:
            self._render_after = self.after(8, self._flush_render)

    def _flush_render(self):
        self._render_after = None
        self._render(fast=self._pending_fast)

    def _render_now(self, fast: bool = False):
        if self._render_after is not None:
            self.after_cancel(self._render_after)
            self._render_after = None
        self._render(fast=fast)

    def _show_image(self, img: Image.Image, w: int, h: int):
        if self._photo is None or self._photo.width() != w or self._photo.height() != h:
            self._photo = ImageTk.PhotoImage(img)
            if self._canvas_img is None:
                self._canvas_img = self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
            else:
                self.canvas.itemconfigure(self._canvas_img, image=self._photo)
        else:
            self._photo.paste(img)        # reuse the Tk image: no per-frame allocation

    def _render(self, fast: bool = False):
        w = max(self.canvas.winfo_width(), 2)
        h = max(self.canvas.winfo_height(), 2)
        if w < 10 or h < 10:
            return

        layout = getattr(self, "_last_layout", {}) or {}
        notes = list(getattr(self, "_last_notes", []) or [])
        wheels = self._wheel_centres(layout)

        img = None
        if self._gl is not None:
            try:
                img = self._render_gl(w, h, wheels)
            except Exception as exc:
                self._gl_error = f"OpenGL failed while drawing: {exc}"
                self._release_gl()
        if img is None:
            img = self._render_software(w, h, fast, wheels)
            if self._gl_error:
                notes.append(f"Using the software renderer ({self._gl_error}).")
        self._show_image(img, w, h)

        path_txt = self._path.name if self._path else "(no model)"
        nverts = 0 if self._verts is None else len(self._verts)
        nfaces = 0 if self._faces is None else len(self._faces)
        backend = f"OpenGL · {self._gl.name}" if self._gl is not None else "software"
        status = (f"{path_txt}  ·  {nverts:,} verts · {nfaces:,} tris · {len(wheels)} wheels  ·  "
                  f"{backend}  ·  drag to orbit, scroll to zoom")
        if status != self._last_status:
            self._last_status = status
            self.status.configure(text=status)
        lines = []
        if wheels:
            lines.append(
                f"Wheelbase {layout.get('wheelbase_mm') or '?'} mm · "
                f"front track {layout.get('front_track_mm') or '?'} mm · "
                f"rear track {layout.get('rear_track_mm') or '?'} mm"
            )
        lines.extend(notes)
        self.info.configure(text="\n".join(lines) if lines else "")

    def _render_gl(self, w: int, h: int, wheels: list[dict]) -> Image.Image:
        gl = self._gl
        if self._mesh_dirty:
            if self._verts is None:
                gl.set_mesh(None)
            else:
                gl.set_mesh(self._verts, self._uvs, self._faces, self._face_tex, self._face_color, self._textures)
            self._mesh_dirty = False
        if self._verts is not None and len(self._verts):
            mins, maxs = self._verts.min(axis=0), self._verts.max(axis=0)
        else:
            mins = maxs = None
        eye, rot = self._camera_matrix()
        lines = overlay_lines(wheels, mins, maxs, self._target)
        return gl.render(w, h, eye, rot, 50.0, lines, near=0.05, far=max(200.0, self._dist * 10.0))

    def _render_software(self, w: int, h: int, fast: bool, wheels: list[dict]) -> Image.Image:
        scale = 0.5 if not fast else 0.4
        rw, rh = max(2, int(w * scale)), max(2, int(h * scale))

        img = Image.new("RGB", (rw, rh), BG)
        zbuf = np.full((rh, rw), np.inf, dtype=np.float32)
        pixels = np.array(img, dtype=np.uint8)

        eye, rot = self._camera_matrix()
        fov = 50.0 * math.pi / 180.0
        f = 0.5 * rh / math.tan(fov * 0.5)

        def project(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            local = (pts - eye) @ rot.T
            depth = local[:, 2]
            z = np.maximum(depth, 1e-4)
            sx = (local[:, 0] * f / z) + rw * 0.5
            sy = (-local[:, 1] * f / z) + rh * 0.5
            return sx, sy, depth

        if self._verts is not None and len(self._verts):
            span = float(np.linalg.norm(self._verts.max(axis=0) - self._verts.min(axis=0))) * 0.7
            cx, cz = float(self._target[0]), float(self._target[2])
        else:
            span, cx, cz = 2.5, 0.0, 0.0
        grid_pts = []
        ngrid = 7
        for i in range(ngrid):
            g = cx - span + 2 * span * i / (ngrid - 1)
            grid_pts.append([[g, 0, cz - span], [g, 0, cz + span]])
            grid_pts.append([[cx - span, 0, g], [cx + span, 0, g]])
        for a, b in grid_pts:
            self._draw_line(pixels, zbuf, project, np.array(a), np.array(b), GRID_RGB, rw, rh)

        if self._verts is not None and self._faces is not None and len(self._faces):
            if fast or self._orbiting:
                self._draw_wireframe(pixels, zbuf, project, self._verts, self._faces, rw, rh)
            else:
                self._draw_mesh(pixels, zbuf, project, rw, rh)

        for wheel in wheels:
            self._draw_wheel_disc(pixels, zbuf, project, wheel, rw, rh)

        img = Image.fromarray(pixels, "RGB")
        if (rw, rh) != (w, h):
            img = img.resize((w, h), Image.BILINEAR)
        return img


    def _draw_wireframe(self, pixels, zbuf, project, verts, faces, w, h):
        step = max(1, len(faces) // 2500)
        faces = faces[::step]
        sx, sy, depth = project(verts)
        col = BODY_RGB
        for i0, i1, i2 in faces:
            for a, b in ((i0, i1), (i1, i2), (i2, i0)):
                if depth[a] <= 0 and depth[b] <= 0:
                    continue
                x0, y0, z0 = sx[a], sy[a], depth[a]
                x1, y1, z1 = sx[b], sy[b], depth[b]
                steps = int(max(abs(x1 - x0), abs(y1 - y0), 1))
                for s in range(0, steps + 1, max(1, steps // 12)):
                    t = s / steps
                    x = int(x0 + (x1 - x0) * t)
                    y = int(y0 + (y1 - y0) * t)
                    z = z0 + (z1 - z0) * t
                    if z <= 0 or x < 0 or y < 0 or x >= w or y >= h:
                        continue
                    if z < zbuf[y, x]:
                        zbuf[y, x] = z
                        pixels[y, x] = col

    def _draw_mesh(self, pixels, zbuf, project, w, h):
        verts = self._verts
        faces = self._faces
        uvs = self._uvs if self._uvs is not None else np.zeros((len(verts), 2), dtype=np.float32)
        face_tex = self._face_tex if self._face_tex is not None else np.full(len(faces), -1, dtype=np.int32)
        face_color = self._face_color if self._face_color is not None else np.full((len(faces), 3), 0.7, dtype=np.float32)
        textures = self._textures or []

        light = np.array([0.4, 0.85, 0.35], dtype=np.float32)
        light /= np.linalg.norm(light)

        v0 = verts[faces[:, 0]]
        v1 = verts[faces[:, 1]]
        v2 = verts[faces[:, 2]]
        normals = np.cross(v1 - v0, v2 - v0)
        nn = np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-8)
        normals = normals / nn
        centres = (v0 + v1 + v2) / 3.0
        eye, _rot = self._camera_matrix()
        view = eye - centres
        view /= np.maximum(np.linalg.norm(view, axis=1, keepdims=True), 1e-8)
        facing = np.sum(normals * view, axis=1) > 0.0
        faces = faces[facing]
        normals = normals[facing]
        face_tex = face_tex[facing]
        face_color = face_color[facing]
        if len(faces) == 0:
            return

        shade = 0.30 + 0.70 * np.clip(normals @ light, 0.0, 1.0)
        sx, sy, depth = project(verts)

        if len(faces) > 4000:
            step = max(1, len(faces) // 4000)
            faces = faces[::step]
            shade = shade[::step]
            face_tex = face_tex[::step]
            face_color = face_color[::step]

        for i, (i0, i1, i2) in enumerate(faces):
            pts = np.array([
                [sx[i0], sy[i0], depth[i0]],
                [sx[i1], sy[i1], depth[i1]],
                [sx[i2], sy[i2], depth[i2]],
            ], dtype=np.float32)
            if pts[0, 2] <= 0 and pts[1, 2] <= 0 and pts[2, 2] <= 0:
                continue
            uv = np.array([uvs[i0], uvs[i1], uvs[i2]], dtype=np.float32)
            ti = int(face_tex[i])
            tex = textures[ti] if 0 <= ti < len(textures) else None
            base = face_color[i]
            self._fill_tri_tex(pixels, zbuf, pts, uv, tex, base, float(shade[i]), w, h)

    def _fill_tri_tex(self, pixels, zbuf, pts, uv, tex, base, shade, w, h):
        xs, ys = pts[:, 0], pts[:, 1]
        minx = max(int(math.floor(xs.min())), 0)
        maxx = min(int(math.ceil(xs.max())), w - 1)
        miny = max(int(math.floor(ys.min())), 0)
        maxy = min(int(math.ceil(ys.max())), h - 1)
        if minx > maxx or miny > maxy:
            return
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts
        (u0, v0), (u1, v1), (u2, v2) = uv
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-8:
            return
        inv = 1.0 / denom
        th = tw = 0
        if tex is not None:
            th, tw = tex.shape[0], tex.shape[1]
        br, bg, bb = float(base[0]), float(base[1]), float(base[2])
        for py in range(miny, maxy + 1):
            for px in range(minx, maxx + 1):
                w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) * inv
                w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) * inv
                w2 = 1.0 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                z = w0 * z0 + w1 * z1 + w2 * z2
                if z <= 0 or z >= zbuf[py, px]:
                    continue
                zbuf[py, px] = z
                if tex is not None and tw > 0 and th > 0:
                    uu = w0 * u0 + w1 * u1 + w2 * u2
                    vv = w0 * v0 + w1 * v1 + w2 * v2
                    uu = uu % 1.0
                    vv = vv % 1.0
                    if uu < 0:
                        uu += 1.0
                    if vv < 0:
                        vv += 1.0
                    tx = min(tw - 1, int(uu * tw))
                    ty = min(th - 1, int(vv * th))
                    tr, tg, tb = tex[ty, tx]
                    r = int(min(255, tr * br * shade))
                    g = int(min(255, tg * bg * shade))
                    b = int(min(255, tb * bb * shade))
                else:
                    r = int(min(255, br * 255 * shade))
                    g = int(min(255, bg * 255 * shade))
                    b = int(min(255, bb * 255 * shade))
                pixels[py, px, 0] = r
                pixels[py, px, 1] = g
                pixels[py, px, 2] = b

    def _draw_line(self, pixels, zbuf, project, a, b, color, w, h):
        pts = np.stack([a, b])
        sx, sy, depth = project(pts)
        if depth[0] <= 0 and depth[1] <= 0:
            return
        x0, y0, z0 = sx[0], sy[0], depth[0]
        x1, y1, z1 = sx[1], sy[1], depth[1]
        steps = int(max(abs(x1 - x0), abs(y1 - y0), 1))
        for i in range(steps + 1):
            t = i / steps
            x = int(x0 + (x1 - x0) * t)
            y = int(y0 + (y1 - y0) * t)
            z = z0 + (z1 - z0) * t
            if z <= 0 or x < 0 or y < 0 or x >= w or y >= h:
                continue
            if z < zbuf[y, x]:
                zbuf[y, x] = z
                pixels[y, x] = color

    def _draw_wheel_disc(self, pixels, zbuf, project, wheel, w, h):
        r = wheel["radius"]
        x0, z0 = wheel["x"], wheel["z"]
        y0 = r
        n = 24
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            pts.append([x0, y0 + r * math.cos(a), z0 + r * math.sin(a)])
        pts = np.asarray(pts, dtype=np.float32)
        for i in range(n):
            self._draw_line(pixels, zbuf, project, pts[i], pts[(i + 1) % n], WHEEL_RGB, w, h)
        hr = r * 0.3
        hub = []
        for i in range(n):
            a = 2 * math.pi * i / n
            hub.append([x0, y0 + hr * math.cos(a), z0 + hr * math.sin(a)])
        hub = np.asarray(hub, dtype=np.float32)
        for i in range(n):
            self._draw_line(pixels, zbuf, project, hub[i], hub[(i + 1) % n], (60, 60, 60), w, h)

    def _wheel_centres(self, layout: dict) -> list[dict]:
        try:
            wb = float(layout.get("wheelbase_mm") or 0) / 1000.0
            ft = float(layout.get("front_track_mm") or 0) / 1000.0
            rt = float(layout.get("rear_track_mm") or 0) / 1000.0
        except (TypeError, ValueError):
            return []
        if wb <= 0:
            return []
        if ft <= 0:
            ft = 1.5
        if rt <= 0:
            rt = ft
        front_tyre = str(layout.get("front") or "")
        rear_tyre = str(layout.get("rear") or "")
        fr = self._tyre_radius_m(front_tyre) or 0.32
        rr = self._tyre_radius_m(rear_tyre) or fr
        half = wb / 2.0
        return [
            {"label": "FL", "x": -ft / 2, "z": half, "radius": fr},
            {"label": "FR", "x": +ft / 2, "z": half, "radius": fr},
            {"label": "RL", "x": -rt / 2, "z": -half, "radius": rr},
            {"label": "RR", "x": +rt / 2, "z": -half, "radius": rr},
        ]

    @staticmethod
    def _tyre_radius_m(size: str) -> float | None:
        parsed = parse_tyre_size(size)
        if not parsed:
            return None
        diam_mm, _ = tyre_dimensions(*parsed)
        return (diam_mm / 1000.0) / 2.0