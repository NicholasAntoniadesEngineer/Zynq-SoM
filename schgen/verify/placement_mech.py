from __future__ import annotations

import re
from dataclasses import dataclass, field

from schgen.core import native as _nat
from schgen.generate.pcb import (
    CONN_MATING_FACE,
    EDGE_FLUSH_MM,
    ORIGIN_X,
    ORIGIN_Y,
    PcbModel,
    _inst_courtyard,
    _mating_face_out_dir,
)

_OVERLAP_EPS = 0.5

_PASSIVE_PREFIX = ("R", "C", "L")
_BUTTON_PREFIX = ("SW",)
_COINCELL_PREFIX = ("BT",)
_TESTPOINT_PREFIX = ("TP",)


def _ref_prefix(ref: str) -> str:
    m = re.match(r"[A-Za-z]+", ref)
    return m.group(0) if m else ref


def _is_passive_under_som(ref: str) -> bool:
    p = _ref_prefix(ref)
    if ref.startswith(("RS", "RJ", "LED")):
        return False
    return p in _PASSIVE_PREFIX


def _is_control(ref: str) -> bool:
    return _ref_prefix(ref) in (_BUTTON_PREFIX + _COINCELL_PREFIX)


def _rect_overlap_area_py(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ox = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    oy = max(0.0, min(ay1, by1) - max(ay0, by0))
    return ox * oy


def _rect_overlap_area(a, b) -> float:
    if not _nat.loaded():
        raise RuntimeError("native overlap_area required")
    got = float(_nat.module().overlap_area(a, b))
    if _nat.trace():
        ref = _rect_overlap_area_py(a, b)
        if got != ref:
            raise AssertionError(
                "native overlap_area DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


@dataclass
class MechResult:
    ok: bool = True
    board_w: float = 0.0
    board_h: float = 0.0
    n_connectors: int = 0
    connectors: list[tuple] = field(default_factory=list)
    bad_connectors: list[str] = field(default_factory=list)
    under_som: list[str] = field(default_factory=list)
    controls_under_som: list[str] = field(default_factory=list)
    top_under_som: list[str] = field(default_factory=list)
    face_top_on_bottom: list[str] = field(default_factory=list)
    n_face_top: int = 0
    som_core: tuple | None = None

    def summary(self) -> str:
        L = [f"LAW-6 PLACEMENT (mechanical) GATE: {'PASS' if self.ok else 'FAIL'} "
             f"(board {self.board_w:g} x {self.board_h:g} mm)"]
        sc = self.som_core
        if sc:
            L.append(f"  SoM module-body core: ({sc[0]:.1f},{sc[1]:.1f}).."
                     f"({sc[2]:.1f},{sc[3]:.1f}) mm — "
                     f"bottom-passives-only, TOP keepout")
        L.append(f"  off-board connectors: {self.n_connectors} "
                 f"({len(self.bad_connectors)} mis-placed)")
        for ref, mpn, edge, rot, face_dir, flush, ok in self.connectors:
            mark = "OK " if ok else "BAD"
            L.append(f"    {mark} {ref:9s} {mpn:16s} edge={edge} rot={rot:>3.0f} "
                     f"mouth->{face_dir} flush={flush:.1f}mm")
        for b in self.bad_connectors:
            L.append(f"    MISPLACED {b}")
        L.append(f"  non-passive parts under SoM core: {len(self.under_som)}")
        for u in self.under_som:
            L.append(f"    UNDER-SoM {u}")
        L.append(f"  controls under SoM core: {len(self.controls_under_som)}")
        for c in self.controls_under_som:
            L.append(f"    CONTROL-UNDER-SoM {c}")
        L.append(f"  carrier TOP parts under SoM core (keepout): "
                 f"{len(self.top_under_som)}")
        for t in self.top_under_som:
            L.append(f"    TOP-UNDER-SoM {t}")
        L.append(f"  user-facing parts (TP/LED/SW): {self.n_face_top} "
                 f"({len(self.face_top_on_bottom)} face-down)")
        for f in self.face_top_on_bottom:
            L.append(f"    FACE-DOWN {f}")
        return "\n".join(L)


def check(model: PcbModel) -> MechResult:
    res = MechResult(board_w=model.board_w, board_h=model.board_h,
                     som_core=model.som_core)
    bx0, by0 = ORIGIN_X, ORIGIN_Y
    bx1, by1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h
    edge_out = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}

    for inst in model.insts:
        mpn = inst.value if inst.value in CONN_MATING_FACE else None
        if mpn is None:
            nm = inst.footprint.split(":")[-1]
            if nm in CONN_MATING_FACE:
                mpn = nm
        if mpn is None:
            continue
        res.n_connectors += 1
        cx0, cy0, cx1, cy1 = _inst_courtyard(inst)
        d = {"N": cy0 - by0, "S": by1 - cy1, "W": cx0 - bx0, "E": bx1 - cx1}
        edge = min(d, key=lambda e: d[e])
        flush = d[edge]
        face_dir = _mating_face_out_dir(CONN_MATING_FACE[mpn], inst.rotation)
        mouth_out = (face_dir == edge_out[edge])
        on_edge = (flush <= EDGE_FLUSH_MM)
        ok = on_edge and mouth_out
        res.connectors.append(
            (inst.ref, mpn, edge, float(inst.rotation), face_dir, flush, ok))
        if not ok:
            why = []
            if not on_edge:
                why.append(f"interior ({flush:.1f}mm > {EDGE_FLUSH_MM:g}mm "
                           f"off the {edge} edge)")
            if not mouth_out:
                why.append(f"mouth {face_dir} faces inward (off-board for the "
                           f"{edge} edge is {edge_out[edge]})")
            res.bad_connectors.append(
                f"{inst.ref} ({inst.sheet}) {mpn}: " + "; ".join(why))

    core = model.som_core
    if core is not None:
        for inst in model.insts:
            ct = _inst_courtyard(inst)
            ov = _rect_overlap_area(ct, core)
            if ov <= _OVERLAP_EPS:
                continue
            if inst.mod_path.name.startswith("MountingHole"):
                continue
            if inst.mod_path.name.startswith("Fiducial"):
                continue
            if inst.sheet.startswith("som_j"):
                continue
            if inst.side == "bottom":
                continue          # LAW 6: only the TOP face under the SoM is keepout
            row = (f"{inst.ref} ({inst.sheet}) {inst.value} [TOP]: courtyard "
                   f"({ct[0]:.1f},{ct[1]:.1f})..({ct[2]:.1f},{ct[3]:.1f}) "
                   f"overlaps SoM core — carrier TOP under the module is a keepout")
            if _is_passive_under_som(inst.ref):
                res.top_under_som.append(row)
                continue
            res.under_som.append(row)
            if _is_control(inst.ref):
                res.controls_under_som.append(row)

    from schgen.generate.pcb.placement import _is_face_top_part
    for inst in model.insts:
        if not _is_face_top_part(inst.ref, inst.footprint, inst.footprint):
            continue
        res.n_face_top += 1
        if inst.side == "bottom":
            res.face_top_on_bottom.append(
                f"{inst.ref} ({inst.sheet}) {inst.value} [{inst.footprint}] "
                f"emits B.Cu — a user-facing part must present on the top face")

    res.ok = (not res.bad_connectors and not res.under_som
              and not res.controls_under_som and not res.top_under_som
              and not res.face_top_on_bottom)
    return res
