from __future__ import annotations
from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent / "icons"
TAB_ICONS = {
    "mod": "mod",
    "maker": "maker",
    "car": "suspension",
    "curve": "curve",      
    "gearbox": "gearbox",
    "paints": "paint",
    "preview": "align-left",
    "model_tools": "model_tools",   
}
SAVE_ICON = "save"

SCALE = 1.0
_cache: dict[tuple[str, int], object] = {}


def load_icon(name: str, size: int = 18):
    if not name:
        return None
    size = int(round(size * SCALE))
    key = (name, size)
    if key not in _cache:
        try:
            from PIL import Image, ImageTk

            img = Image.open(ICON_DIR / f"{name}.png").convert("RGBA").resize((size, size), Image.LANCZOS)
            _cache[key] = ImageTk.PhotoImage(img)
        except Exception:
            _cache[key] = None
    return _cache[key]
