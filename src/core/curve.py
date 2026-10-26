from __future__ import annotations
import re

Point = tuple[int, float]
DEFAULT_MAX_POINTS = 16
_PAIR_RE = re.compile(r"(\d+)\s*:\s*(-?(?:\d+(?:\.\d*)?|\.\d+))")


def parse_curve(text: str) -> list[Point]:
    match = re.search(r"(?im)^\s*[\w.\-]+\s*=\s*(.*?)\s*$", text)
    source = match.group(1) if match else text
    return [(int(x), float(y)) for x, y in _PAIR_RE.findall(source)]


def format_curve(points: list[Point]) -> str:
    return " ".join(f"{x}:{y:g}" for x, y in sorted(points, key=lambda p: p[0]))


def validate_points(points: list[Point], max_points: int = DEFAULT_MAX_POINTS) -> None:
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


KW_PER_HP = 0.745699872
POWER_UNITS = ("kW", "PS", "hp")


def power_in(unit: str, rpm: float, torque_nm: float) -> float:
    kw = power_kw(rpm, torque_nm)
    if unit == "PS":
        return kw_to_ps(kw)
    if unit == "hp":
        return kw / KW_PER_HP
    return kw


def torque_for_power(unit: str, rpm: float, power: float) -> float:
    kw = power * {"kW": 1.0, "PS": 1 / 1.3596216, "hp": KW_PER_HP}[unit]
    return kw * 9549.2966 / rpm


def peak_power(points: list[Point]) -> tuple[int, float] | None:
    if not points:
        return None
    rpm, nm = max(points, key=lambda p: p[0] * p[1])
    return rpm, power_kw(rpm, nm)


def interpolate(points: list[Point], rpm: float) -> float:
    pts = sorted(points)
    if not pts:
        return 0.0
    if rpm <= pts[0][0]:
        return pts[0][1]
    if rpm >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= rpm <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (rpm - x0) / (x1 - x0)
    return pts[-1][1]


def scale_torque(points: list[Point], percent: float) -> list[Point]:
    return [(x, round(max(0.0, y * percent / 100.0), 1)) for x, y in points]


def shift_rpm(points: list[Point], delta: int) -> list[Point]:
    moved = {max(0, x + delta): y for x, y in points}      # merging at 0 keeps the last one
    return sorted(moved.items())


def smooth(points: list[Point], passes: int = 1) -> list[Point]:
    pts = sorted(points)
    for _ in range(passes):
        if len(pts) < 3:
            break
        pts = [pts[0]] + [(pts[i][0], round((pts[i - 1][1] + 2 * pts[i][1] + pts[i + 1][1]) / 4, 1))
                          for i in range(1, len(pts) - 1)] + [pts[-1]]
    return pts


def fit_to_limit(points: list[Point], limit: int, max_points: int = DEFAULT_MAX_POINTS) -> list[Point]:
    pts = sorted(points)
    if not pts:
        return pts
    end_torque = interpolate(pts, limit)
    if pts[-1][0] < limit and len(pts) >= 2:      # extend along the last slope, never below zero
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        end_torque = max(0.0, y1 + (y1 - y0) * (limit - x1) / (x1 - x0))
    kept = [p for p in pts if p[0] < limit]
    kept.append((limit, round(end_torque, 1)))
    while len(kept) > max_points:                   # make room by dropping the flattest middle point
        i = min(range(1, len(kept) - 1), key=lambda k: abs(kept[k][1] - (kept[k - 1][1] + kept[k + 1][1]) / 2))
        del kept[i]
    return kept


def parse_loose(text: str) -> list[Point]:
    pairs = parse_curve(text)
    if pairs:
        return pairs
    rows = []
    for line in text.splitlines():
        if re.search(r"[\t;]", line):                 # spreadsheet / European CSV: decimal commas allowed
            fields = [f.strip().replace(",", ".") for f in re.split(r"[\t;]", line) if f.strip()]
        else:
            fields = [f for f in re.split(r"[\s,]+", line.strip()) if f]
        nums = [f for f in fields if re.fullmatch(r"-?\d+(?:\.\d+)?", f)]
        if len(nums) >= 2:
            rows.append((int(round(float(nums[0]))), float(nums[1])))
    return rows


def generate(peak_nm: float, peak_nm_rpm: int, peak_kw: float, peak_kw_rpm: int,
             idle: int, redline: int, max_points: int = DEFAULT_MAX_POINTS) -> list[Point]:
    if not (0 < idle < peak_nm_rpm <= peak_kw_rpm <= redline):
        raise ValueError("Needs idle < torque peak rpm <= power peak rpm <= rev limiter.")
    t_pow = peak_kw * 9549.2966 / peak_kw_rpm
    if t_pow > peak_nm * 1.0005:
        raise ValueError(f"{peak_kw:g} kW at {peak_kw_rpm} rpm needs {t_pow:.0f} Nm, more than the "
                         f"{peak_nm:g} Nm peak torque. Lower the power or raise the torque.")
    t_pow = min(t_pow, peak_nm)

    def torque(r: float) -> float:
        if r <= peak_nm_rpm:
            u = min(1.0, max(0.0, (r - idle) / max(1, peak_nm_rpm - idle)))
            return peak_nm * (0.55 + 0.45 * (u * u * (3 - 2 * u)))
        if r <= peak_kw_rpm:
            u = (r - peak_nm_rpm) / max(1, peak_kw_rpm - peak_nm_rpm)
            return peak_nm + (t_pow - peak_nm) * u
        return t_pow * (peak_kw_rpm / r) ** 1.6

    anchors = {peak_nm_rpm, peak_kw_rpm, redline}
    start = max(1000, int(round(idle / 500.0)) * 500)
    step = 250 * max(1, -(-(redline - start) // (250 * (max_points - 3))))
    grid = {r for r in range(start, redline, step)}
    rpms = sorted(anchors | grid)
    while len(rpms) > max_points:
        free = [r for r in rpms if r not in anchors]
        if not free:
            break
        free.remove(min(free, key=lambda r: min(abs(r - a) for a in anchors)))   # drop the point nearest an anchor
        rpms = sorted(anchors | set(free))
    return [(r, round(torque(r), 1)) for r in rpms]
