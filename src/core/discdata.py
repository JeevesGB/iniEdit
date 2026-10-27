from __future__ import annotations
import json
import re
from dataclasses import dataclass, fields
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
    sound_id: int = 0  # engine sound bank id (sound/engine/%05d); 0 = unknown

    @property
    def torque_nm(self) -> float:
        return self.torque_kgfm * KGFM_TO_NM


def _car_from_row(r: dict) -> DiscCar:
    """Build a DiscCar from a JSON row; unknown/extra keys ignored; sound_id optional."""
    data = {}
    for f in fields(DiscCar):
        if f.name not in r:
            continue
        val = r[f.name]
        if f.name == "sound_id":
            try:
                data[f.name] = int(val)
            except (TypeError, ValueError):
                data[f.name] = 0
        else:
            data[f.name] = val
    # required core fields must exist
    required = ("label", "name", "maker", "year", "price", "model", "drive",
                "power_ps", "torque_kgfm", "weight_kg")
    for k in required:
        if k not in data:
            raise KeyError(k)
    return DiscCar(**data)


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
            cars = []
            for r in raw:
                try:
                    cars.append(_car_from_row(r))
                except (KeyError, TypeError, ValueError):
                    continue
            return cls(cars)
        except (OSError, ValueError, TypeError):
            return cls()

    def __bool__(self) -> bool:
        return bool(self.cars)

    @property
    def labels(self) -> list[str]:
        return sorted(self.by_label)

    def has_maker(self, maker: str) -> bool:
        return _norm(maker) in self._maker_keys if maker.strip() else False

    def lookup(self, source: str) -> list[str]:
        if source == "cars.label":
            return self.labels
        if source == "cars.maker":
            return self.makers
        if source == "cars.sound_id":
            # unique non-zero sound bank ids as strings
            ids = sorted({c.sound_id for c in self.cars if c.sound_id})
            return [str(i) for i in ids]
        return []

    def search(self, text: str) -> list[DiscCar]:
        words = text.lower().split()
        return [c for c in self.cars
                if all(w in f"{c.label} {c.name} {c.maker} {c.drive} {c.year} {c.model} {c.sound_id}".lower()
                       for w in words)]
