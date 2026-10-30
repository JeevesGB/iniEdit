from __future__ import annotations
import math
import numpy as np
from PIL import Image

BG = (26, 30, 36)
GRID_RGB = (42, 48, 56)
WHEEL_RGB = (232, 184, 74)
HUB_RGB = (60, 60, 60)

_LIGHT = np.array([0.4, 0.85, 0.35], dtype=np.float32)
_LIGHT /= np.linalg.norm(_LIGHT)

MESH_VS = """
#version 330
uniform mat4 mvp;
uniform vec3 light;
in vec3 in_pos;
in vec3 in_nrm;
in vec2 in_uv;
in vec3 in_col;
out vec2 v_uv;
out vec3 v_col;
void main() {
    float shade = 0.30 + 0.70 * clamp(dot(normalize(in_nrm), light), 0.0, 1.0);
    v_col = in_col * shade;
    v_uv = in_uv;
    gl_Position = mvp * vec4(in_pos, 1.0);
}
"""

MESH_FS = """
#version 330
uniform sampler2D tex;
in vec2 v_uv;
in vec3 v_col;
out vec4 frag;
void main() {
    frag = vec4(min(texture(tex, v_uv).rgb * v_col, vec3(1.0)), 1.0);
}
"""

LINE_VS = """
#version 330
uniform mat4 mvp;
in vec3 in_pos;
in vec3 in_col;
out vec3 v_col;
void main() {
    v_col = in_col;
    gl_Position = mvp * vec4(in_pos, 1.0);
}
"""

LINE_FS = """
#version 330
in vec3 v_col;
out vec4 frag;
void main() { frag = vec4(v_col, 1.0); }
"""


def perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2.0 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def view_matrix(eye: np.ndarray, rot: np.ndarray) -> np.ndarray:
    m = np.eye(4, dtype=np.float32)
    m[0, :3] = rot[0]
    m[1, :3] = rot[1]
    m[2, :3] = -rot[2]          # GL looks down -Z
    m[:3, 3] = -(m[:3, :3] @ np.asarray(eye, dtype=np.float32))
    return m


def build_batches(verts, uvs, faces, face_tex, face_color):
    verts = np.asarray(verts, dtype=np.float32)
    faces = np.asarray(faces, dtype=np.int64)
    uvs = np.asarray(uvs, dtype=np.float32)
    if uvs.shape[0] != verts.shape[0]:
        uvs = np.zeros((verts.shape[0], 2), dtype=np.float32)
    face_tex = np.asarray(face_tex, dtype=np.int64)
    face_color = np.asarray(face_color, dtype=np.float32)

    order = np.argsort(face_tex, kind="stable")
    faces, face_tex, face_color = faces[order], face_tex[order], face_color[order]

    tri = verts[faces]                                    # (M,3,3)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-8)

    data = np.hstack([
        tri.reshape(-1, 3),
        np.repeat(normals, 3, axis=0),
        uvs[faces].reshape(-1, 2),
        np.repeat(face_color, 3, axis=0),
    ]).astype(np.float32)

    uniq, start = np.unique(face_tex, return_index=True)
    counts = np.diff(np.append(start, len(face_tex)))
    groups = [(int(t), int(s) * 3, int(c) * 3) for t, s, c in zip(uniq, start, counts)]
    return np.ascontiguousarray(data), groups


def overlay_lines(wheels, mins, maxs, target) -> np.ndarray:
    if mins is not None:
        span = float(np.linalg.norm(np.asarray(maxs) - np.asarray(mins))) * 0.7
        cx, cz = float(target[0]), float(target[2])
    else:
        span, cx, cz = 2.5, 0.0, 0.0

    rows: list[list[float]] = []

    def seg(a, b, rgb):
        c = [rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0]
        rows.append([*a, *c])
        rows.append([*b, *c])

    n_grid = 7
    for i in range(n_grid):
        g = -span + 2 * span * i / (n_grid - 1)
        seg([cx + g, 0, cz - span], [cx + g, 0, cz + span], GRID_RGB)
        seg([cx - span, 0, cz + g], [cx + span, 0, cz + g], GRID_RGB)

    n = 24
    for wheel in wheels:
        r, x0, z0 = wheel["radius"], wheel["x"], wheel["z"]
        for radius, rgb in ((r, WHEEL_RGB), (r * 0.3, HUB_RGB)):
            pts = [[x0, r + radius * math.cos(2 * math.pi * i / n), z0 + radius * math.sin(2 * math.pi * i / n)]
                   for i in range(n)]
            for i in range(n):
                seg(pts[i], pts[(i + 1) % n], rgb)

    return np.asarray(rows, dtype=np.float32)

class GLRenderer:
    def __init__(self):
        import moderngl                      # ImportError here => panel falls back

        self._mgl = moderngl
        self.ctx = moderngl.create_standalone_context(require=330)
        self.name = str(self.ctx.info.get("GL_RENDERER", "OpenGL"))
        self._max_tex = int(self.ctx.info.get("GL_MAX_TEXTURE_SIZE", 4096))

        self._mesh_prog = self.ctx.program(vertex_shader=MESH_VS, fragment_shader=MESH_FS)
        self._line_prog = self.ctx.program(vertex_shader=LINE_VS, fragment_shader=LINE_FS)
        self._mesh_prog["tex"].value = 0
        self._mesh_prog["light"].value = tuple(float(v) for v in _LIGHT)
        self._white = self.ctx.texture((1, 1), 3, b"\xff\xff\xff")

        self._vbo = None
        self._vao = None
        self._groups: list[tuple[object, int, int]] = []   # (texture, first, count)
        self._textures: list = []
        self._fbo = None
        self._msaa = None
        self._size: tuple[int, int] | None = None

    def _free_mesh(self):
        for obj in (self._vao, self._vbo, *self._textures):
            try:
                obj.release()
            except Exception:
                pass
        self._vao = self._vbo = None
        self._textures = []
        self._groups = []

    def _upload_texture(self, arr):
        if arr is None:
            return None
        img = np.ascontiguousarray(arr[..., :3], dtype=np.uint8)
        h, w = img.shape[:2]
        if max(w, h) > self._max_tex:
            k = self._max_tex / max(w, h)
            img = np.asarray(Image.fromarray(img).resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS))
            h, w = img.shape[:2]
        tex = self.ctx.texture((w, h), 3, img.tobytes())
        tex.repeat_x = tex.repeat_y = True
        tex.build_mipmaps()
        tex.filter = (self._mgl.LINEAR_MIPMAP_LINEAR, self._mgl.LINEAR)
        try:
            tex.anisotropy = 8.0
        except Exception:
            pass
        self._textures.append(tex)
        return tex

    def set_mesh(self, verts=None, uvs=None, faces=None, face_tex=None, face_color=None, textures=None):
        self._free_mesh()
        if verts is None or faces is None or len(faces) == 0:
            return
        data, groups = build_batches(verts, uvs, faces, face_tex, face_color)
        self._vbo = self.ctx.buffer(data.tobytes())
        self._vao = self.ctx.vertex_array(
            self._mesh_prog,
            [(self._vbo, "3f 3f 2f 3f", "in_pos", "in_nrm", "in_uv", "in_col")],
        )
        textures = textures or []
        cache: dict[int, object] = {}
        for ti, first, count in groups:
            if 0 <= ti < len(textures) and textures[ti] is not None:
                if ti not in cache:
                    cache[ti] = self._upload_texture(textures[ti])
                tex = cache[ti]
            else:
                tex = None
            self._groups.append((tex or self._white, first, count))

    def _ensure_fbo(self, w: int, h: int):
        if self._size == (w, h):
            return
        for fb in (self._fbo, self._msaa):
            try:
                if fb is not None:
                    fb.release()
            except Exception:
                pass
        self._fbo = self.ctx.simple_framebuffer((w, h))
        try:
            self._msaa = self.ctx.simple_framebuffer((w, h), samples=4)
        except Exception:
            self._msaa = None
        self._size = (w, h)

    def render(self, w, h, eye, rot, fov_deg, lines, near=0.05, far=200.0) -> Image.Image:
        w, h = max(2, int(w)), max(2, int(h))
        self._ensure_fbo(w, h)
        ctx = self.ctx
        target = self._msaa or self._fbo
        target.use()
        ctx.clear(BG[0] / 255.0, BG[1] / 255.0, BG[2] / 255.0, 1.0, depth=1.0)
        ctx.enable(self._mgl.DEPTH_TEST | self._mgl.CULL_FACE)

        mvp = (perspective(fov_deg, w / h, near, far) @ view_matrix(eye, rot)).astype("f4").T.tobytes()

        if self._vao is not None:
            self._mesh_prog["mvp"].write(mvp)
            for tex, first, count in self._groups:
                tex.use(0)
                self._vao.render(self._mgl.TRIANGLES, vertices=count, first=first)

        if lines is not None and len(lines):
            vbo = ctx.buffer(np.ascontiguousarray(lines, dtype=np.float32).tobytes())
            vao = ctx.vertex_array(self._line_prog, [(vbo, "3f 3f", "in_pos", "in_col")])
            try:
                self._line_prog["mvp"].write(mvp)
                vao.render(self._mgl.LINES)
            finally:
                vao.release()
                vbo.release()

        if self._msaa is not None:
            ctx.copy_framebuffer(self._fbo, self._msaa)
        raw = self._fbo.read(components=3)
        return Image.frombuffer("RGB", (w, h), raw, "raw", "RGB", 0, -1)   # -1 = flip vertically

    def release(self):
        self._free_mesh()
        for obj in (self._fbo, self._msaa, self._white, self._mesh_prog, self._line_prog, self.ctx):
            try:
                obj.release()
            except Exception:
                pass
        self._fbo = self._msaa = None