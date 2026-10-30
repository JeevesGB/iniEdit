from __future__ import annotations
import json
import os
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Callable

JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942

class ModelToolError(Exception):
    pass

def _read_glb(path: str | Path) -> tuple[dict, bytes]:
    d = Path(path).read_bytes()
    if d[:4] != b"glTF":
        raise ModelToolError(f"{Path(path).name} is not a binary glTF (.glb) file.")
    o, doc, binc = 12, None, b""
    while o + 8 <= len(d):
        ln, ty = struct.unpack_from("<II", d, o)
        if ty == JSON_CHUNK:
            doc = json.loads(d[o + 8:o + 8 + ln])
        elif ty == BIN_CHUNK:
            binc = d[o + 8:o + 8 + ln]
        o += 8 + ((ln + 3) & ~3)
    if doc is None:
        raise ModelToolError("The .glb has no JSON chunk.")
    return doc, binc


def measure_glb(path: str | Path) -> dict[str, float]:
    doc, b = _read_glb(path)
    pts = []
    for mesh in doc["meshes"]:
        for p in mesh["primitives"]:
            a = doc["accessors"][p["attributes"]["POSITION"]]
            bv = doc["bufferViews"][a["bufferView"]]
            off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
            stride = bv.get("byteStride") or 12
            name = doc["materials"][p["material"]]["name"] if "material" in p else ""
            for i in range(a["count"]):
                pts.append((name,) + struct.unpack_from("<3f", b, off + stride * i))
    if not pts:
        raise ModelToolError("The model has no vertices.")
    xs, ys, zs = ([p[k] for p in pts] for k in (1, 2, 3))
    half = max((abs(p[1]) for p in pts if p[0] != "mirror_chrome" and not (0.75 < p[2] < 1.0 and abs(p[1]) > 1.0)),
               default=max(abs(x) for x in xs))
    return {
        "x_min": min(xs), "x_max": max(xs), "y_min": min(ys), "y_max": max(ys), "z_min": min(zs), "z_max": max(zs),
        "length_mm": round((max(zs) - min(zs)) * 1000), "width_mm": round(half * 2000),
        "height_mm": round(max(ys) * 1000), "clearance_mm": round(min(ys) * 1000),
    }


GLYPHS = {
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
}
PLATE_W, PLATE_H = 256, 64


def plate_png(text: str = "GT3R") -> bytes:
    W, H = PLATE_W, PLATE_H
    bg, ink, edge = (232, 232, 224), (24, 28, 44), (40, 40, 40)
    px = [[bg for _ in range(W)] for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if x < 3 or y < 3 or x >= W - 3 or y >= H - 3:
                px[y][x] = edge
    sx, sy = 7, 6
    gw, gap = 5 * sx, 2 * sx
    total = len(text) * gw + (len(text) - 1) * gap
    x0, y0 = (W - total) // 2, (H - 7 * sy) // 2
    for i, ch in enumerate(text):
        for r, row in enumerate(GLYPHS[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    for yy in range(y0 + r * sy, y0 + (r + 1) * sy):
                        for xx in range(x0 + i * (gw + gap) + c * sx, x0 + i * (gw + gap) + (c + 1) * sx):
                            px[yy][xx] = ink
    raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in px)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# name: (rgba, metallic, roughness, doubleSided). The game uses base colours as given.
MATS = {
    "body_paint":           ((0.62, 0.07, 0.09, 1), 0.0, 0.3, True),
    "trim_gloss_black":     ((0.07, 0.07, 0.08, 1), 1.0, 0.15, True),
    "window_glass":         ((0.10, 0.12, 0.14, 0.62), 0.0, 0.0, True),
    "headlamp":             ((0.92, 0.95, 1.00, 1), 0.0, 0.2, False),
    "taillamp":             ((0.60, 0.04, 0.04, 1), 0.0, 0.2, False),
    "indicator_amber":      ((0.80, 0.42, 0.06, 1), 0.0, 0.3, False),
    "mirror_chrome":        ((0.78, 0.80, 0.83, 1), 1.0, 0.05, False),
    "plate":                ((1, 1, 1, 1), 0.0, 0.8, False),
    "chassis_dark":         ((0.06, 0.06, 0.06, 1), 0.0, 0.8, True),
    "trim_satin_metal":     ((0.50, 0.51, 0.53, 1), 1.0, 0.4, False),
    "trim_black":           ((0.05, 0.05, 0.05, 1), 0.0, 0.7, True),
    "interior_dark":        ((0.09, 0.09, 0.10, 1), 0.0, 0.8, True),
    "dashboard":            ((0.06, 0.06, 0.07, 1), 0.0, 0.7, False),
    "interior_leather_red": ((0.42, 0.07, 0.06, 1), 0.0, 0.6, True),
}


def finish_glb(src: str | Path, dst: str | Path) -> str:
    doc, binc = _read_glb(src)
    png = plate_png()
    views = [binc[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]] for v in doc["bufferViews"]]

    bare = [p for m in doc["meshes"] for p in m["primitives"] if "material" not in p]
    if len(bare) > 1:
        raise ModelToolError("More than one primitive without a material: this is not a prepare.py output.")
    for p in bare:
        doc["materials"].append({"name": "body_paint"})
        p["material"] = len(doc["materials"]) - 1

    used = sorted({p["material"] for m in doc["meshes"] for p in m["primitives"]})
    remap = {old: new for new, old in enumerate(used)}
    doc["materials"] = [doc["materials"][i] for i in used]
    for m in doc["meshes"]:
        m.pop("extensions", None), m.pop("extras", None)
        for p in m["primitives"]:
            p["material"] = remap[p["material"]]
            p.pop("extensions", None), p.pop("extras", None)

    for m in doc["materials"]:
        name = m.get("name", "")
        if name not in MATS:
            raise ModelToolError(f"Unknown material '{name}': run the Prepare step first (or edit MATS in core/modeltools.py).")
        rgba, metal, rough, ds = MATS[name]
        tex = m.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        new = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": list(rgba), "metallicFactor": metal,
                                                       "roughnessFactor": rough}}
        if name == "plate":
            if tex is None:
                raise ModelToolError("The plate lost its texture coordinates.")
            new["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex["index"]}
        if rgba[3] < 1:
            new["alphaMode"] = "BLEND"
        if ds:
            new["doubleSided"] = True
        m.clear()
        m.update(new)

    if len(doc.get("images", [])) != 1:
        raise ModelToolError("Expected exactly one image (the plate): run the Prepare step first.")
    img = doc["images"][0]
    views[img["bufferView"]] = png
    doc["images"] = [{"name": "plate", "mimeType": "image/png", "bufferView": img["bufferView"]}]
    doc["textures"] = [{"source": 0, "sampler": 0}]
    doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}]
    for m in doc["materials"]:
        t = m["pbrMetallicRoughness"].get("baseColorTexture")
        if t:
            t["index"] = 0
    for k in ("extensionsUsed", "extensionsRequired", "extensions"):
        doc.pop(k, None)
    for n in doc["nodes"]:
        n.pop("extras", None)
    doc["asset"] = {"version": "2.0", "generator": "GT3 Mod Creator (finish)",
                    "copyright": "2024 Darmstadt Graphics Group GmbH (CC-BY 4.0); modified for GT3 Revisited"}

    out = bytearray()
    for i, v in enumerate(views):
        while len(out) % 4:
            out.append(0)
        doc["bufferViews"][i]["byteOffset"] = len(out)
        doc["bufferViews"][i]["byteLength"] = len(v)
        out += v
    while len(out) % 4:
        out.append(0)
    doc["buffers"] = [{"byteLength": len(out)}]
    js = json.dumps(doc, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    total = 12 + 8 + len(js) + 8 + len(out)
    glb = (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(js), JSON_CHUNK) + js +
           struct.pack("<II", len(out), BIN_CHUNK) + bytes(out))
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(glb)
    acc = doc["accessors"]
    tris = sum(acc[p["indices"]]["count"] // 3 for m in doc["meshes"] for p in m["primitives"])
    return f"wrote {dst.name}: {len(glb):,} bytes, {tris:,} triangles, {len(doc['materials'])} materials"


_DIMS = re.compile(r"wheelbase\s+(\S+)\s+front track\s+(\S+)\s+rear track\s+(\S+)")


def find_blender() -> str:
    from shutil import which
    found = which("blender")
    if found:
        return found
    if os.name == "nt":
        roots = [Path(os.environ.get(v, "")) / "Blender Foundation" for v in ("ProgramFiles", "ProgramFiles(x86)")]
        hits = [p for r in roots if r.is_dir() for p in r.glob("Blender */blender.exe")]
        if hits:
            return str(max(hits, key=lambda p: [int(n) if n.isdigit() else 0 for n in re.split(r"\D+", p.parent.name)]))
    elif sys.platform == "darwin" and Path("/Applications/Blender.app/Contents/MacOS/Blender").is_file():
        return "/Applications/Blender.app/Contents/MacOS/Blender"
    return ""


def run_prepare(blender: str | Path, script: str | Path, src: str | Path, dst: str | Path,
                on_line: Callable[[str], None] = lambda _l: None) -> dict[str, int]:
    if not Path(blender).is_file():
        raise ModelToolError("Blender not found: choose its executable.")
    if not Path(script).is_file():
        raise ModelToolError(f"Missing script {script}.")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    if Path(dst).exists():
        Path(dst).unlink()
    cmd = [str(blender), "-b", "--factory-startup", "--python", str(script), "--", str(src), str(dst)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    dims: dict[str, int] = {}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                            creationflags=flags)
    for line in proc.stdout:
        line = line.rstrip()
        on_line(line)
        m = _DIMS.search(line)
        if m:
            wb, ft, rt = (abs(float(g)) for g in m.groups())
            dims = {"wheelbase_mm": round(wb * 1000), "front_track_mm": round(ft * 1000), "rear_track_mm": round(rt * 1000)}
    if proc.wait() != 0 or not Path(dst).is_file():
        raise ModelToolError("Blender did not produce a model (see the log).")
    return dims


def make_pictures(shot: str | Path, pic: str | Path, thumb: str | Path) -> str:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ModelToolError("Pillow is required (python -m pip install pillow).") from exc
    im = Image.open(shot).convert("RGB")
    W, H = im.size
    bg = im.getpixel((5, H // 2))
    px = im.load()
    xs, ys = [], []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            p = px[x, y]
            if sum(abs(p[i] - bg[i]) for i in range(3)) > 24:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise ModelToolError("No car found in the screenshot (it is all one colour).")
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    def crop(aspect, margin, dx=0.0, dy=0.0):
        w = (x1 - x0) * margin
        h = w / aspect
        if h < (y1 - y0) * margin:
            h = (y1 - y0) * margin
            w = h * aspect
        ox, oy = cx - dx * w, cy - dy * h
        return im.crop((int(ox - w / 2), int(oy - h / 2), int(ox + w / 2), int(oy + h / 2)))

    for p in (pic, thumb):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    crop(640 / 448, 1.35, 0.07, -0.07).resize((640, 448), Image.LANCZOS).save(pic, optimize=True)
    crop(51 / 27, 1.04).resize((51, 27), Image.LANCZOS).save(thumb, optimize=True)
    return f"car found at {x0},{y0}-{x1},{y1}; wrote {Path(pic).name} and {Path(thumb).name}"



def _accessor_bytes(doc: dict, b: bytes, accessor_index: int):
    """Return (raw_slice, count, byte_stride, component_count, component_type)."""
    a = doc["accessors"][accessor_index]
    bv = doc["bufferViews"][a["bufferView"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    count = a["count"]
    ctype = a["componentType"]
    type_name = a["type"]
    comp_size = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}[ctype]
    comps = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[type_name]
    stride = bv.get("byteStride") or (comp_size * comps)
    length = stride * (count - 1) + comp_size * comps if count else 0
    return b[off:off + length], count, stride, comps, ctype


def _decode_glb_image(doc: dict, b: bytes, image_index: int):
    """Decode a glTF image to an RGB uint8 numpy array (H, W, 3), or None."""
    try:
        from PIL import Image
        import io
        import numpy as np
    except Exception:
        return None
    images = doc.get("images") or []
    if image_index < 0 or image_index >= len(images):
        return None
    img = images[image_index]
    data = None
    if "bufferView" in img:
        bv = doc["bufferViews"][img["bufferView"]]
        off = bv.get("byteOffset", 0)
        data = b[off:off + bv["byteLength"]]
    elif "uri" in img:
        uri = img["uri"]
        if uri.startswith("data:"):
            import base64
            _, encoded = uri.split(",", 1)
            data = base64.b64decode(encoded)
        else:
            # external file relative to glb — not resolved here
            return None
    if not data:
        return None
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        return np.asarray(im, dtype=np.uint8)
    except Exception:
        return None




def load_glb_mesh(
    path: str | Path,
    max_triangles: int = 20000,
) -> tuple:
    """Load a display mesh from a .glb via pygltflib (node transforms + textures).

    Returns
    -------
    vertices, uvs, faces, face_tex, face_color, textures
    """
    try:
        return _load_glb_mesh_pygltf(path, max_triangles)
    except Exception as primary:
        # Fall back to the lightweight parser if pygltflib is missing / fails
        try:
            return _load_glb_mesh_fallback(path, max_triangles)
        except Exception:
            raise ModelToolError(f"Could not load model: {primary}") from primary


def _load_glb_mesh_pygltf(path: str | Path, max_triangles: int) -> tuple:
    import numpy as np
    from pygltflib import GLTF2

    gltf = GLTF2().load(str(path))
    # Binary blob
    blob = gltf.binary_blob()
    if blob is None:
        # Some files store buffer as external; try first buffer uri data
        blob = b""
        if gltf.buffers:
            data = gltf.get_data_from_buffer_uri(gltf.buffers[0].uri) if gltf.buffers[0].uri else None
            blob = data or b""

    def accessor_np(accessor_idx: int) -> np.ndarray:
        acc = gltf.accessors[accessor_idx]
        bv = gltf.bufferViews[acc.bufferView]
        off = (bv.byteOffset or 0) + (acc.byteOffset or 0)
        ctype = acc.componentType
        type_name = acc.type
        comp_size = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}[ctype]
        comps = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[type_name]
        dtype = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16,
                 5125: np.uint32, 5126: np.float32}[ctype]
        stride = bv.byteStride or (comp_size * comps)
        count = acc.count
        if stride == comp_size * comps:
            arr = np.frombuffer(blob, dtype=dtype, count=count * comps, offset=off)
            return arr.reshape(count, comps).copy()
        # strided
        out = np.empty((count, comps), dtype=dtype)
        for i in range(count):
            base = off + i * stride
            out[i] = np.frombuffer(blob, dtype=dtype, count=comps, offset=base)
        return out

    # Materials → texture index + base colour
    mat_tex: list[int] = []
    mat_color: list[tuple[float, float, float]] = []
    for mat in (gltf.materials or []):
        pbr = mat.pbrMetallicRoughness
        factor = (pbr.baseColorFactor if pbr and pbr.baseColorFactor else None) or [0.7, 0.7, 0.7, 1]
        mat_color.append((float(factor[0]), float(factor[1]), float(factor[2])))
        tex_idx = -1
        if pbr and pbr.baseColorTexture is not None:
            ti = pbr.baseColorTexture.index
            if gltf.textures and 0 <= ti < len(gltf.textures):
                src = gltf.textures[ti].source
                if src is not None:
                    tex_idx = int(src)
        mat_tex.append(tex_idx)

    # Decode images (index = image index referenced by texture.source)
    from PIL import Image
    import io
    textures: list = []
    for img in (gltf.images or []):
        data = None
        try:
            if img.bufferView is not None:
                bv = gltf.bufferViews[img.bufferView]
                off = bv.byteOffset or 0
                length = bv.byteLength
                data = bytes(blob[off:off + length])
            elif img.uri:
                if img.uri.startswith("data:"):
                    import base64
                    data = base64.b64decode(img.uri.split(",", 1)[1])
                else:
                    data = gltf.get_data_from_buffer_uri(img.uri)
        except Exception:
            data = None
        if data:
            try:
                im = Image.open(io.BytesIO(data)).convert("RGBA")
                # Premultiply-ish: composite on mid grey so transparent pixels aren't black
                bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
                bg.alpha_composite(im)
                textures.append(np.asarray(bg.convert("RGB"), dtype=np.uint8))
            except Exception:
                textures.append(None)
        else:
            textures.append(None)

    # Node world matrices
    nodes = gltf.nodes or []
    world = [np.eye(4, dtype=np.float64) for _ in nodes]

    def node_matrix(node) -> np.ndarray:
        if node.matrix:
            m = np.array(node.matrix, dtype=np.float64).reshape(4, 4, order="F")  # column-major
            return m
        t = np.array(node.translation or [0, 0, 0], dtype=np.float64)
        s = np.array(node.scale or [1, 1, 1], dtype=np.float64)
        r = node.rotation or [0, 0, 0, 1]
        x, y, z, w = r
        rot = np.array([
            [1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
            [2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)],
            [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)],
        ], dtype=np.float64)
        m = np.eye(4, dtype=np.float64)
        m[:3, :3] = rot * s  # scale columns
        # proper S then R: R @ diag(s)
        m[:3, :3] = rot @ np.diag(s)
        m[:3, 3] = t
        return m

    def bake(idx: int, parent: np.ndarray):
        local = node_matrix(nodes[idx])
        world[idx] = parent @ local
        for c in (nodes[idx].children or []):
            bake(int(c), world[idx])

    roots = []
    if gltf.scenes and gltf.scene is not None and gltf.scene < len(gltf.scenes):
        roots = list(gltf.scenes[gltf.scene].nodes or [])
    elif gltf.scenes:
        roots = list(gltf.scenes[0].nodes or [])
    if not roots:
        children = {c for n in nodes for c in (n.children or [])}
        roots = [i for i in range(len(nodes)) if i not in children]

    ident = np.eye(4, dtype=np.float64)
    for r in roots:
        bake(int(r), ident)

    vertices: list = []
    uvs: list = []
    faces: list = []
    face_tex: list = []
    face_color: list = []
    v_base = 0

    def consume(mesh_idx: int, xform: np.ndarray):
        nonlocal v_base
        mesh = gltf.meshes[mesh_idx]
        for prim in mesh.primitives:
            attrs = prim.attributes
            pos_idx = getattr(attrs, "POSITION", None)
            if pos_idx is None and isinstance(attrs, dict):
                pos_idx = attrs.get("POSITION")
            if pos_idx is None:
                continue
            pos = accessor_np(int(pos_idx)).astype(np.float64)
            if pos.ndim == 1:
                pos = pos.reshape(-1, 3)
            # transform
            ones = np.ones((len(pos), 1))
            homogen = np.hstack([pos, ones])
            pos_w = (xform @ homogen.T).T[:, :3]

            uv = np.zeros((len(pos), 2), dtype=np.float64)
            tc = None
            # pygltflib Attributes: TEXCOORD_0 field or dict-style
            if hasattr(attrs, "TEXCOORD_0") and attrs.TEXCOORD_0 is not None:
                tc = attrs.TEXCOORD_0
            elif isinstance(attrs, dict) and attrs.get("TEXCOORD_0") is not None:
                tc = attrs["TEXCOORD_0"]
            else:
                # extras / __dict__
                tc = getattr(attrs, "__dict__", {}).get("TEXCOORD_0")
            if tc is not None:
                try:
                    uv = accessor_np(int(tc)).astype(np.float64)
                    if uv.ndim == 1:
                        uv = uv.reshape(-1, 2)
                except Exception:
                    uv = np.zeros((len(pos), 2), dtype=np.float64)

            mi = prim.material
            tex_idx = -1
            base = (0.65, 0.68, 0.72)
            if mi is not None and 0 <= mi < len(mat_tex):
                tex_idx = mat_tex[mi]
                base = mat_color[mi]

            if prim.indices is not None:
                idx = accessor_np(prim.indices).reshape(-1).astype(np.int64)
            else:
                idx = np.arange(len(pos), dtype=np.int64)

            mode = prim.mode if prim.mode is not None else 4
            tri = []
            if mode == 4:
                for i in range(0, len(idx) - 2, 3):
                    tri.append((int(idx[i]), int(idx[i+1]), int(idx[i+2])))
            elif mode == 5:
                for i in range(len(idx) - 2):
                    if i % 2 == 0:
                        tri.append((int(idx[i]), int(idx[i+1]), int(idx[i+2])))
                    else:
                        tri.append((int(idx[i+1]), int(idx[i]), int(idx[i+2])))
            elif mode == 6:
                for i in range(1, len(idx) - 1):
                    tri.append((int(idx[0]), int(idx[i]), int(idx[i+1])))
            else:
                continue

            # Negative determinant (reflection): reverse winding per glTF
            det = float(np.linalg.det(xform[:3, :3]))
            if det < 0:
                tri = [(a, c, b_) for a, b_, c in tri]

            for p in pos_w:
                vertices.append((float(p[0]), float(p[1]), float(p[2])))
            for u in uv:
                uvs.append((float(u[0]), float(u[1])))
            for a, b_, c in tri:
                faces.append((v_base + a, v_base + b_, v_base + c))
                face_tex.append(tex_idx)
                face_color.append(base)
            v_base += len(pos)

    seen = set()
    for i, node in enumerate(nodes):
        if node.mesh is not None:
            consume(int(node.mesh), world[i])
            seen.add(int(node.mesh))
    for mi in range(len(gltf.meshes or [])):
        if mi not in seen:
            consume(mi, ident)

    if not faces:
        raise ModelToolError("The model has no triangle faces to display.")

    if len(faces) > max_triangles:
        step = max(1, len(faces) // max_triangles)
        faces = faces[::step]
        face_tex = face_tex[::step]
        face_color = face_color[::step]

    return vertices, uvs, faces, face_tex, face_color, textures


def _load_glb_mesh_fallback(path: str | Path, max_triangles: int) -> tuple:
    """Minimal loader without pygltflib (no node transforms)."""
    doc, b = _read_glb(path)
    vertices, uvs, faces, face_tex, face_color = [], [], [], [], []
    v_base = 0
    for mesh in doc.get("meshes") or []:
        for prim in mesh.get("primitives") or []:
            attrs = prim.get("attributes") or {}
            if "POSITION" not in attrs:
                continue
            mode = prim.get("mode", 4)
            if mode not in (4, 5, 6):
                continue
            raw, count, stride, comps, ctype = _accessor_bytes(doc, b, attrs["POSITION"])
            if ctype != 5126 or comps != 3:
                continue
            positions = [struct.unpack_from("<3f", raw, i * stride) for i in range(count)]
            prim_uvs = [(0.0, 0.0)] * count
            if "TEXCOORD_0" in attrs:
                uraw, ucount, ustride, ucomps, uctype = _accessor_bytes(doc, b, attrs["TEXCOORD_0"])
                if uctype == 5126 and ucomps == 2:
                    prim_uvs = [struct.unpack_from("<2f", uraw, i * ustride) for i in range(ucount)]
            if "indices" in prim:
                iraw, icount, istride, icomps, ictype = _accessor_bytes(doc, b, prim["indices"])
                fmt = {5121: "B", 5123: "H", 5125: "I"}[ictype]
                idx = [struct.unpack_from("<" + fmt, iraw, i * istride)[0] for i in range(icount)]
            else:
                idx = list(range(count))
            tri = []
            if mode == 4:
                for i in range(0, len(idx) - 2, 3):
                    tri.append((v_base + idx[i], v_base + idx[i+1], v_base + idx[i+2]))
            vertices.extend(positions)
            uvs.extend(prim_uvs)
            for t in tri:
                faces.append(t)
                face_tex.append(-1)
                face_color.append((0.65, 0.68, 0.72))
            v_base += count
    if not faces:
        raise ModelToolError("The model has no triangle faces to display.")
    if len(faces) > max_triangles:
        step = max(1, len(faces) // max_triangles)
        faces = faces[::step]
        face_tex = face_tex[::step]
        face_color = face_color[::step]
    return vertices, uvs, faces, face_tex, face_color, []


def load_glb_vertices(path: str | Path, max_points: int = 25000) -> list[tuple[float, float, float]]:
    """Return (x, y, z) vertices from a .glb."""
    verts, _u, _f, _ft, _fc, _t = load_glb_mesh(path, max_triangles=max_points * 2)
    if len(verts) > max_points:
        step = max(1, len(verts) // max_points)
        verts = verts[::step]
    return verts
