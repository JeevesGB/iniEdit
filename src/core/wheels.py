"""Disc rim catalogue: ids from 24_wheel.csv + {id}.png thumbnails."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data" / "wheels.json"
_THUMBS = Path(__file__).resolve().parent.parent / "gui" / "wheel_thumbs"
_CSV = Path(__file__).resolve().parent / "gt3db" / "24_wheel.csv"

# Marker image only — never offered as a selectable rim id
CURRENT_MARKER = "current.png"


@dataclass(frozen=True)
class DiscWheel:
    id: str
    index: int
    thumb: Path | None  # filesystem path to {id}.png, or None


class DiscWheels:
    def __init__(self, wheels: list[DiscWheel] | None = None):
        self.wheels = wheels or []
        self.by_id = {w.id: w for w in self.wheels}

    def __bool__(self) -> bool:
        return bool(self.wheels)

    @property
    def ids(self) -> list[str]:
        return [w.id for w in self.wheels]

    def search(self, text: str) -> list[DiscWheel]:
        words = text.lower().split()
        if not words:
            return list(self.wheels)
        return [w for w in self.wheels if all(t in w.id.lower() for t in words)]

    @staticmethod
    def thumbs_dir() -> Path:
        return _THUMBS

    @staticmethod
    def current_marker_path() -> Path | None:
        p = _THUMBS / CURRENT_MARKER
        return p if p.is_file() else None

    @classmethod
    def _thumb_for(cls, wheel_id: str) -> Path | None:
        """Resolve {id}.png under wheel_thumbs; never treat current.png as a rim."""
        if not wheel_id or wheel_id.lower() == "current":
            return None
        p = _THUMBS / f"{wheel_id}.png"
        return p if p.is_file() else None

    @classmethod
    def load(cls) -> "DiscWheels":
        if _DATA.is_file():
            try:
                raw = json.loads(_DATA.read_text(encoding="utf-8"))
                wheels = []
                for r in raw:
                    wid = str(r["id"]).strip()
                    if not wid or wid.lower() == "current":
                        continue
                    thumb = cls._thumb_for(wid)
                    # fall back to explicit thumb name in json if present
                    if thumb is None and r.get("thumb") and r["thumb"] != CURRENT_MARKER:
                        p = _THUMBS / r["thumb"]
                        if p.is_file():
                            thumb = p
                    wheels.append(DiscWheel(id=wid, index=int(r.get("index", 0)), thumb=thumb))
                if wheels:
                    return cls(wheels)
            except (OSError, ValueError, KeyError, TypeError):
                pass

        if _CSV.is_file():
            import csv
            wheels = []
            with _CSV.open(encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    label = r["label"].strip()
                    if not label or label.lower() == "current":
                        continue
                    wheels.append(DiscWheel(
                        id=label,
                        index=int(r["index"]),
                        thumb=cls._thumb_for(label),
                    ))
            return cls(wheels)

        # Last resort: every *.png in the thumbs folder except current.png
        if _THUMBS.is_dir():
            wheels = []
            for i, p in enumerate(sorted(_THUMBS.glob("*.png"))):
                if p.name.lower() == CURRENT_MARKER:
                    continue
                wheels.append(DiscWheel(id=p.stem, index=i, thumb=p))
            return cls(wheels)

        return cls()
