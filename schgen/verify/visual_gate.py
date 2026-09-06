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

    def intersects(self, o: Box, pad: float = 0.0) -> bool:
        if _nat.loaded():
            return _nat.module().boxes_overlap(
                (self.x0, self.y0, self.x1, self.y1),
                (o.x0, o.y0, o.x1, o.y1), pad)
        return (self.x0 - pad < o.x1 and self.x1 + pad > o.x0
                and self.y0 - pad < o.y1 and self.y1 + pad > o.y0)


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
    if _nat.loaded():
        got = bool(_nat.module().visual_hv_cross(
            a.x0, a.y0, a.x1, a.y1, b.x0, b.y0, b.x1, b.y1))
        if _nat.trace():
            ref = _cross_py(a, b)
            if got is not ref:
                raise AssertionError(
                    "native visual_hv_cross DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _cross_py(a, b)


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
    if _nat.loaded():
        got = bool(_nat.module().collinear_overlap(
            a.x0, a.y0, a.x1, a.y1, b.x0, b.y0, b.x1, b.y1))
        if _nat.trace():
            ref = _collinear_overlap_py(a, b)
            if got is not ref:
                raise AssertionError(
                    "native collinear_overlap DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _collinear_overlap_py(a, b)


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
    if _nat.loaded():
        got = _nat.module().point_on_seg(px, py, s.x0, s.y0, s.x1, s.y1,
                                         interior_only)
        if _nat.trace():
            ref = _point_on_seg_py(px, py, s, interior_only=interior_only)
            if got is not ref:
                raise AssertionError(
                    "native point_on_seg DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _point_on_seg_py(px, py, s, interior_only=interior_only)


def _foreign_t_touch(a: Seg, b: Seg) -> tuple[float, float] | None:
    if a.net == b.net:
        return None
    for (ex, ey), other in (((a.x0, a.y0), b), ((a.x1, a.y1), b),
                            ((b.x0, b.y0), a), ((b.x1, b.y1), a)):
        if _point_on_seg(ex, ey, other, interior_only=False):
            return (ex, ey)
    return None


def _seg_box(s: Seg, half: float = 0.127) -> Box:
    x0, x1 = sorted((s.x0, s.x1))
    y0, y1 = sorted((s.y0, s.y1))
    return Box(x0 - half, y0 - half, x1 + half, y1 + half, "wire", f"net:{s.net}")


def check(
    geo: SheetGeometry, clearance_mm: float = VISUAL_CLEARANCE_MM
) -> VisualResult:
    res = VisualResult(ok=True)

    bs = geo.boxes
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            a, b = bs[i], bs[j]
            if a.owner == b.owner and not (a.kind in _TEXT and b.kind in _TEXT):
                continue
            if a.owner == b.owner and a.kind in _TEXT and b.kind in _TEXT:
                pass
            if a.intersects(b, pad=clearance_mm):
                res.ok = False
                res.findings.append(
                    f"{a.kind}({a.owner}) overlaps {b.kind}({b.owner})")

    for s in geo.wires:
        wb = _seg_box(s)
        for b in geo.boxes:
            if b.kind == "body" and "net:" in b.owner:
                continue
            pad = -0.14 if (b.kind == "label"
                            and b.owner == f"label:{s.net}") else 0.0
            if b.kind in _TEXT and wb.intersects(b, pad=pad):
                res.ok = False
                res.findings.append(f"wire({s.net}) over {b.kind}({b.owner})")

    ws = geo.wires
    for i in range(len(ws)):
        for j in range(i + 1, len(ws)):
            a, b = ws[i], ws[j]
            if _cross(a, b):
                res.ok = False
                res.findings.append(
                    f"wires CROSS: {a.net} x {b.net} "
                    f"@({a.x0:.2f},{a.y0:.2f})-({b.x0:.2f},{b.y0:.2f})")
            if _collinear_overlap(a, b):
                res.ok = False
                tag = ("same-net wire-over-wire" if a.net == b.net
                       else "collinear overlap")
                res.findings.append(f"{tag}: {a.net} ~ {b.net}")
            tt = _foreign_t_touch(a, b)
            if tt is not None:
                res.ok = False
                res.findings.append(
                    f"different-net T-touch: {a.net} endpoint on {b.net} "
                    f"@({tt[0]:.2f},{tt[1]:.2f})")

    for jn in geo.junctions:
        nets = {s.net for s in geo.wires
                if _point_on_seg(jn.x, jn.y, s, interior_only=False)}
        if len(nets) > 1:
            res.ok = False
            res.findings.append(
                f"cross-net junction @({jn.x:.2f},{jn.y:.2f}): {sorted(nets)}")
    return res
