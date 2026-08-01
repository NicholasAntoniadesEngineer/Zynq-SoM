from __future__ import annotations

from dataclasses import dataclass, field

from schgen.core.config import CROSS_K
from schgen.generate import ratsnest as rn
from schgen.generate.pcb import (
    ORIGIN_X,
    ORIGIN_Y,
    PcbModel,
    _inst_courtyard,
    _inst_pad_bbox,
)

DISPERSION_MAX = 9.0
SMALL_N = 3


@dataclass
class RatsnestResult:
    ok: bool = True
    off_board: list[str] = field(default_factory=list)
    dispersed: list[str] = field(default_factory=list)
    clusters: list[tuple[str, int, float, float]] = field(default_factory=list)
    cross_mm: float = 0.0
    total_mm: float = 0.0
    n_cross: int = 0
    n_subsystems: int = 0
    cross_budget_mm: float = 0.0
    board_w: float = 0.0
    board_h: float = 0.0

    @property
    def cross_ratio(self) -> float:
        return (self.cross_mm / self.total_mm) if self.total_mm else 0.0

    @property
    def cross_ok(self) -> bool:
        return self.cross_mm <= self.cross_budget_mm

    def summary(self) -> str:
        L = [f"LAW-5 RATSNEST GATE: {'PASS' if self.ok else 'FAIL'} "
             f"(board {self.board_w:g} x {self.board_h:g} mm)"]
        L.append(f"  off-board parts: {len(self.off_board)}")
        for r in self.off_board:
            L.append(f"    OFF-BOARD {r}")
        L.append(f"  dispersed subsystems: {len(self.dispersed)} "
                 f"(threshold {DISPERSION_MAX:g}x)")
        for d in self.dispersed:
            L.append(f"    DISPERSED {d}")
        L.append(f"  cross-subsystem airwire: {self.cross_mm:g} mm "
                 f"(budget {self.cross_budget_mm:.0f} mm, "
                 f"{'OK' if self.cross_ok else 'OVER'}; {self.n_cross} edges; "
                 f"{self.cross_mm:g}/{self.total_mm:g} mm = "
                 f"{100 * self.cross_ratio:.1f}% of total)")
        L.append("  per-subsystem clusters (n, bbox mm, dispersion):")
        for name, n, area, disp in self.clusters:
            L.append(f"    {name:22s} n={n:<3d} bbox_area={area:8.0f} "
                     f"disp={disp:5.1f}")
        return "\n".join(L)


def dispersion_by_sheet(res: RatsnestResult) -> dict[str, float]:
    return {name: disp for name, _n, _area, disp in res.clusters}


def check(model: PcbModel, npp: dict | None = None,
          mst: dict | None = None) -> RatsnestResult:
    res = RatsnestResult(board_w=model.board_w, board_h=model.board_h)
    bx0, by0 = ORIGIN_X, ORIGIN_Y
    bx1, by1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h

    by_sheet: dict[str, list[tuple[float, float, float, float, float]]] = {}
    for inst in model.insts:
        px0, py0, px1, py1 = _inst_pad_bbox(inst)
        if (px0 < bx0 - 1e-6 or py0 < by0 - 1e-6
                or px1 > bx1 + 1e-6 or py1 > by1 + 1e-6):
            res.off_board.append(
                f"{inst.ref} ({inst.sheet}): copper "
                f"({px0:.1f},{py0:.1f})..({px1:.1f},{py1:.1f}) outside "
                f"Edge.Cuts ({bx0:.0f},{by0:.0f})..({bx1:.0f},{by1:.0f})")
        cx0, cy0, cx1, cy1 = _inst_courtyard(inst)
        if inst.mod_path.name.startswith(("MountingHole", "Fiducial")):
            continue
        area = (cx1 - cx0) * (cy1 - cy0)
        by_sheet.setdefault(inst.sheet, []).append((cx0, cy0, cx1, cy1, area))

    for name in sorted(by_sheet):
        if name.startswith("som_j"):
            continue
        boxes = by_sheet[name]
        n = len(boxes)
        minx = min(b[0] for b in boxes)
        miny = min(b[1] for b in boxes)
        maxx = max(b[2] for b in boxes)
        maxy = max(b[3] for b in boxes)
        bbox_area = (maxx - minx) * (maxy - miny)
        sum_area = sum(b[4] for b in boxes) or 1.0
        disp = bbox_area / sum_area
        res.clusters.append((name, n, round(bbox_area, 1), round(disp, 2)))
        if n > SMALL_N and disp > DISPERSION_MAX:
            res.dispersed.append(
                f"{name}: dispersion {disp:.1f}x > {DISPERSION_MAX:g}x "
                f"(bbox {maxx - minx:.0f}x{maxy - miny:.0f} mm for {n} parts)")
    res.clusters.sort(key=lambda c: -c[3])

    res.cross_mm, res.total_mm, res.n_cross = rn.cross_airwire_length(
        model, npp, mst)
    res.n_subsystems = sum(1 for name in by_sheet
                           if not name.startswith("som_j"))
    res.cross_budget_mm = round(
        CROSS_K * (model.board_w * model.board_h) ** 0.5 * res.n_subsystems, 1)

    res.ok = (not res.off_board and not res.dispersed and res.cross_ok)
    return res
