from __future__ import annotations
import json
from pathlib import Path

SETTINGS = Path.home() / ".gt3_mod_creator.json"
MAX_RECENT = 6


def load() -> dict:
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def update(**values) -> None:
    data = load()
    data.update(values)
    try:
        SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def recent_mods() -> list[Path]:
    found = []
    for item in load().get("recent_mods", []):
        path = Path(str(item))
        if (path / "mod.ini").is_file() and path not in found:
            found.append(path)
    return found[:MAX_RECENT]


def add_recent(folder: str | Path) -> None:
    folder = Path(folder)
    others = [p for p in recent_mods() if p != folder]
    update(recent_mods=[str(p) for p in [folder] + others][:MAX_RECENT], last_parent=str(folder.parent))


def last_parent() -> Path | None:
    path = Path(str(load().get("last_parent", "")))
    return path if str(path) not in ("", ".") and path.is_dir() else None
