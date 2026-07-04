"""LAW-5 ratsnest/placement gate — the visual-correctness oracle for the PCB.

The defect this closes: ``schgen board`` CLAIMED "per-subsystem ratsnest
bundles" and passed DRC=0, but the actual board was BROKEN — the ratsnest was a
board-spanning HAIRBALL (footprints NOT grouped by subsystem) AND several
connectors (FMC J1, the LCD FFC, hdmi_tx, the microSD) were placed OFF-BOARD,
below the Edge.Cuts outline. DRC=0 hid all of it: airwires, off-board placement
and grouping are NOT DRC errors. LAW 5 makes the placement itself a HARD gate.

INVARIANTS (any failure HARD-FAILS the board):
  (a) NO OFF-BOARD part — every footprint's courtyard sits inside Edge.Cuts.
  (b) EVERY subsystem is CONTIGUOUS — its footprints' bounding-box area must not
      exceed ``DISPERSION_MAX`` x the sum of their courtyard areas (a scattered
      subsystem has a huge bbox vs little real copper; a tight cluster ~1-4x).
      This is the DECISIVE grouping oracle: the old hairball sat at 50-230x; a
      properly clustered board is 1-3x.
  (c) the ABSOLUTE cross-subsystem airwire length must stay under a board-scaled
      budget ``CROSS_K * sqrt(board_area) * n_subsystems`` — a scattered board
      runs many long inter-block wires. (A RATIO of cross/total is deliberately
      NOT used: tight clustering shrinks the intra-wire denominator, so a better
      layout would paradoxically have a HIGHER ratio. Absolute cross length is
      the honest measure — the old hairball's was ~26.8 m, the clustered board's
      ~15.7 m, a 41% drop.)

The numbers are reported in the verdict so a regression shows AS numbers, not a
binary. LAW 4: strict — a dispersed subsystem or an off-board part is FIXED in
the placer (grow the zone / grow the outline / improve the affinity placement),
never waived here.
"""

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

# A subsystem whose footprints' bbox area exceeds this multiple of the sum of
# their courtyard areas is DISPERSED (scattered, not a contiguous cluster). A
# perfectly packed block is ~1.4-2; a small/2-part block can read higher purely
# from geometry, so the threshold is generous — the hairball this catches sat at
# 50-230x.
DISPERSION_MAX = 9.0
# CROSS_K (absolute cross-subsystem airwire budget coefficient: budget =
# CROSS_K * sqrt(board_area_mm2) * n_subsystems) lives in config.py — imported
# above. It bites a board-spanning placement but passes a clustered one.
# small subsystems (<= this many parts) are exempt from the dispersion metric:
# 2-3 parts can have a degenerate bbox/area ratio with no real scatter. They
# still must be ON-BOARD (rule a) and contribute to the airwire budget.
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
    """{sheet: dispersion} from a computed :class:`RatsnestResult` — the T1
    composition ledger's per-sheet scalar view of the SAME numbers the summary
    prints (additive helper; the gate verdict/summary are unchanged)."""
    return {name: disp for name, _n, _area, disp in res.clusters}


def check(model: PcbModel) -> RatsnestResult:
    res = RatsnestResult(board_w=model.board_w, board_h=model.board_h)
    bx0, by0 = ORIGIN_X, ORIGIN_Y
    bx1, by1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h

    # (a) off-board: any courtyard corner outside the Edge.Cuts rectangle.
    # MOUNTING HOLES are FIXED-position fab-art: the placer corner-FORCES them to
    # the four board corners (so a board-mechanical sheet of 4 holes spans the
    # whole board by design). They must still be ON-BOARD (checked here), but
    # they are excluded from the per-subsystem DISPERSION metric below — measuring
    # the spread of deliberately corner-spread holes as "dispersion" is a category
    # error (the metric exists to catch a FREE-placed subsystem that got
    # scattered, exactly why the equally-fixed SoM receptacle sheets are skipped).
    by_sheet: dict[str, list[tuple[float, float, float, float, float]]] = {}
    for inst in model.insts:
        # off-board test uses the COPPER (pad) bbox, not the courtyard: an edge
        # connector's mating area (USB-C shell / SD slot / PMOD module / RJ45
        # jack) legitimately overhangs the board edge so a cable can mate (LAW 6),
        # while its pads stay on-board. A genuinely off-board part has copper
        # outside Edge.Cuts and still fails. Dispersion below still uses the
        # courtyard (clustering is about the physical footprint extent).
        px0, py0, px1, py1 = _inst_pad_bbox(inst)
        if (px0 < bx0 - 1e-6 or py0 < by0 - 1e-6
                or px1 > bx1 + 1e-6 or py1 > by1 + 1e-6):
            res.off_board.append(
                f"{inst.ref} ({inst.sheet}): copper "
                f"({px0:.1f},{py0:.1f})..({px1:.1f},{py1:.1f}) outside "
                f"Edge.Cuts ({bx0:.0f},{by0:.0f})..({bx1:.0f},{by1:.0f})")
        cx0, cy0, cx1, cy1 = _inst_courtyard(inst)
        if inst.mod_path.name.startswith(("MountingHole", "Fiducial")):
            continue          # corner-/keepout-forced fixed-position fab-art: the
            #                   3 global fiducials span the board by design (corner
            #                   L) and the local pair sits at the SoM keepout — like
            #                   the mounting holes, measuring their spread as
            #                   "dispersion" is a category error (fixed, net-less).
        area = (cx1 - cx0) * (cy1 - cy0)
        by_sheet.setdefault(inst.sheet, []).append((cx0, cy0, cx1, cy1, area))

    # (b) dispersion per subsystem (skip the SoM receptacle sheets + tiny ones).
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

    # (c) absolute, board-scaled cross-subsystem airwire budget.
    res.cross_mm, res.total_mm, res.n_cross = rn.cross_airwire_length(model)
    res.n_subsystems = sum(1 for name in by_sheet
                           if not name.startswith("som_j"))
    res.cross_budget_mm = round(
        CROSS_K * (model.board_w * model.board_h) ** 0.5 * res.n_subsystems, 1)

    res.ok = (not res.off_board and not res.dispersed and res.cross_ok)
    return res
