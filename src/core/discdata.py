from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path

KGFM_TO_NM = 9.80665


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass(frozen=True)
class DiscCar:
    label: str
    name: str
    maker: str
    year: int
    price: int
    model: str
    drive: str
    power_ps: float
    torque_kgfm: float
    weight_kg: float

    @property
    def torque_nm(self) -> float:
        return self.torque_kgfm * KGFM_TO_NM


class DiscCars:
    def __init__(self, cars: list[DiscCar] | None = None):
        self.cars = cars or []
        self.by_label = {c.label: c for c in self.cars}
        seen: dict[str, str] = {}
        for c in self.cars:
            if c.maker.strip() not in ("", "-"):
                seen.setdefault(_norm(c.maker), c.maker)
        self.makers = sorted((m for m in seen.values() if "?" not in m), key=str.lower)
        self._maker_keys = set(seen)

    @classmethod
    def load(cls, path: str | Path) -> "DiscCars":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            return cls([DiscCar(**{f: r[f] for f in DiscCar.__dataclass_fields__}) for r in raw])
        except (OSError, ValueError, KeyError, TypeError):
            return cls()

    def __bool__(self) -> bool:
        return bool(self.cars)

    @property
    def labels(self) -> list[str]:
        return sorted(self.by_label)

    def has_maker(self, maker: str) -> bool:
        return _norm(maker) in self._maker_keys if maker.strip() else False

    def lookup(self, source: str) -> list[str]:
        return {"cars.label": self.labels, "cars.maker": self.makers}.get(source, [])

    def search(self, text: str) -> list[DiscCar]:
        words = text.lower().split()
        return [c for c in self.cars
                if all(w in f"{c.label} {c.name} {c.maker} {c.drive} {c.year} {c.model}".lower() for w in words)]
