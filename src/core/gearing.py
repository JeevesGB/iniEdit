"""Gearbox maths: tyre size -> speed per gear, ratio generators, presets."""
from __future__ import annotations
import math
import re

from . import curve as curve_mod

_TYRE_RE = re.compile(r"\s*(\d{3})/(\d{2})R(\d{2})\s*$")
DRIVETRAIN_EFFICIENCY = 0.90          # only used for the drive-force chart (an estimate)

PRESETS: dict[str, tuple[list[float], float, float]] = {
    # name: (gears, final drive, reverse)
    "4-speed economy": ([3.45, 1.95, 1.28, 0.92], 3.90, 3.10),
    "5-speed hatchback": ([3.58, 2.04, 1.38, 1.03, 0.82], 4.10, 3.40),
    "5-speed sports": ([3.32, 2.14, 1.57, 1.21, 0.97], 3.90, 3.30),
    "6-speed sports": ([3.62, 2.19, 1.52, 1.19, 0.97, 0.80], 3.72, 3.40),
    "6-speed supercar": ([3.36, 2.14, 1.52, 1.19, 0.97, 0.78], 3.42, 3.20),
}
SPACINGS = {
    "Even steps": 1.0,
    "Closer at the top (typical)": 0.85,
    "Closer at the top (sporty)": 0.72,
}


def tyre_radius_m(size: str) -> float | None:
    """Rolling radius in metres of a '205/55R16' tyre (about 2 % under the unloaded radius)."""
    m = _TYRE_RE.fullmatch(size or "")
    if not m:
        return None
    width, aspect, rim = (int(g) for g in m.groups())
    return (rim * 25.4 / 2 + width * aspect / 100.0) / 1000.0 * 0.98


def speed_kmh(rpm: float, gear: float, final_drive: float, radius_m: float) -> float:
    if gear <= 0 or final_drive <= 0:
        return 0.0
    return rpm * 2 * math.pi * radius_m / 60.0 / (gear * final_drive) * 3.6


def rpm_at(speed: float, gear: float, final_drive: float, radius_m: float) -> float:
    return speed / 3.6 / (2 * math.pi * radius_m) * 60.0 * gear * final_drive


def drive_force_n(rpm: float, torque_nm: float, gear: float, final_drive: float, radius_m: float) -> float:
    return torque_nm * gear * final_drive * DRIVETRAIN_EFFICIENCY / radius_m


def parse_gears(text: str) -> list[float]:
    out = []
    for token in (text or "").replace(",", " ").split():
        try:
            out.append(float(token))
        except ValueError:
            pass
    return out


def fmt_ratio(value: float) -> str:
    """3.25 -> '3.25', 1.0 -> '1.00', 0.825 -> '0.825' (at least two decimals, no clutter)."""
    text = f"{value:.3f}"
    return text[:-1] if text.endswith("0") else text


def format_gears(gears: list[float]) -> str:
    return " ".join(fmt_ratio(g) for g in gears)


def generate_gears(count: int, first: float, top: float, spacing: float = 0.85) -> list[float]:
    """`count` ratios from `first` down to `top`; spacing < 1 packs the steps closer at the top."""
    if count < 1:
        return []
    if count == 1:
        return [round(first, 3)]
    return [round(first * (top / first) ** ((i / (count - 1)) ** spacing), 3) for i in range(count)]


def final_drive_for_top_speed(speed: float, rpm: float, top_gear: float, radius_m: float) -> float:
    """Final drive that puts `rpm` in the top gear at `speed` km/h."""
    return rpm * 2 * math.pi * radius_m / 60.0 * 3.6 / (speed * top_gear)


def issues(gears: list[float]) -> list[str]:
    out = []
    if any(a <= b for a, b in zip(gears, gears[1:])):
        out.append("Ratios should get smaller from 1st gear upwards.")
    return out


def tractive_curve(points: list[curve_mod.Point], gear: float, final_drive: float, radius_m: float,
                   lo: int, hi: int, steps: int = 60) -> tuple[list[float], list[float]]:
    """(speed km/h, drive force N) between `lo` and `hi` rpm for one gear."""
    xs, ys = [], []
    for i in range(steps + 1):
        rpm = lo + (hi - lo) * i / steps
        xs.append(speed_kmh(rpm, gear, final_drive, radius_m))
        ys.append(drive_force_n(rpm, curve_mod.interpolate(points, rpm), gear, final_drive, radius_m))
    return xs, ys
