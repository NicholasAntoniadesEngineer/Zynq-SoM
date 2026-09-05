from __future__ import annotations

import math

from schgen.core import native as _nat

KICAD_TURN_SIGN = -1.0
QUADRANT_DEG = 90.0
FULL_TURN_DEG = 360.0

Box = tuple[float, float, float, float]


def _quadrant_exact_cos_sin(deg: float) -> tuple[float, float]:
    quarters, residual_deg = divmod(
        (KICAD_TURN_SIGN * deg) % FULL_TURN_DEG, QUADRANT_DEG)
    residual = math.radians(residual_deg)
    cs, sn = math.cos(residual), math.sin(residual)
    for _ in range(int(quarters)):
        cs, sn = -sn, cs
    return cs, sn


def turn_point_py(x: float, y: float, deg: float) -> tuple[float, float]:
    cs, sn = _quadrant_exact_cos_sin(deg)
    return (x * cs - y * sn, x * sn + y * cs)


def turn_point(x: float, y: float, deg: float) -> tuple[float, float]:
    if _nat.loaded():
        got = _nat.module().turn_point(x, y, deg)
        if _nat.trace():
            ref = turn_point_py(x, y, deg)
            if got != ref:
                raise AssertionError(
                    f"native turn_point DIVERGENCE: cpp={got} python={ref}")
        return got
    return turn_point_py(x, y, deg)


def turn_box_py(box: Box, deg: float) -> Box:
    corners = [turn_point_py(px, py, deg)
               for px in (box[0], box[2]) for py in (box[1], box[3])]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return (min(xs), min(ys), max(xs), max(ys))


def turn_box(box: Box, deg: float) -> Box:
    if _nat.loaded():
        got = _nat.module().turn_box(box, deg)
        if _nat.trace():
            ref = turn_box_py(box, deg)
            if got != ref:
                raise AssertionError(
                    f"native turn_box DIVERGENCE: cpp={got} python={ref}")
        return got
    return turn_box_py(box, deg)


def pad_half_extent_py(size_w: float, size_h: float,
                       deg: float) -> tuple[float, float]:
    cs, sn = _quadrant_exact_cos_sin(deg)
    ct, st = abs(cs), abs(sn)
    hw, hh = size_w / 2, size_h / 2
    return (ct * hw + st * hh, st * hw + ct * hh)


def pad_half_extent(size_w: float, size_h: float,
                    deg: float) -> tuple[float, float]:
    if _nat.loaded():
        got = _nat.module().pad_half_extent(size_w, size_h, deg)
        if _nat.trace():
            ref = pad_half_extent_py(size_w, size_h, deg)
            if got != ref:
                raise AssertionError(
                    "native pad_half_extent DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return pad_half_extent_py(size_w, size_h, deg)
