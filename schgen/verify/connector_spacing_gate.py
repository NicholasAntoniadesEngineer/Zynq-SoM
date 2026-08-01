from __future__ import annotations

from dataclasses import dataclass, field

from schgen.generate.floorplan import OVERMOLD_SIDE_GAP
from schgen.generate.pcb import (
    CONN_MATING_FACE,
    PcbModel,
    _inst_pad_bbox,
)

_FAMILY_MIN_GAP_MM: dict[str, float] = {
    "HDMI-019S": 18.0,
}

_FAMILY_SIDE_GAP_MM: dict[str, float] = {
    "HDMI-019S": OVERMOLD_SIDE_GAP,
}

_FAMILY_OF: dict[str, str] = {mpn: mpn for mpn in _FAMILY_MIN_GAP_MM}

_SAME_BAND_FRAC = 0.5


def _conn_mpn(inst) -> str | None:
    if inst.value in CONN_MATING_FACE:
        return inst.value
    nm = inst.footprint.split(":")[-1]
    if nm in CONN_MATING_FACE:
        return nm
    return None


def _overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _same_edge_gap(a: tuple, b: tuple) -> tuple[str, float] | None:
    ox = _overlap_1d(a[0], a[2], b[0], b[2])
    oy = _overlap_1d(a[1], a[3], b[1], b[3])
    wx = min(a[2] - a[0], b[2] - b[0])
    hy = min(a[3] - a[1], b[3] - b[1])
    same_x_band = wx > 0 and ox >= _SAME_BAND_FRAC * wx
    same_y_band = hy > 0 and oy >= _SAME_BAND_FRAC * hy
    if same_y_band and not same_x_band:
        return "x", max(a[0], b[0]) - min(a[2], b[2])
    if same_x_band and not same_y_band:
        return "y", max(a[1], b[1]) - min(a[3], b[3])
    return None


@dataclass
class SpacingResult:
    ok: bool = True
    board_w: float = 0.0
    board_h: float = 0.0
    pairs: list[tuple] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    def summary(self) -> str:
        L = [f"CONNECTOR OVERMOLD SPACING GATE: {'PASS' if self.ok else 'FAIL'} "
             f"(board {self.board_w:g} x {self.board_h:g} mm)"]
        L.append(f"  same-edge overmold connector pairs: {len(self.pairs)} "
                 f"({len(self.violations)} too tight)")
        for ra, rb, fam, axis, gap, need, ok in self.pairs:
            mark = "OK " if ok else "BAD"
            L.append(f"    {mark} {ra:9s} <-> {rb:9s} {fam:12s} "
                     f"gap={gap:6.2f}mm along {axis} (need >= {need:g}mm)")
        for v in self.violations:
            L.append(f"    TOO-TIGHT {v}")
        return "\n".join(L)


def check(model: PcbModel) -> SpacingResult:
    res = SpacingResult(board_w=model.board_w, board_h=model.board_h)

    by_family: dict[str, list[tuple]] = {}
    for inst in model.insts:
        mpn = _conn_mpn(inst)
        if mpn is None:
            continue
        fam = _FAMILY_OF.get(mpn)
        if fam is None:
            continue
        bb = _inst_pad_bbox(inst)
        by_family.setdefault(fam, []).append((inst.ref, bb))

    conns = [(i.ref, _inst_pad_bbox(i)) for i in model.insts if _conn_mpn(i)]
    for ci in range(len(conns)):
        for cj in range(ci + 1, len(conns)):
            ra, a = conns[ci]
            rb, b = conns[cj]
            ox = _overlap_1d(a[0], a[2], b[0], b[2])
            oy = _overlap_1d(a[1], a[3], b[1], b[3])
            if ox > 0.05 and oy > 0.05:
                res.violations.append(
                    f"{ra} <-> {rb}: connector footprints OVERLAP "
                    f"(ox={ox:.2f} oy={oy:.2f}mm) — coincident/stacked placement")

    for fam, members in by_family.items():
        need = _FAMILY_MIN_GAP_MM[fam]
        members.sort(key=lambda m: m[0])
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                ra, a = members[i]
                rb, b = members[j]
                hit = _same_edge_gap(a, b)
                if hit is None:
                    continue
                axis, gap = hit
                ok = gap >= need
                res.pairs.append((ra, rb, fam, axis, gap, need, ok))
                if not ok:
                    res.violations.append(
                        f"{ra} <-> {rb} ({fam}): overmold gap {gap:.2f}mm along "
                        f"{axis} < required {need:g}mm — the two cable plugs' "
                        f"overmolds would collide; cannot mate both at once")

    fam_of_ref = {inst.ref: _FAMILY_OF.get(_conn_mpn(inst) or "")
                  for inst in model.insts if _conn_mpn(inst)}
    for fam, members in by_family.items():
        side_need = _FAMILY_SIDE_GAP_MM[fam]
        for ra, a in sorted(members):
            for rb, b in conns:
                if fam_of_ref.get(rb) == fam:
                    continue
                hit = _same_edge_gap(a, b)
                if hit is None:
                    continue
                axis, gap = hit
                ok = gap >= side_need
                res.pairs.append((ra, rb, f"{fam}|1", axis, gap, side_need, ok))
                if not ok:
                    res.violations.append(
                        f"{ra} <-> {rb} ({fam} one-sided): gap {gap:.2f}mm along "
                        f"{axis} < required {side_need:g}mm — the {fam} plug's "
                        f"own boot overhangs its copper into the neighbour")

    res.pairs.sort(key=lambda p: p[4])
    res.ok = not res.violations
    return res
