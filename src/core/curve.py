"""Curve helpers: parse, format, validate and analyse ``x:y`` curves.

Curve format is a space separated list of ``x:y`` pairs, e.g. for a torque
curve ``1000:205 2000:250 3000:282`` (rpm:Nm).  Pure Python, no GUI imports.
"""

from __future__ import annotations

import re

Point = tuple[int, float]

DEFAULT_MAX_POINTS = 16

_PAIR_RE = re.compile(r"(\d+)\s*:\s*(-?(?:\d+(?:\.\d*)?|\.\d+))")


def parse_curve(text: str) -> list[Point]:
    """Extract ``x:y`` pairs from a bare value or a ``curve = ...`` line."""
    match = re.search(r"(?im)^\s*[\w.\-]+\s*=\s*(.*?)\s*$", text)
    source = match.group(1) if match else text
    return [(int(x), float(y)) for x, y in _PAIR_RE.findall(source)]


def format_curve(points: list[Point]) -> str:
    """Format points (sorted by x) as ``x:y x:y ...``."""
    return " ".join(f"{x}:{y:g}" for x, y in sorted(points, key=lambda p: p[0]))


def validate_points(points: list[Point], max_points: int = DEFAULT_MAX_POINTS) -> None:
    """Raise ``ValueError`` describing the first problem found."""
    if not points:
        raise ValueError("No x:y pairs were found.")
    if len(points) > max_points:
        raise ValueError(f"Found {len(points)} points; at most {max_points} are supported.")
    xs = [p[0] for p in points]
    if len(xs) != len(set(xs)):
        raise ValueError("The curve contains duplicate x values.")
    if any(x < 0 for x in xs):
        raise ValueError("x values must be zero or greater.")


def validate_text(text: str, max_points: int = DEFAULT_MAX_POINTS) -> str | None:
    """Return an error message for a curve value string, or ``None`` if valid."""
    stripped = text.strip()
    if not stripped:
        return "Curve is empty."
    leftover = _PAIR_RE.sub("", stripped).strip()
    if leftover:
        return f"Unrecognised text in curve: '{leftover[:20]}'"
    try:
        validate_points(parse_curve(stripped), max_points)
    except ValueError as exc:
        return str(exc)
    return None


def peak(points: list[Point]) -> Point | None:
    return max(points, key=lambda p: p[1]) if points else None


def power_kw(rpm: float, torque_nm: float) -> float:
    return torque_nm * rpm / 9549.2966


def kw_to_ps(kw: float) -> float:
    return kw * 1.3596216
