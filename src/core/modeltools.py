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
