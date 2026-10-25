"""Tab / toolbar icons (black line art in gui/icons/*.png, scaled down on load)."""

from __future__ import annotations

from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent / "icons"
# GUI-only: which icon decorates which tab. Nothing here touches the .ini data or schema.
TAB_ICONS = {
    "mod": "mod",
    "maker": "maker",
    "car": "suspension",
    "curve": "curve",      # the torque curve tab
    "paints": "paint",
    "preview": "align-left",
    "model_tools": "model_tools",   # icons/model_tools.png (tab icon + panel header)
}
SAVE_ICON = "save"

_cache: dict[tuple[str, int], object] = {}


def load_icon(name: str, size: int = 18):
    """Return a Tk image for ``icons/<name>.png`` or None if it can't be loaded.

    Needs Pillow (installed with matplotlib); the app still works without icons.
    """
    if not name:
        return None
    key = (name, size)
    if key not in _cache:
        try:
            from PIL import Image, ImageTk

            img = Image.open(ICON_DIR / f"{name}.png").convert("RGBA").resize((size, size), Image.LANCZOS)
            _cache[key] = ImageTk.PhotoImage(img)
        except Exception:
            _cache[key] = None
    return _cache[key]
