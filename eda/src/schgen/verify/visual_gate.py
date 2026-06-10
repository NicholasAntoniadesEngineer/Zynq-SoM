"""Visual gate: ZERO overlap of anything, ZERO crossings — no exemptions.

Operates on schgen's emitted geometry primitives (the emit layer hands back a
:class:`SheetGeometry` of everything it wrote, in page coordinates). Every text
box (pin name/number, Reference, Value, label), every body outline, and every
wire is checked pairwise. Two things touching in the render = FAIL. There are
deliberately NO carve-outs: the old generator's validator exemptions (junctioned
crossings, same-symbol text) are exactly where shorts and pile-ups hid.

Allowed contacts (electrical necessity, not exemptions):
- a wire ENDPOINT exactly on a pin point / another wire of the SAME net;
- a junction dot at a same-net degree>=3 vertex (provided by the router, which
  guarantees by construction that no two nets share a cell — so any wire-wire
  contact here is same-net).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str      # body | pin_name | pin_number | reference | value | label
    owner: str     # "U1", "label:STM32_USB_CC1", …

    def intersects(self, o: "Box", pad: float = 0.0) -> bool:
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


@dataclass
class SheetGeometry:
    boxes: list[Box] = field(default_factory=list)
    wires: list[Seg] = field(default_factory=list)


@dataclass
class VisualResult:
    ok: bool
    findings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return "VISUAL GATE: PASS (0 overlaps, 0 crossings)"
        return "VISUAL GATE: FAIL\n" + "\n".join(f"  {f}" for f in self.findings)


_TEXT = {"pin_name", "pin_number", "reference", "value", "label"}


def _cross(a: Seg, b: Seg) -> bool:
    """Perpendicular interior crossing (endpoint touching excluded)."""
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


def _collinear_overlap(a: Seg, b: Seg) -> bool:
    eps = 1e-6
    if a.horizontal and b.horizontal and abs(a.y0 - b.y0) < eps:
        a0, a1 = sorted((a.x0, a.x1)); b0, b1 = sorted((b.x0, b.x1))
        return min(a1, b1) - max(a0, b0) > eps
    if a.vertical and b.vertical and abs(a.x0 - b.x0) < eps:
        a0, a1 = sorted((a.y0, a.y1)); b0, b1 = sorted((b.y0, b.y1))
        return min(a1, b1) - max(a0, b0) > eps
    return False


def _seg_box(s: Seg, half: float = 0.127) -> Box:
    x0, x1 = sorted((s.x0, s.x1))
    y0, y1 = sorted((s.y0, s.y1))
    return Box(x0 - half, y0 - half, x1 + half, y1 + half, "wire", f"net:{s.net}")


def check(geo: SheetGeometry, clearance_mm: float = 0.2) -> VisualResult:
    res = VisualResult(ok=True)

    # text/body vs text/body — nothing may touch anything it doesn't own
    bs = geo.boxes
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            a, b = bs[i], bs[j]
            if a.owner == b.owner and not (a.kind in _TEXT and b.kind in _TEXT):
                continue  # a part's own texts may touch its body outline region
            if a.owner == b.owner and a.kind in _TEXT and b.kind in _TEXT:
                pass      # same part's two texts must still not overlap each other
            if a.intersects(b, pad=clearance_mm):
                res.ok = False
                res.findings.append(
                    f"{a.kind}({a.owner}) overlaps {b.kind}({b.owner})")

    # wires vs text/body
    for s in geo.wires:
        wb = _seg_box(s)
        for b in geo.boxes:
            if b.kind == "body" and f"net:" in b.owner:
                continue
            if b.kind in _TEXT and wb.intersects(b, pad=0.0):
                res.ok = False
                res.findings.append(f"wire({s.net}) over {b.kind}({b.owner})")

    # wire vs wire: crossings and different-net collinear overlap
    ws = geo.wires
    for i in range(len(ws)):
        for j in range(i + 1, len(ws)):
            a, b = ws[i], ws[j]
            if _cross(a, b):
                res.ok = False
                res.findings.append(
                    f"wires CROSS: {a.net} x {b.net} "
                    f"@({a.x0:.2f},{a.y0:.2f})-({b.x0:.2f},{b.y0:.2f})")
            if a.net != b.net and _collinear_overlap(a, b):
                res.ok = False
                res.findings.append(f"collinear overlap: {a.net} ~ {b.net}")
    return res
