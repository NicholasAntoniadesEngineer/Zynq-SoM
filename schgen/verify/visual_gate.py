from __future__ import annotations

from dataclasses import dataclass, field

from schgen.core import native as _nat
from schgen.core.config import VISUAL_CLEARANCE_MM


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str
    owner: str

    def intersects_py(self, o: Box, pad: float = 0.0) -> bool:
        return (self.x0 - pad < o.x1 and self.x1 + pad > o.x0
                and self.y0 - pad < o.y1 and self.y1 + pad > o.y0)

    def intersects(self, o: Box, pad: float = 0.0) -> bool:
        if not _nat.loaded():
            raise RuntimeError("native boxes_overlap required")
        got = bool(_nat.module().boxes_overlap(
            (self.x0, self.y0, self.x1, self.y1),
            (o.x0, o.y0, o.x1, o.y1), pad))
        if _nat.trace():
            ref = self.intersects_py(o, pad)
            if got is not ref:
                raise AssertionError(
                    "native boxes_overlap DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got


@dataclass(frozen=True)
class Seg:
    x0: float
    y0: float
    x1: float
    y1: float
    net: str

    @property
    def horizontal(self) -> bool:
        return abs(self.y0 - self.y1) < 1e-6

    @property
    def vertical(self) -> bool:
        return abs(self.x0 - self.x1) < 1e-6


@dataclass(frozen=True)
class Junction:
    x: float
    y: float


@dataclass
class SheetGeometry:
    boxes: list[Box] = field(default_factory=list)
    wires: list[Seg] = field(default_factory=list)
    junctions: list[Junction] = field(default_factory=list)


@dataclass
class VisualResult:
    ok: bool
    findings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return "VISUAL GATE: PASS (0 overlaps, 0 crossings)"
        return "VISUAL GATE: FAIL\n" + "\n".join(f"  {f}" for f in self.findings)


_TEXT = {"pin_name", "pin_number", "reference", "value", "label"}


def _cross_py(a: Seg, b: Seg) -> bool:
    if a.horizontal and b.vertical:
        h, v = a, b
    elif a.vertical and b.horizontal:
        h, v = b, a
    else:
        return False
    hx0, hx1 = sorted((h.x0, h.x1))
    vy0, vy1 = sorted((v.y0, v.y1))
    eps = 1e-6
    return (hx0 + eps < v.x0 < hx1 - eps) and (vy0 + eps < h.y0 < vy1 - eps)


def _cross(a: Seg, b: Seg) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native visual_hv_cross required")
    got = bool(_nat.module().visual_hv_cross(
        a.x0, a.y0, a.x1, a.y1, b.x0, b.y0, b.x1, b.y1))
    if _nat.trace():
        ref = _cross_py(a, b)
        if got is not ref:
            raise AssertionError(
                "native visual_hv_cross DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _collinear_overlap_py(a: Seg, b: Seg) -> bool:
    eps = 1e-6
    if a.horizontal and b.horizontal and abs(a.y0 - b.y0) < eps:
        a0, a1 = sorted((a.x0, a.x1))
        b0, b1 = sorted((b.x0, b.x1))
        return min(a1, b1) - max(a0, b0) > eps
    if a.vertical and b.vertical and abs(a.x0 - b.x0) < eps:
        a0, a1 = sorted((a.y0, a.y1))
        b0, b1 = sorted((b.y0, b.y1))
        return min(a1, b1) - max(a0, b0) > eps
    return False


def _collinear_overlap(a: Seg, b: Seg) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native collinear_overlap required")
    got = bool(_nat.module().collinear_overlap(
        a.x0, a.y0, a.x1, a.y1, b.x0, b.y0, b.x1, b.y1))
    if _nat.trace():
        ref = _collinear_overlap_py(a, b)
        if got is not ref:
            raise AssertionError(
                "native collinear_overlap DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _point_on_seg_py(px: float, py: float, s: Seg, *, interior_only: bool) -> bool:
    eps = 1e-6
    if s.horizontal:
        if abs(py - s.y0) > eps:
            return False
        lo, hi = sorted((s.x0, s.x1))
    elif s.vertical:
        if abs(px - s.x0) > eps:
            return False
        lo, hi = sorted((s.y0, s.y1))
    else:
        return False
    coord = px if s.horizontal else py
    if interior_only:
        return lo + eps < coord < hi - eps
    return lo - eps <= coord <= hi + eps


def _point_on_seg(px: float, py: float, s: Seg, *, interior_only: bool) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native point_on_seg required")
    got = _nat.module().point_on_seg(px, py, s.x0, s.y0, s.x1, s.y1,
                                     interior_only)
    if _nat.trace():
        ref = _point_on_seg_py(px, py, s, interior_only=interior_only)
        if got is not ref:
            raise AssertionError(
                "native point_on_seg DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _foreign_t_touch_py(a: Seg, b: Seg) -> tuple[float, float] | None:
    if a.net == b.net:
        return None
    for (ex, ey), other in (((a.x0, a.y0), b), ((a.x1, a.y1), b),
                            ((b.x0, b.y0), a), ((b.x1, b.y1), a)):
        if _point_on_seg(ex, ey, other, interior_only=False):
            return (ex, ey)
    return None


def _foreign_t_touch(a: Seg, b: Seg) -> tuple[float, float] | None:
    if not _nat.loaded():
        raise RuntimeError("native foreign_t_touch required")
    hit = _nat.module().foreign_t_touch(
        a.x0, a.y0, a.x1, a.y1, b.x0, b.y0, b.x1, b.y1, a.net == b.net)
    got = None if hit is None else (float(hit[0]), float(hit[1]))
    if _nat.trace():
        ref = _foreign_t_touch_py(a, b)
        if got != ref:
            raise AssertionError(
                "native foreign_t_touch DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _seg_box(s: Seg, half: float = 0.127) -> Box:
    x0, x1 = sorted((s.x0, s.x1))
    y0, y1 = sorted((s.y0, s.y1))
    return Box(x0 - half, y0 - half, x1 + half, y1 + half, "wire", f"net:{s.net}")


def check(
    geo: SheetGeometry, clearance_mm: float = VISUAL_CLEARANCE_MM
) -> VisualResult:
    """Transport page geometry to the complete native validation stage."""
    if not _nat.loaded():
        raise RuntimeError("native check_visual_geometry required")
    ok, findings = _nat.module().check_visual_geometry(
        [(b.x0, b.y0, b.x1, b.y1, b.kind, b.owner) for b in geo.boxes],
        [(s.x0, s.y0, s.x1, s.y1, s.net) for s in geo.wires],
        [(j.x, j.y) for j in geo.junctions], clearance_mm)
    return VisualResult(ok=ok, findings=findings)
